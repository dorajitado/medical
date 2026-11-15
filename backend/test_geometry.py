import hashlib
import json
import sqlite3
from pathlib import Path
import unittest
from tempfile import TemporaryDirectory
import numpy as np
from fastapi.testclient import TestClient
from pydicom.uid import generate_uid
from backend.app import create_app
from backend.test_intake import ct_bytes, HEADERS

class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.client=TestClient(create_app(self.root),base_url='http://127.0.0.1:8000')
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.temp.cleanup()

    def load(self,positions,variants=None,**changes):
        uid,series=generate_uid(),generate_uid()
        jid=self.client.post('/api/imports',headers=HEADERS,json={'total':len(positions)}).json()['id']
        for i,position in enumerate(positions):
            options={'ImagePositionPatient':position,'PixelSpacing':[2,3],**changes}
            if variants:options.update(variants[i])
            payload=ct_bytes(uid,series,**options)
            response=self.client.post(f'/api/imports/{jid}/files',headers={**HEADERS,'Content-Type':'application/octet-stream'},content=payload)
            self.assertEqual(response.json()['outcome'],'imported')
        self.client.post(f'/api/imports/{jid}/finish',headers=HEADERS)
        with sqlite3.connect(self.root/'workspace.sqlite3') as c:
            study=c.execute('SELECT id FROM studies WHERE study_uid=?',(uid,)).fetchone()[0]
        return self.client.get(f'/api/studies/{study}/series').json()['items'][0]['id']

    def test_sorted_slice_geometry_and_distance(self):
        sid=self.load([[10,20,34],[10,20,30],[10,20,32]])
        geo=self.client.get(f'/api/series/{sid}/geometry').json()
        self.assertTrue(geo['supported'])
        self.assertEqual(geo['spacing_xyz'],[3,2,2])
        self.assertEqual(geo['origin'],[10,20,30])
        result=self.client.post(f'/api/series/{sid}/probe',headers=HEADERS,json={'x':1,'y':1,'z':1}).json()
        self.assertEqual(result['patient_lps_mm'],[13,22,32])
        self.assertAlmostEqual(result['hu'],-1024,delta=1e-4)
        length=self.client.post(f'/api/series/{sid}/distance',headers=HEADERS,json={'start':[0,0,0],'end':[1,1,2]}).json()
        self.assertAlmostEqual(length['distance_mm'],np.sqrt(29),delta=1e-4)

    def test_oblique_and_reversed_patient_directions(self):
        a=2**-.5
        sid=self.load([[10,20,34],[10,20,30],[10,20,32]],ImageOrientationPatient=[-a,-a,0,a,-a,0])
        geo=self.client.get(f'/api/series/{sid}/geometry').json()
        self.assertTrue(geo['supported'])
        result=self.client.post(f'/api/series/{sid}/probe',headers=HEADERS,json={'x':1,'y':1,'z':1}).json()
        np.testing.assert_allclose(result['patient_lps_mm'],[10-a,20-5*a,32],atol=1e-4)

    def test_irregular_duplicate_and_gantry_tilt_are_rejected(self):
        for positions in [[[0,0,0],[0,0,1],[0,0,3]],[[0,0,0],[0,0,0]],[[0,0,0],[1,0,1],[2,0,2]]]:
            sid=self.load(positions)
            self.assertFalse(self.client.get(f'/api/series/{sid}/geometry').json()['supported'])
            self.assertEqual(self.client.post(f'/api/series/{sid}/open',headers=HEADERS).status_code,422)
            self.assertEqual(self.client.post(f'/api/series/{sid}/probe',headers=HEADERS,json={'x':0,'y':0,'z':0}).status_code,422)

    def test_out_of_bounds_and_padding(self):
        sid=self.load([[0,0,0]],PixelPaddingValue=0)
        result=self.client.post(f'/api/series/{sid}/probe',headers=HEADERS,json={'x':0,'y':0,'z':0}).json()
        self.assertIsNone(result['hu'])
        self.assertTrue(result['padding'])
        self.assertEqual(self.client.post(f'/api/series/{sid}/probe',headers=HEADERS,json={'x':20,'y':0,'z':0}).status_code,422)
        self.assertFalse(self.client.get(f'/api/series/{sid}/geometry').json()['mpr_supported'])

    def test_per_slice_slope_intercept_signed_pixels(self):
        raw=np.array([[-20,0],[100,200]],dtype='<i2').tobytes()
        sid=self.load([[0,0,0]],PixelRepresentation=1,PixelData=raw,RescaleSlope=2,RescaleIntercept=-100)
        sample=self.client.post(f'/api/series/{sid}/probe',headers=HEADERS,json={'x':0,'y':0,'z':0}).json()
        self.assertEqual(sample['hu'],-140)
        sample=self.client.post(f'/api/series/{sid}/probe',headers=HEADERS,json={'x':1,'y':1,'z':0}).json()
        self.assertEqual(sample['hu'],300)

    def test_corrupted_pixel_data_and_source_tampering(self):
        sid=self.load([[0,0,0]],PixelData=b'\0\0')
        self.assertFalse(self.client.get(f'/api/series/{sid}/geometry').json()['supported'])
        sid=self.load([[0,0,1]])
        with sqlite3.connect(self.root/'workspace.sqlite3') as c:
            name=c.execute('SELECT stored_name FROM instances WHERE series_id=?',(sid,)).fetchone()[0]
        (self.root/'originals'/name).write_bytes(b'tampered')
        self.assertFalse(self.client.get(f'/api/series/{sid}/geometry').json()['supported'])

    def test_proxy_does_not_expose_admin_or_unknown_series(self):
        self.assertEqual(self.client.get('/imaging/system').status_code,404)
        self.assertEqual(self.client.get('/imaging/instances/foo/file').status_code,404)
        self.assertEqual(self.client.get('/api/series/unknown/geometry').status_code,404)
        self.assertEqual(self.client.post('/api/series/unknown/open',headers=HEADERS).status_code,404)

    def test_mixed_dimensions_spacing_and_orientation_are_rejected(self):
        for variant in [{'Columns':3},{'PixelSpacing':[1,1]},{'ImageOrientationPatient':[0,1,0,1,0,0]}]:
            sid=self.load([[0,0,0],[0,0,1]],variants=[{},variant])
            self.assertFalse(self.client.get(f'/api/series/{sid}/geometry').json()['supported'])

    def test_per_slice_rescale_and_active_import_guard(self):
        sid=self.load([[0,0,0],[0,0,1],[0,0,2]],variants=[{'RescaleIntercept':0},{'RescaleIntercept':100},{'RescaleIntercept':200}])
        sample=self.client.post(f'/api/series/{sid}/probe',headers=HEADERS,json={'x':0,'y':0,'z':2}).json()
        self.assertEqual(sample['hu'],200)
        jid=self.client.post('/api/imports',headers=HEADERS,json={'total':1}).json()['id']
        self.assertFalse(self.client.get(f'/api/series/{sid}/geometry').json()['supported'])
        self.client.post(f'/api/imports/{jid}/cancel',headers=HEADERS)
        self.assertTrue(self.client.get(f'/api/series/{sid}/geometry').json()['supported'])

if __name__=='__main__':
    unittest.main()
