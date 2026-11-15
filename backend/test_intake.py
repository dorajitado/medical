from io import BytesIO
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, generate_uid
from backend.app import create_app

HEADERS = {'X-Workspace-Request': '1'}

def ct_bytes(study=None, series=None, sop=None, **changes):
    meta = FileMetaDataset()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.MediaStorageSOPClassUID = CTImageStorage
    meta.MediaStorageSOPInstanceUID = sop or generate_uid()
    ds = FileDataset(None, {}, file_meta=meta, preamble=b'\0' * 128)
    ds.SOPClassUID = CTImageStorage
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID = study or generate_uid()
    ds.SeriesInstanceUID = series or generate_uid()
    ds.Modality = 'CT'
    ds.FrameOfReferenceUID = ds.SeriesInstanceUID
    ds.PatientID = 'SYNTHETIC_QA_ONLY'
    ds.PatientName = 'SYNTHETIC^QA'
    ds.StudyDate = '20260101'
    ds.StudyTime = '120000'
    ds.SeriesNumber = 1
    ds.InstanceNumber = 1
    ds.Rows = ds.Columns = 2
    ds.ImagePositionPatient = [0,0,0]
    ds.ImageOrientationPatient = [1,0,0,0,1,0]
    ds.PixelSpacing = [1,1]
    ds.RescaleSlope = 1
    ds.RescaleIntercept = -1024
    ds.BitsAllocated = ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = 'MONOCHROME2'
    ds.PixelData = b'\0' * 8
    for key, value in changes.items():
        if value is None:
            delattr(ds, key)
        else:
            setattr(ds, key, value)
    result = BytesIO()
    ds.save_as(result, enforce_file_format=True)
    return result.getvalue()


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.client = TestClient(create_app(self.path), base_url='http://127.0.0.1:8000')
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.temp.cleanup()

    def start(self, total=1):
        response = self.client.post('/api/imports', headers=HEADERS, json={'total':total})
        self.assertEqual(response.status_code, 201)
        return response.json()['id']

    def upload(self, jid, content):
        response = self.client.post(f'/api/imports/{jid}/files', headers={**HEADERS, 'Content-Type':'application/octet-stream'}, content=content)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def finish(self, jid):
        response = self.client.post(f'/api/imports/{jid}/finish', headers=HEADERS)
        self.assertEqual(response.status_code, 200, response.text)

    def test_import_preserves_bytes_and_groups_series(self):
        study, series = generate_uid(), generate_uid()
        original = ct_bytes(study, series)
        jid = self.start(2)
        self.assertEqual(self.upload(jid, original)['outcome'], 'imported')
        self.upload(jid, ct_bytes(study, series))
        self.finish(jid)
        studies = self.client.get('/api/studies').json()['items']
        self.assertEqual(len(studies), 1)
        detail = self.client.get(f"/api/studies/{studies[0]['id']}/series").json()['items']
        self.assertEqual(detail[0]['instance_count'], 2)
        self.assertEqual(detail[0]['ctpa'], 'unknown')
        self.assertEqual(detail[0]['validation'], 'metadata_only')
        hashes = [hashlib.sha256(f.read_bytes()).digest() for f in (self.path/'originals').glob('*')]
        self.assertIn(hashlib.sha256(original).digest(), hashes)
        self.assertFalse(list((self.path/'staging').glob('*')))

    def test_duplicate_and_uid_collision_do_not_overwrite(self):
        ids = [generate_uid() for _ in range(3)]
        original = ct_bytes(*ids)
        jid = self.start(3)
        self.upload(jid, original)
        self.assertEqual(self.upload(jid, original)['outcome'], 'duplicates')
        self.assertEqual(self.upload(jid, ct_bytes(*ids, StudyDescription='different'))['outcome'], 'failed')
        self.finish(jid)
        files = list((self.path/'originals').glob('*'))
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].read_bytes(), original)

    def test_rejects_wrong_or_missing_metadata(self):
        cases = [b'not dicom', ct_bytes(Modality='MR'), ct_bytes(PixelSpacing=None), ct_bytes(NumberOfFrames=2), ct_bytes(ImageType=['LOCALIZER']), ct_bytes(PixelSpacing=[-1,1]), ct_bytes(ImageOrientationPatient=[1,0,0,1,0,0])]
        jid = self.start(len(cases))
        for payload in cases:
            self.assertEqual(self.upload(jid,payload)['outcome'], 'excluded')
        self.finish(jid)
        self.assertEqual(self.client.get('/api/studies').json()['items'], [])
        self.assertEqual(list((self.path/'originals').glob('*')), [])

    def test_cancel_finish_and_total_guards(self):
        jid = self.start()
        self.assertEqual(self.client.post(f'/api/imports/{jid}/finish', headers=HEADERS).status_code, 409)
        self.assertEqual(self.client.post('/api/imports', headers=HEADERS, json={'total':1}).status_code, 409)
        self.client.post(f'/api/imports/{jid}/cancel', headers=HEADERS)
        self.assertEqual(self.client.post(f'/api/imports/{jid}/files', headers={**HEADERS,'Content-Type':'application/octet-stream'}, content=ct_bytes()).status_code,409)

    def test_restart_recovers_jobs_and_staging(self):
        jid = self.start()
        (self.path/'staging'/'managed.part').write_bytes(b'partial')
        with TestClient(create_app(self.path), base_url='http://127.0.0.1:8000') as restarted:
            jobs = restarted.get('/api/imports').json()['items']
            self.assertEqual(jobs[0]['id'], jid)
            self.assertEqual(jobs[0]['status'], 'interrupted')
            self.assertFalse((self.path/'staging'/'managed.part').exists())

    def test_size_limit_and_path_names_are_not_used(self):
        jid = self.start()
        with patch('backend.app.MAX_FILE_BYTES', 2):
            self.assertEqual(self.upload(jid,b'too large')['outcome'],'excluded')
        self.finish(jid)
        self.assertFalse(list((self.path/'staging').glob('*')))

    def test_reports_versions_and_study_isolation(self):
        jid = self.start(2)
        self.upload(jid,ct_bytes())
        self.upload(jid,ct_bytes())
        self.finish(jid)
        a,b = self.client.get('/api/studies').json()['items']
        path = f"/api/studies/{a['id']}/reports"
        for value in ['No nodule.', 'Possible nodule. <script>not executable</script>']:
            self.assertEqual(self.client.post(path,headers=HEADERS,json={'source':'hospital_transcription','text':value}).status_code,201)
        self.assertEqual(len(self.client.get(path).json()['items']),2)
        self.assertEqual(self.client.get(f"/api/studies/{b['id']}/reports").json()['items'],[])
        self.assertEqual(self.client.post(path,headers=HEADERS,json={'source':'hospital_transcription','text':'   '}).status_code,422)
        self.assertEqual(self.client.post('/api/studies/not-found/reports',headers=HEADERS,json={'source':'personal_note','text':'hello'}).status_code,404)
        with TestClient(create_app(self.path),base_url='http://127.0.0.1:8000') as restarted:
            self.assertEqual(len(restarted.get(path).json()['items']),2)

    def test_models_never_claim_unconfigured_inference_ready(self):
        items = self.client.get('/api/models').json()['items']
        self.assertEqual(len(items),3)
        self.assertTrue(all(not m['executable'] and m['weights_sha256'] is None and m['validation_status']=='not_evaluated' for m in items))

    def test_report_source_is_explicit_and_schema_rejects_forged_source(self):
        jid=self.start()
        self.upload(jid,ct_bytes())
        self.finish(jid)
        study=self.client.get('/api/studies').json()['items'][0]
        route=f"/api/studies/{study['id']}/reports"
        self.assertEqual(self.client.post(route,headers=HEADERS,json={'source':'user_authored','text':'Written by user'}).status_code,201)
        self.assertEqual(self.client.get(route).json()['items'][0]['source'],'user_authored')
        self.assertEqual(self.client.post(route,headers=HEADERS,json={'source':'certified_hospital_original','text':'bad source'}).status_code,422)

    def test_total_cannot_be_exceeded(self):
        jid=self.start()
        self.upload(jid,ct_bytes())
        self.assertEqual(self.client.post(f'/api/imports/{jid}/files',headers={**HEADERS,'Content-Type':'application/octet-stream'},content=ct_bytes()).status_code,409)

    def test_cross_study_series_collision_rolls_back(self):
        series = generate_uid()
        jid=self.start(2)
        self.upload(jid,ct_bytes(series=series))
        self.assertEqual(self.upload(jid,ct_bytes(series=series))['outcome'],'failed')
        self.assertEqual(len(self.client.get('/api/studies').json()['items']),1)
        self.assertEqual(len(list((self.path/'originals').glob('*'))),1)

if __name__ == '__main__':
    unittest.main()
