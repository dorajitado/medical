"""Explicit public-example integration test, separated from the user's workspace.

Download tests/reference_files/example_ct_sm.nii.gz from the official project to
data/qa-week3 first. This utility wraps the small public NIfTI as QA-labelled CT
DICOM, exercises the production intake/queue/worker, and retains local evidence.
It never discovers or reads the production data/workspace.sqlite3 database.
"""
import hashlib
import json
from pathlib import Path
import time
from uuid import uuid4

from fastapi.testclient import TestClient
import nibabel as nib
import numpy as np
from pydicom.uid import generate_uid

from .analysis_runtime import ROOT
from .app import create_app
from .test_intake import HEADERS, ct_bytes


def main():
    root = ROOT / 'data' / 'qa-week3'
    sample = root / 'example_ct_sm.nii.gz'
    expected = 'e50c00b2914e2cac0aaee8e7f3b5f57d44d9f21bfd5c0577271c54c0cb49e9fb'
    if hashlib.sha256(sample.read_bytes()).hexdigest() != expected:
        raise RuntimeError('Public QA sample hash differs from the recorded version.')
    image = nib.load(sample)
    voxels = np.rint(np.asanyarray(image.dataobj)).astype('<i2')
    lps = np.diag([-1., -1., 1., 1.]) @ image.affine
    spacing = np.linalg.norm(lps[:3, :3], axis=0)
    direction = lps[:3, :3] / spacing
    folder = root / ('workspace-' + str(uuid4()))
    study, series = generate_uid(), generate_uid()
    with TestClient(create_app(folder), base_url='http://127.0.0.1:8000') as client:
        jid = client.post('/api/imports', headers=HEADERS, json={'total': voxels.shape[2]}).json()['id']
        for z in range(voxels.shape[2]):
            payload = ct_bytes(study, series, Rows=voxels.shape[1], Columns=voxels.shape[0],
                               ImagePositionPatient=(lps @ [0, 0, z, 1])[:3].tolist(),
                               ImageOrientationPatient=np.r_[direction[:, 0], direction[:, 1]].tolist(),
                               PixelSpacing=[spacing[1], spacing[0]], PixelRepresentation=1,
                               PixelData=voxels[:, :, z].T.copy().tobytes(), RescaleSlope=1, RescaleIntercept=0,
                               StudyDescription='PUBLIC EXAMPLE QA ONLY', SeriesDescription='Public model smoke test',
                               SliceThickness=spacing[2], InstanceNumber=z + 1)
            response = client.post(f'/api/imports/{jid}/files', headers={**HEADERS, 'Content-Type': 'application/octet-stream'}, content=payload)
            if response.json()['outcome'] != 'imported':
                raise RuntimeError('QA intake failed')
        client.post(f'/api/imports/{jid}/finish', headers=HEADERS)
        study_id = client.get('/api/studies').json()['items'][0]['id']
        sid = client.get(f'/api/studies/{study_id}/series').json()['items'][0]['id']
        response = client.post(f'/api/series/{sid}/analyses', headers=HEADERS, json={'model_id': 'total', 'confirmed': True})
        response.raise_for_status()
        run = response.json()
        print(json.dumps({'workspace': str(folder), 'run_id': run['id'], 'status': run['status']}), flush=True)
        # A bounded smoke test; work remains cancellable even if a driver stalls.
        deadline = time.monotonic() + 600
        previous = None
        while time.monotonic() < deadline:
            history = client.get(f'/api/series/{sid}/analyses').json()['items']
            run = next(r for r in history if r['id'] == run['id'])
            if run['stage'] != previous:
                print(json.dumps({'status': run['status'], 'stage': run['stage']}), flush=True)
                previous = run['stage']
            if run['status'] not in {'queued', 'running'}:
                break
            time.sleep(.5)
        if run['status'] != 'completed':
            client.post(f"/api/analyses/{run['id']}/cancel", headers=HEADERS)
            raise RuntimeError(f"QA inference not completed: {run['status']}; {run['error']}")
        result = client.get(f"/api/analyses/{run['id']}/result").json()
        count = sum(s['voxel_count'] for s in result['structures'])
        if not count:
            raise RuntimeError('Public sample produced no retained anatomy; investigate output mapping.')
        for z in [0, voxels.shape[2] // 2, voxels.shape[2] - 1]:
            plane = client.get(f"/api/analyses/{run['id']}/slices/{z}").json()
            np.testing.assert_allclose(np.array(plane['hu']).reshape(voxels.shape[1], voxels.shape[0]).T, voxels[:, :, z], atol=1e-4)
        evidence = {'workspace': str(folder), 'series_id': sid, 'run_id': run['id'],
                    'sample_sha256': expected, 'source': 'https://github.com/wasserth/TotalSegmentator/blob/master/tests/reference_files/example_ct_sm.nii.gz',
                    'shape_xyz': list(voxels.shape), 'metrics': result['metrics'],
                    'segmented_structures': [s['title'] for s in result['structures'] if s['voxel_count']],
                    'segmented_voxels': count, 'sample_hu_planes_verified': 3,
                    'clinical_validation': False}
        (root / 'last-run.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(evidence, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
