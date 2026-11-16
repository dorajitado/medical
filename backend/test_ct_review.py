"""CT-first acceptance with real geometry and isolated known synthetic masks.

No patient CT or genuine image inference is used here. Batch enqueue tests keep
the real persistence path and replace only executor submission/runtime inventory.
"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4
from fastapi.testclient import TestClient
from .analysis import AnalysisManager
from .app import create_app
from .ct_review import CTReview
from .exports import json_bytes, pdf_bytes
from .geometry import GeometryError
from .maintenance import create_backup, delete_study, restore_backup
from .qa_findings_fixture import create_fixture
from .storage import Store

HEADERS = {'X-Workspace-Request': '1'}
READY = {'ready': True, 'reason': None, 'weights_digest': 'synthetic-test-runtime'}


class CTReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fixture = create_fixture(self.root)
        self.store = Store(self.root)
        self.series = self.fixture['series_id']
        self.manager = AnalysisManager(self.store, enabled=False)
        self.service = CTReview(self.store, self.manager)
        self.study = self.service.row('series', self.series)['study_id']

    def tearDown(self):
        self.manager.close()
        self.temp.cleanup()

    def report(self, text='SYNTHETIC private report; not an image model input'):
        identifier = str(uuid4())
        with self.store.connect() as c:
            c.execute("INSERT INTO report_versions(id,study_id,source,text) VALUES (?,?,'hospital_transcription',?)", (identifier, self.study, text))
        return identifier

    def edit_result(self, model, edit):
        path = self.root/'analysis'/self.fixture['runs'][model]/'result.json'
        value = json.loads(path.read_text(encoding='utf-8'))
        edit(value)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def queued_batch(self, models=None):
        self.manager.enabled = True
        with patch('backend.analysis.runtime_status', return_value=READY), patch('backend.ct_review.runtime_status', return_value=READY), patch.object(self.manager.pool, 'submit') as submit:
            batch = self.service.start(self.series, models or ['total', 'lung_nodules', 'pleural_pericard_effusion', 'monai_nodule'], True)
        return batch, submit

    def test_ct_only_review_has_plain_facts_locations_and_no_report_dependency(self):
        view = self.service.view(self.series)
        self.assertEqual(view['proposal_count'], 4)
        self.assertFalse(view['report_context']['enabled'])
        self.assertEqual(view['report_sources'], [])
        nodules = [c for c in view['candidates'] if c['kind']=='nodule']
        self.assertEqual({c['location'] for c in nodules}, {'왼쪽 위폐엽', '오른쪽 위폐엽'})
        for candidate in view['candidates']:
            self.assertIn(candidate['source_instance_id'], [r['id'] for r in self.service.source(self.series)['rows']])
            self.assertIn('AI', candidate['explanation'])
            self.assertIn('후보', candidate['title'])
        self.assertEqual(view['clinical_validation'], 'not_evaluated')
        self.assertIn('미분석', ' '.join(view['limitations']))

    def test_report_opt_in_absent_present_and_opt_out_snapshot_are_independent(self):
        without = self.service.view(self.series, include_report=True)
        self.assertEqual(without['report_context']['status'], 'not_provided')
        marker = 'PRIVATE SYNTHETIC REPORT NEVER INCLUDED UNLESS OPTED IN'
        self.report(marker)
        off = self.service.snapshot(self.series)['payload']
        self.assertNotIn(marker, json_bytes(off).decode())
        on = self.service.snapshot(self.series, include_report=True)['payload']
        self.assertIn(marker, json_bytes(on).decode())
        self.assertEqual(on['integrated_review']['proposal_count'], off['integrated_review']['proposal_count'])
        self.assertEqual(on['integrated_review']['report_context']['status'], 'available_not_compared')

    def test_newest_failed_run_does_not_silently_reuse_older_completed_candidates(self):
        rid = str(uuid4())
        with self.store.connect() as c:
            c.execute("INSERT INTO analysis_runs(id,series_id,model_id,status,stage,snapshot,error) VALUES (?,?,'lung_nodules','failed','failed','{}','synthetic failure')", (rid, self.series))
        view = self.service.view(self.series)
        row = next(c for c in view['coverage'] if c['model_id']=='lung_nodules')
        self.assertEqual(row['status'], 'failed')
        self.assertFalse(any(c['model_id']=='lung_nodules' for c in view['candidates']))
        self.assertEqual(next(m for m in view['modules'] if m['kind']=='nodule')['completed_models'], 0)

    def test_corrupt_measurement_and_source_order_are_not_empty_normal_results(self):
        self.edit_result('lung_nodules', lambda r: r['findings'][0].update(diameter_mm=float('nan')))
        view = self.service.view(self.series)
        self.assertEqual(next(c for c in view['coverage'] if c['model_id']=='lung_nodules')['status'], 'output_error')
        self.assertFalse(any(c['kind']=='nodule' for c in view['candidates']))
        self.edit_result('pleural_pericard_effusion', lambda r: r['source']['sources'].reverse())
        view = self.service.view(self.series)
        self.assertEqual(view['proposal_count'], 0)
        self.assertNotEqual(view['status'], 'available')
        self.assertIn('확인', view['headline'])
        # A valid NPY and matching hash cannot legitimize the wrong source grid.
        import hashlib
        import numpy as np
        anatomy = self.root/'analysis'/self.fixture['runs']['total']/'labels.npy'
        np.save(anatomy, np.zeros((2, 2, 2), dtype=np.uint8))
        self.edit_result('total', lambda r: r.update(labels_sha256=hashlib.sha256(anatomy.read_bytes()).hexdigest()))
        view = self.service.view(self.series)
        self.assertEqual(next(c for c in view['coverage'] if c['model_id']=='total')['status'], 'output_error')

    def test_changed_original_invalidates_geometry_cache(self):
        self.service.view(self.series)
        name = self.service.source(self.series)['rows'][0]['stored_name']
        path = self.root/'originals'/name
        path.write_bytes(path.read_bytes()+b'CORRUPTED')
        with self.assertRaises(GeometryError):
            self.service.view(self.series)

    def test_batch_binds_fixed_source_in_one_queue_without_a_report(self):
        batch, submit = self.queued_batch()
        self.assertEqual(batch['selected_count'], 4)
        self.assertEqual(submit.call_count, 4)
        self.assertEqual(batch['status'], 'running')
        self.assertEqual(len({m['run_id'] for m in batch['models']}), 4)
        for member in batch['models']:
            run = self.manager.get(member['run_id'])
            self.assertEqual(run['snapshot']['batch_source']['digest'], batch['plan']['source']['digest'])
            self.assertNotIn('report', run['snapshot'])
        with self.assertRaises(ValueError):
            self.service.start(self.series, ['total'], True)
        cancelled = self.service.cancel(batch['id'])
        self.assertEqual(cancelled['status'], 'cancelled')
        self.assertEqual(cancelled['completed_count'], 0)
        self.assertEqual(len(self.service.batches(self.series)), 1)

    def test_preparation_failure_is_persisted_and_other_tasks_remain_queued(self):
        self.manager.enabled = True
        real = self.manager.enqueue
        def prepare(series, confirmed, model, batch_id=None):
            if model=='lung_nodules': raise GeometryError('synthetic unavailable at enqueue')
            return real(series, confirmed, model, batch_id=batch_id)
        with patch('backend.analysis.runtime_status', return_value=READY), patch('backend.ct_review.runtime_status', return_value=READY), patch.object(self.manager.pool, 'submit'), patch.object(self.manager, 'enqueue', side_effect=prepare):
            batch = self.service.start(self.series, ['total', 'lung_nodules'], True)
        self.assertEqual({m['status'] for m in batch['models']}, {'queued', 'failed'})
        self.assertTrue(next(m for m in batch['models'] if m['model_id']=='lung_nodules')['issue'])
        view = self.service.view(self.series, batch['id'])
        self.assertEqual(view['proposal_count'], 0)
        self.assertFalse(any(c['run_id']==self.fixture['runs']['lung_nodules'] for c in view['coverage']))

    def test_worker_refuses_input_changed_after_batch_was_queued(self):
        batch, _ = self.queued_batch(['total'])
        rid = batch['models'][0]['run_id']
        changed = {'sources': [{'instance_id': 'different-original', 'sha256': '0'*64}]}
        with patch('backend.analysis.runtime_status', return_value=READY), patch('backend.analysis.convert_source', return_value=changed), patch('backend.analysis.subprocess.Popen') as process:
            self.manager.execute(rid)
        self.assertEqual(self.manager.get(rid)['status'], 'failed')
        self.assertIn('원본', self.manager.get(rid)['error'])
        process.assert_not_called()

    def test_executor_failure_is_recorded_instead_of_a_stuck_queued_batch(self):
        self.manager.enabled = True
        with patch('backend.analysis.runtime_status', return_value=READY), patch('backend.ct_review.runtime_status', return_value=READY), patch.object(self.manager.pool, 'submit', side_effect=RuntimeError('synthetic closed executor')):
            batch = self.service.start(self.series, ['total'], True)
        self.assertEqual(batch['status'], 'failed')
        self.assertEqual(batch['models'][0]['run']['status'], 'failed')
        self.assertEqual(self.service.view(self.series, batch['id'])['status'], 'needs_attention')

    def test_unsupported_model_is_explicit_and_cannot_be_started(self):
        self.manager.enabled = True
        def inventory(*args, model_id='total', **kwargs):
            return {'ready':False,'reason':'synthetic missing optional weights'} if model_id=='monai_nodule' else READY
        with patch('backend.ct_review.runtime_status', side_effect=inventory):
            plan = self.service.plan(self.series)
            self.assertFalse(next(m for m in plan['models'] if m['id']=='monai_nodule')['eligible'])
            view = self.service.view(self.series)
            self.assertEqual(next(m for m in view['coverage'] if m['model_id']=='monai_nodule')['status'], 'not_supported')
            with self.assertRaises(ValueError): self.service.start(self.series, ['monai_nodule'], True)

    def test_optional_document_transcript_keeps_attachment_provenance(self):
        from .documents import accept_document
        identifier = str(uuid4())
        with self.store.connect() as c:
            c.execute("INSERT INTO source_documents(id,study_id,media_type,sha256,stored_name,status,pages) VALUES (?,?,'image/png',?,?,'extracted',?)", (identifier, self.study, '0'*64, identifier, json.dumps([{'page':1,'text':'SYNTHETIC DOCUMENT','method':'synthetic fixture','confidence':None}])))
        report = accept_document(self.store, identifier, 'SYNTHETIC CORRECTED TRANSCRIPT', True)
        on = self.service.snapshot(self.series, include_report=True)['payload']
        self.assertEqual(on['report_sources'][0]['id'], report['id'])
        self.assertEqual(on['report_sources'][0]['document_id'], identifier)
        self.assertEqual(on['source_documents'][0]['sha256'], '0'*64)
        off = self.service.snapshot(self.series)['payload']
        self.assertEqual(off['source_documents'], [])
        self.assertNotIn('SYNTHETIC CORRECTED TRANSCRIPT', json_bytes(off).decode())

    def test_restart_interruption_and_foreign_batch_boundary(self):
        batch, _ = self.queued_batch(['total'])
        self.store.initialize()
        self.assertNotEqual(self.service.batch(batch['id'])['status'], 'completed')
        other = create_fixture(self.root)['series_id']
        with self.assertRaises(ValueError): self.service.view(other, batch['id'])
        with self.assertRaises(ValueError): self.service.start(self.series, ['total'], False)
        with self.assertRaises(ValueError): self.service.start(self.series, ['total', 'total'], True)

    def test_optional_comparison_is_used_only_for_matching_current_run_versions(self):
        rid = self.report('8 mm nodule.')
        extraction = self.service.extract(rid)
        comparison = self.service.compare(extraction['id'], self.series, list(self.fixture['runs'].values()))
        self.assertEqual(self.service.view(self.series, include_report=True, comparison_id=comparison['id'])['report_context']['status'], 'compared')
        with self.store.connect() as c:
            c.execute("INSERT INTO analysis_runs(id,series_id,model_id,status,stage,snapshot) VALUES (?,?,'lung_nodules','cancelled','cancelled','{}')", (str(uuid4()), self.series))
        view = self.service.view(self.series, include_report=True, comparison_id=comparison['id'])
        self.assertEqual(view['report_context']['status'], 'previous_analysis_comparison')
        self.assertIsNone(view['comparison'])
        self.assertEqual(self.service.view(self.series, include_report=False, comparison_id='ignored-invalid-id')['report_sources'], [])

    def test_snapshot_json_pdf_backup_restore_and_delete_batch_links(self):
        batch, _ = self.queued_batch(['total'])
        self.service.cancel(batch['id'])
        snapshot = self.service.snapshot(self.series)
        payload = snapshot['payload']
        self.assertEqual(json.loads(json_bytes(payload))['summary_id'], snapshot['id'])
        self.assertEqual(payload['report_sources'], [])
        from io import BytesIO
        from pypdf import PdfReader
        text = '\n'.join(p.extract_text() for p in PdfReader(BytesIO(pdf_bytes(payload))).pages)
        self.assertIn('CT 종합 검토', text)
        self.assertIn('소견 대조를 사용하지 않습니다', text)
        backup = create_backup(self.store)
        delete_study(self.store, self.study, 'DELETE '+self.study)
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM integrated_batches').fetchone()[0], 0)
        restore_backup(self.store, backup['id'], 'RESTORE '+backup['id'], check_ports=False)
        self.assertEqual(self.service.batch(batch['id'])['status'], 'cancelled')
        self.assertEqual(self.service.row('summary_versions', snapshot['id'])['id'], snapshot['id'])

    def test_api_requires_explicit_scope_and_never_requires_report(self):
        with TestClient(create_app(self.root, analysis_enabled=False), base_url='http://127.0.0.1:8000') as client:
            url=f'/api/series/{self.series}'
            view=client.get(url+'/ct-review').json()
            self.assertFalse(view['report_context']['enabled'])
            saved=client.post(url+'/ct-reviews',headers=HEADERS,json={})
            self.assertEqual(saved.status_code,201,saved.text)
            self.assertEqual(client.post(url+'/ct-batches',json={'model_ids':['total'],'confirmed':True}).status_code,403)
            self.assertEqual(client.post(url+'/ct-batches',headers=HEADERS,json={'model_ids':['total'],'confirmed':False}).status_code,422)
            self.assertEqual(client.post(url+'/ct-batches',headers=HEADERS,json={'model_ids':['unknown'],'confirmed':True,'report':'forged'}).status_code,422)
