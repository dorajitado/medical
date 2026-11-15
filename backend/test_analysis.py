"""Isolated regression tests for spatial transforms, volumes and job lifecycle.

Synthetic masks below are explicit test fixtures, never production AI outputs.
Tolerances: source-world coordinates 1e-4 mm, voxel counts exact, volume 1e-4 mm³.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
import nibabel as nib
import numpy as np
from pydicom.uid import generate_uid

from .analysis import AnalysisManager
from .analysis_runtime import ROOT, inference_environment, runtime_status
from .analysis_runtime import CONFIGURATION
from .analysis_volume import affine_ras, convert_source, eligible, restore_output
from .app import create_app
from .geometry import GeometryError, patient_point, validate_series
from .storage import Store
from .test_intake import HEADERS, ct_bytes


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root)
        self.client = TestClient(create_app(self.root), base_url='http://127.0.0.1:8000')
        self.client.__enter__()
        self.managers = []
        # Unit fixtures never launch a real neural network and remain portable
        # to a machine without GPU packages. Integration QA runs are separate.
        self.runtime_patch = patch('backend.analysis.runtime_status', return_value={'ready': True, 'weights_digest': 'synthetic-test-only'})
        self.runtime_patch.start()

    def tearDown(self):
        for manager in self.managers:
            manager.close()
        self.client.__exit__(None, None, None)
        self.runtime_patch.stop()
        self.temp.cleanup()

    def load(self, orientation=None, positions=None):
        """Distinct asymmetric pixels and reversed import order expose axis flips."""
        study, series = generate_uid(), generate_uid()
        if orientation is None:
            orientation = [1, 0, 0, 0, 1, 0]
        a, b = np.array(orientation[:3]), np.array(orientation[3:])
        normal = np.cross(a, b)
        if positions is None:
            positions = [np.array([10., 20., 30.]) + normal * z * 2 for z in range(3)]
        jid = self.client.post('/api/imports', headers=HEADERS, json={'total': 3}).json()['id']
        for z in [2, 0, 1]:
            pixels = np.array([[z * 10, 1], [2, 3]], dtype='<u2')
            payload = ct_bytes(study, series, ImagePositionPatient=list(positions[z]),
                               ImageOrientationPatient=orientation, PixelSpacing=[2, 3],
                               RescaleSlope=z + 1, RescaleIntercept=-100, PixelData=pixels.tobytes())
            self.client.post(f'/api/imports/{jid}/files', headers={**HEADERS, 'Content-Type': 'application/octet-stream'}, content=payload)
        self.client.post(f'/api/imports/{jid}/finish', headers=HEADERS)
        with self.store.connect() as c:
            return c.execute('SELECT id FROM series WHERE series_uid=?', (series,)).fetchone()[0]

    def manager(self):
        manager = AnalysisManager(self.store)
        self.managers.append(manager)
        return manager

    def fixture_output(self, sid):
        """Create two labelled voxels with exact expected physical volume."""
        folder = self.root / 'fixture'
        folder.mkdir()
        source = convert_source(self.store, sid, folder)
        labels = np.zeros(source['geometry']['shape_xyz'], dtype=np.uint8)
        labels[0, 0, 1] = labels[1, 0, 1] = 10
        nib.save(nib.Nifti1Image(labels, np.array(source['affine_ras'])), folder / 'prediction.nii.gz')
        return folder, source, labels

    def test_oblique_reversed_affine_hu_and_provenance(self):
        v = 2 ** -.5
        sid = self.load([-v, -v, 0, v, -v, 0])
        folder, source, _ = self.fixture_output(sid)
        image = nib.load(folder / 'input.nii.gz')
        volume = np.asanyarray(image.dataobj)
        self.assertEqual(volume[0, 0, 2], -40)
        self.assertEqual(volume[1, 0, 1], -98)
        info = source['geometry']
        world = (image.affine @ [1, 1, 2, 1])[:3] * [-1, -1, 1]
        np.testing.assert_allclose(world, patient_point(info, 1, 1, 2), atol=1e-4)
        self.assertEqual(source['array_axes'], 'XYZ: column,row,sorted slice')
        self.assertEqual(len(source['sources']), 3)
        self.assertEqual(source['input_sha256'], hashlib.sha256((folder / 'input.nii.gz').read_bytes()).hexdigest())
        self.assertNotIn('report', source)

    def test_mask_restore_volume_centroid_and_translated_grid(self):
        sid = self.load()
        folder, source, labels = self.fixture_output(sid)
        # Shift model grid origin one source column and shift its labels back.
        shifted = np.zeros_like(labels)
        shifted[0, 0, 1] = 10
        affine = np.array(source['affine_ras'])
        affine[:3, 3] += affine[:3, 0]
        nib.save(nib.Nifti1Image(shifted, affine), folder / 'prediction.nii.gz')
        result = restore_output(folder)
        restored = np.load(folder / 'labels.npy')
        self.assertEqual(restored[1, 0, 1], 10)
        self.assertEqual(restored[0, 0, 1], 0)
        lung = result['structures'][0]
        self.assertEqual(lung['voxel_count'], 1)
        self.assertAlmostEqual(lung['volume_mm3'], 12, delta=1e-4)
        np.testing.assert_allclose(lung['centroid_lps_mm'], [13, 20, 32], atol=1e-4)

    def test_fractional_or_invalid_model_labels_fail(self):
        sid = self.load()
        folder, source, labels = self.fixture_output(sid)
        for value in [.5, 118, -1, float('nan')]:
            invalid = labels.astype(np.float32)
            invalid[0, 0, 0] = value
            nib.save(nib.Nifti1Image(invalid, np.array(source['affine_ras'])), folder / 'prediction.nii.gz')
            with self.assertRaises(GeometryError):
                restore_output(folder)
        self.assertFalse((folder / 'result.json').exists())

    def test_unrelated_mask_grid_and_source_position_drift_are_blocked(self):
        sid = self.load()
        folder, source, labels = self.fixture_output(sid)
        affine = np.array(source['affine_ras'])
        affine[:3, 3] += 10000
        nib.save(nib.Nifti1Image(labels, affine), folder / 'prediction.nii.gz')
        with self.assertRaises(GeometryError):
            restore_output(folder)
        info = source['geometry']
        info['positions'][1][0] += .02
        self.assertTrue(eligible(info))

    def test_anisotropic_model_grid_restores_exact_source_voxel(self):
        sid = self.load()
        folder, source, _ = self.fixture_output(sid)
        affine = np.array(source['affine_ras'])
        affine[:3, 1] /= 2
        affine[:3, 2] /= 2
        model = np.zeros((2, 3, 5), dtype=np.uint8)
        model[1, 2, 2] = 10
        nib.save(nib.Nifti1Image(model, affine), folder / 'prediction.nii.gz')
        result = restore_output(folder)
        labels = np.load(folder / 'labels.npy')
        self.assertEqual(labels[1, 1, 1], 10)
        self.assertEqual(int(np.count_nonzero(labels)), 1)
        self.assertAlmostEqual(result['structures'][0]['volume_mm3'], 12, delta=1e-4)

    def test_empty_masks_are_not_normal_and_result_access_is_gated(self):
        sid = self.load()
        folder, source, labels = self.fixture_output(sid)
        nib.save(nib.Nifti1Image(np.zeros_like(labels), np.array(source['affine_ras'])), folder / 'prediction.nii.gz')
        result = restore_output(folder)
        self.assertTrue(all(s['status'] == 'no_segment' for s in result['structures']))
        self.assertIn('질환', result['limitations'][0])
        manager = self.manager()
        rid = self.insert(sid, 'failed')
        with self.assertRaises(GeometryError):
            manager.result(rid)
        self.assertEqual(self.client.get(f'/api/analyses/{rid}/result').status_code, 422)

    def insert(self, sid, status):
        rid = str(uuid4())
        with self.store.connect() as c:
            snapshot = json.dumps({'configuration': CONFIGURATION, 'runtime': {'weights_digest': 'synthetic-test-only'}})
            c.execute("INSERT INTO analysis_runs(id,series_id,model_id,status,stage,snapshot) VALUES (?,?,'total',?,?,?)", (rid, sid, status, status, snapshot))
        return rid

    def test_cancel_wins_and_restart_keeps_previous_versions(self):
        sid = self.load()
        manager = self.manager()
        previous = self.insert(sid, 'completed')
        queued = self.insert(sid, 'queued')
        running = self.insert(sid, 'running')
        manager.cancel(queued)
        manager.update(queued, 'completed', 'completed')
        self.assertEqual(manager.get(queued)['status'], 'cancelled')
        self.store.initialize()
        self.assertEqual(manager.get(running)['status'], 'failed')
        self.assertEqual(manager.get(running)['stage'], 'interrupted')
        self.assertEqual(manager.get(previous)['status'], 'completed')
        self.assertEqual(len(manager.list(sid)), 3)

    def test_api_rejects_unknown_task_confirmation_paths_and_foreign_runs(self):
        sid = self.load()
        endpoint = f'/api/series/{sid}/analyses'
        self.assertEqual(self.client.post(endpoint, headers=HEADERS, json={'model_id': 'unknown-task', 'confirmed': True}).status_code, 422)
        self.assertEqual(self.client.post(endpoint, headers=HEADERS, json={'model_id': 'total', 'confirmed': False}).status_code, 422)
        self.assertEqual(self.client.post(endpoint, headers=HEADERS, json={'model_id': 'total', 'confirmed': True, 'path': 'C:/secret'}).status_code, 422)
        self.assertEqual(self.client.post(endpoint, json={'model_id': 'total', 'confirmed': True}).status_code, 403)
        self.assertEqual(self.client.get('/api/analyses/no-such-run/result').status_code, 404)
        self.assertEqual(self.client.get('/api/series/no-such-series/analysis-eligibility').status_code, 404)

    def test_completed_slice_identity_and_row_major_order(self):
        sid = self.load()
        folder, source, _ = self.fixture_output(sid)
        restore_output(folder)
        (folder / 'metrics.json').write_text('{}')
        rid = self.insert(sid, 'completed')
        manager = self.manager()
        manager.directory(rid).parent.mkdir(exist_ok=True)
        folder.rename(manager.directory(rid))
        plane = self.client.get(f'/api/analyses/{rid}/slices/1').json()
        self.assertEqual(plane['labels'], [10, 10, 0, 0])
        self.assertEqual(plane['hu'], [-80, -98, -96, -94])
        self.assertEqual(plane['source_instance']['id'], source['sources'][1]['instance_id'])
        self.assertEqual(self.client.get(f'/api/analyses/{rid}/slices/3').status_code, 422)
        # A mismatched parent-series identity must never be rendered as this run.
        path = manager.directory(rid) / 'result.json'
        foreign = json.loads(path.read_text(encoding='utf-8'))
        foreign['series_id'] = 'different-series'
        path.write_text(json.dumps(foreign), encoding='utf-8')
        self.assertEqual(self.client.get(f'/api/analyses/{rid}/result').status_code, 422)

    def test_runtime_missing_is_not_ready_and_external_network_guard(self):
        self.assertFalse(runtime_status(home=self.root, python=Path(sys.executable))['ready'])
        # A fresh Python process confirms sitecustomize also protects spawn workers.
        code = "import socket; socket.create_connection(('example.com',443),timeout=1)"
        result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=inference_environment(), capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('External DNS disabled', result.stderr)

    def test_completed_surface_cache_and_tampered_labels_are_not_exposed(self):
        sid = self.load()
        folder, source, _ = self.fixture_output(sid)
        restore_output(folder)
        (folder / 'metrics.json').write_text('{}')
        rid = self.insert(sid, 'completed')
        manager = self.manager()
        manager.directory(rid).parent.mkdir(exist_ok=True)
        folder.rename(manager.directory(rid))
        endpoint = f'/api/analyses/{rid}/surfaces'
        response = self.client.get(endpoint)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['run_id'], rid)
        self.assertEqual(len(response.json()['objects']), 1)
        self.assertEqual(response.json(), self.client.get(endpoint).json())
        labels_path = manager.directory(rid) / 'labels.npy'
        labels = np.load(labels_path)
        labels[:] = 0
        np.save(labels_path, labels)
        self.assertEqual(self.client.get(endpoint).status_code, 422)

    def test_cached_candidate_surface_checks_selection_map_integrity(self):
        sid = self.load()
        folder, source, labels = self.fixture_output(sid)
        labels[labels == 10] = 2
        nib.save(nib.Nifti1Image(labels, np.array(source['affine_ras'])), folder / 'prediction.nii.gz')
        result = restore_output(folder, 'lung_nodules')
        (folder / 'metrics.json').write_text('{}')
        rid = self.insert(sid, 'completed')
        with self.store.connect() as c:
            c.execute("UPDATE analysis_runs SET model_id='lung_nodules' WHERE id=?", (rid,))
        manager = self.manager()
        manager.directory(rid).parent.mkdir(exist_ok=True)
        folder.rename(manager.directory(rid))
        endpoint = f'/api/analyses/{rid}/surfaces'
        self.assertEqual(self.client.get(endpoint).status_code, 200)
        path = manager.directory(rid) / 'components.npy'
        components = np.load(path); components[:] = 0; np.save(path, components)
        self.assertEqual(self.client.get(endpoint).status_code, 422)

    def test_execution_failure_is_persisted_not_empty_success(self):
        sid = self.load()
        rid = self.insert(sid, 'queued')
        manager = self.manager()
        with patch('backend.analysis.subprocess.Popen', side_effect=OSError('isolated fake missing runtime')):
            manager.execute(rid)
        run = manager.get(rid)
        self.assertEqual(run['status'], 'failed')
        self.assertTrue(run['error'])
        with self.assertRaises(GeometryError):
            manager.result(rid)

    def test_oom_response_and_cancel_running_owned_process(self):
        sid = self.load()
        manager = self.manager()
        rid = self.insert(sid, 'queued')

        class FailedWorker:
            """Simulate a measured worker failure without exhausting the real GPU."""
            returncode = 1
            def __init__(self, *args, **kwargs):
                (manager.directory(rid) / 'failure.json').write_text('{"code":"out_of_memory"}')
            def poll(self):
                return self.returncode

        with patch('backend.analysis.subprocess.Popen', FailedWorker):
            manager.execute(rid)
        self.assertEqual(manager.get(rid)['status'], 'failed')
        self.assertIn('GPU 메모리', manager.get(rid)['error'])

        rid = self.insert(sid, 'queued')
        class CancelledWorker:
            returncode = None
            def __init__(self, *args, **kwargs):
                manager.cancel(rid)
            def poll(self):
                return self.returncode

        def terminate(process):
            process.returncode = -1

        with patch('backend.analysis.subprocess.Popen', CancelledWorker), patch.object(manager, 'terminate_tree', side_effect=terminate) as stopped:
            manager.execute(rid)
            stopped.assert_called_once()
        self.assertEqual(manager.get(rid)['status'], 'cancelled')

    def test_enqueue_snapshots_and_duplicate_guard(self):
        sid = self.load()
        manager = self.manager()
        runtime = {'ready': True, 'weights_digest': 'synthetic-test-only'}
        with patch.object(manager, 'eligibility', return_value={'eligible': True}), patch('backend.analysis.runtime_status', return_value=runtime), patch.object(manager.pool, 'submit'):
            first = manager.enqueue(sid, True)
            self.assertEqual(first['status'], 'queued')
            self.assertEqual(first['snapshot']['configuration']['report_input'], False)
            with self.assertRaises(GeometryError):
                manager.enqueue(sid, True)
            manager.cancel(first['id'])
            second = manager.enqueue(sid, True)
            self.assertNotEqual(first['id'], second['id'])
            self.assertEqual(len(manager.list(sid)), 2)


if __name__ == '__main__':
    unittest.main()
