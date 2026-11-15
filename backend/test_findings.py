"""Week 4 quantitative and provenance regression using synthetic masks only.

Tolerances fixed before verification: exact component/voxel counts, 1e-4 mm and
mm³ for analytic measurements, 0.002 mm for rounded display-mesh coordinates.
"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import nibabel as nib
import numpy as np

from .analysis import AnalysisManager
from .analysis_runtime import CONFIGURATIONS, runtime_status
from .analysis_volume import affine_ras, eligible, restore_output
from .findings import quantify_findings, axial_feret
from .geometry import GeometryError
from .storage import Store
from .surfaces import surface, build_surfaces


def source_fixture(shape=(8, 8, 8)):
    """Oblique/reversed patient axes and anisotropic spacings expose axis swaps."""
    v = 2 ** -.5
    info = {'shape_xyz': list(shape), 'spacing_xyz': [2., 3., 4.], 'origin': [10., 20., 30.],
            'column_direction': [-v, -v, 0], 'row_direction': [v, -v, 0], 'slice_normal': [0, 0, 1],
            'positions': [[10, 20, 30 + z * 4] for z in range(shape[2])]}
    return {'id': 'synthetic-series', 'study_id': 'synthetic-study', 'geometry': info,
            'affine_ras': affine_ras(info).tolist(), 'sources': [{'instance_id': f'synthetic-{z}'} for z in range(shape[2])]}


class FindingTests(unittest.TestCase):
    def test_feret_uses_full_patient_basis_with_orientation_rounding(self):
        mask = np.ones((2, 1, 1), dtype=bool)
        epsilon = 5e-5
        basis = np.array([[2, 3 * epsilon], [0, 3 * np.sqrt(1 - epsilon ** 2)], [0, 0]])
        measured = axial_feret(mask, basis)
        expected = np.linalg.norm(2 * basis[:, 0] + basis[:, 1])
        self.assertAlmostEqual(measured['diameter_mm'], expected, delta=1e-6)

    def test_separate_nodules_volume_outer_corner_feret_and_representative(self):
        source = source_fixture()
        labels = np.zeros((8, 8, 8), dtype=np.uint8)
        labels[1:3, 1, 2] = 2
        labels[6, 6, 5] = 2
        findings, selections = quantify_findings(labels, source, 'lung_nodules')
        self.assertEqual(len(findings), 2)
        first, second = findings
        self.assertEqual(first['voxel_count'], 2)
        self.assertAlmostEqual(first['volume_mm3'], 48, delta=1e-4)
        self.assertAlmostEqual(first['diameter_mm'], np.sqrt(4 ** 2 + 3 ** 2), delta=1e-4)
        self.assertAlmostEqual(second['diameter_mm'], np.sqrt(2 ** 2 + 3 ** 2), delta=1e-4)
        self.assertIsNone(first['score'])
        self.assertIn('not RECIST', first['diameter_method'])
        for finding in findings:
            index = tuple(finding['representative_index_xyz'])
            self.assertEqual(selections[index], finding['selection_label'])
            lps = (np.diag([-1., -1., 1., 1.]) @ np.array(source['affine_ras']) @ np.r_[index, 1])[:3]
            np.testing.assert_allclose(finding['representative_lps_mm'], lps, atol=1e-4)
            self.assertEqual(finding['source_instance_id'], f'synthetic-{index[2]}')

    def test_26_connectivity_holes_and_largest_axial_plane(self):
        source = source_fixture()
        labels = np.zeros((8, 8, 8), dtype=np.uint8)
        labels[1, 1, 1] = labels[2, 2, 2] = 2  # corner-connected, documented 26-rule
        labels[1:4, 1:4, 3] = 2
        labels[2, 2, 3] = 0  # centre is not a segmented navigation voxel
        findings, selections = quantify_findings(labels, source, 'lung_nodules')
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding['diameter_slice_z'], 3)
        self.assertEqual(labels[tuple(finding['representative_index_xyz'])], 2)
        self.assertAlmostEqual(finding['diameter_mm'], np.hypot(6, 9), delta=1e-4)

    def test_effusions_aggregate_disconnected_regions_without_nodule_semantics(self):
        labels = np.zeros((8, 8, 8), dtype=np.uint8)
        labels[0, 0, 0] = labels[7, 7, 7] = 2
        labels[3, 3, 3] = 3
        findings, selections = quantify_findings(labels, source_fixture(), 'pleural_pericard_effusion')
        self.assertEqual(len(findings), 2)
        self.assertEqual([f['kind'] for f in findings], ['pleural_effusion', 'pericardial_effusion'])
        self.assertEqual(findings[0]['voxel_count'], 2)
        self.assertTrue(findings[0]['touches_boundary'])
        self.assertTrue(all(f['diameter_mm'] is None for f in findings))
        self.assertEqual(selections[0, 0, 0], selections[7, 7, 7])

    def test_empty_candidates_and_task_auxiliary_labels_are_excluded(self):
        source = source_fixture()
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / 'source.json').write_text(json.dumps(source))
            for task, maximum in [('lung_nodules', 2), ('pleural_pericard_effusion', 3)]:
                # Auxiliary label 1 is lung context, never a nodule or effusion.
                labels = np.ones((8, 8, 8), dtype=np.uint8)
                nib.save(nib.Nifti1Image(labels, np.array(source['affine_ras'])), folder / 'prediction.nii.gz')
                result = restore_output(folder, task)
                self.assertEqual(result['finding_status'], 'no_candidates')
                self.assertEqual(result['finding_count'], 0)
                self.assertEqual(np.count_nonzero(np.load(folder / 'labels.npy')), 0)
                labels[0, 0, 0] = maximum + 1
                nib.save(nib.Nifti1Image(labels, np.array(source['affine_ras'])), folder / 'prediction.nii.gz')
                with self.assertRaises(GeometryError):
                    restore_output(folder, task)

    def test_surface_world_transform_bounds_and_candidate_identity(self):
        source = source_fixture()
        labels = np.zeros((8, 8, 8), dtype=np.uint8)
        labels[2:5, 2:6, 1:4] = 2
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / 'source.json').write_text(json.dumps(source))
            nib.save(nib.Nifti1Image(labels, np.array(source['affine_ras'])), folder / 'prediction.nii.gz')
            result = restore_output(folder, 'lung_nodules')
            payload = build_surfaces(np.load(folder / 'labels.npy'), result, np.load(folder / 'components.npy'))
            self.assertEqual(len(payload['objects']), 1)
            obj = payload['objects'][0]
            self.assertEqual(obj['candidate_id'], result['findings'][0]['id'])
            lps = np.array(obj['vertices_lps_mm']).reshape(-1, 3)
            affine = np.diag([-1., -1., 1., 1.]) @ np.array(source['affine_ras'])
            index = (np.linalg.inv(affine) @ np.c_[lps, np.ones(len(lps))].T).T[:, :3]
            np.testing.assert_allclose(index.min(axis=0), [1.5, 1.5, .5], atol=.002)
            np.testing.assert_allclose(index.max(axis=0), [4.5, 5.5, 3.5], atol=.002)
            self.assertTrue(all(i < len(lps) for i in obj['triangles']))
            self.assertIsNone(surface(np.zeros_like(labels), affine))

    def test_model_specific_spacing_limits_and_no_unknown_adapters(self):
        source = source_fixture()
        info = source['geometry']
        self.assertTrue(eligible(info, 'lung_nodules'))  # source Z=4 exceeds initial app limit
        self.assertFalse(eligible(info, 'pleural_pericard_effusion'))
        info['spacing_xyz'] = [2, 3, 2]
        info['positions'] = [[10, 20, 30 + z * 2] for z in range(8)]
        self.assertFalse(eligible(info, 'lung_nodules'))
        self.assertFalse(runtime_status(model_id='unknown-task')['ready'])

    def test_queue_per_model_versions_are_independent_and_weight_changes_fail(self):
        with TemporaryDirectory() as temporary:
            store = Store(Path(temporary)); store.initialize()
            with store.connect() as c:
                c.execute("INSERT INTO studies(id,study_uid) VALUES ('study','uid')")
                c.execute("INSERT INTO series(id,series_uid,study_id,metadata) VALUES ('series','series-uid','study','{}')")
            manager = AnalysisManager(store)
            runtime = {'ready': True, 'weights_digest': 'synthetic-digest'}
            try:
                with patch.object(manager, 'eligibility', return_value={'eligible': True}), patch('backend.analysis.runtime_status', return_value=runtime), patch.object(manager.pool, 'submit'):
                    a = manager.enqueue('series', True, 'lung_nodules')
                    b = manager.enqueue('series', True, 'pleural_pericard_effusion')
                    self.assertEqual(a['model_id'], 'lung_nodules')
                    self.assertEqual(b['snapshot']['configuration'], CONFIGURATIONS['pleural_pericard_effusion'])
                    with self.assertRaises(GeometryError):
                        manager.enqueue('series', True, 'lung_nodules')
                # A queued run must not execute with a silently changed model.
                with patch('backend.analysis.runtime_status', return_value={'ready': True, 'weights_digest': 'different'}):
                    manager.execute(a['id'])
                self.assertEqual(manager.get(a['id'])['status'], 'failed')
                self.assertIn('가중치', manager.get(a['id'])['error'])
                self.assertEqual(manager.get(b['id'])['status'], 'queued')
            finally:
                manager.close()


if __name__ == '__main__':
    unittest.main()
