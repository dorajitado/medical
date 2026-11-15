"""Synthetic-only report/comparison/review/export and provenance tests."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from .app import create_app
from .report_parser import extract_report
from .storage import Store

HEADERS={'X-Workspace-Request':'1'}


def seed_workflow(store):
    """Minimal known AI-output fixture, explicitly separate from model accuracy."""
    store.initialize()
    study,series=str(uuid4()),str(uuid4())
    with store.connect() as c:
        c.execute('INSERT INTO studies(id,study_uid,study_date,description) VALUES (?,?,?,?)',(study,str(uuid4()),'20260102','SYNTHETIC WORKFLOW QA'))
        c.execute('INSERT INTO series(id,series_uid,study_id,metadata) VALUES (?,?,?,?)',(series,str(uuid4()),study,'{}'))
    runs=[]
    for model in ['lung_nodules','pleural_pericard_effusion']:
        rid=str(uuid4());folder=store.root/'analysis'/rid;folder.mkdir(parents=True)
        finding={'id':'synthetic-nodule-1','kind':'lung_nodules','title':'합성 후보','label':2,'selection_label':1,'model_id':model,
                 'voxel_count':100,'volume_mm3':100.,'volume_ml':.1,'diameter_mm':6.,'diameter_method':'synthetic known measurement',
                 'representative_index_xyz':[1,1,1],'representative_lps_mm':[10.,20.,30.], 'source_instance_id':'synthetic-instance',
                 'centroid_lps_mm':[10.,20.,30.],'touches_boundary':False,'score':None}
        result={'series_id':series,'study_id':study,'model_id':model,'findings':[finding] if model=='lung_nodules' else [],
                'finding_status':'candidates_present' if model=='lung_nodules' else 'no_candidates',
                'source':{'sources':[{'instance_id':'synthetic-instance','sha256':'0'*64}]},'limitations':['Synthetic fixture, not model prediction']}
        (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8');(folder/'metrics.json').write_text('{}')
        with store.connect() as c:c.execute("INSERT INTO analysis_runs(id,series_id,model_id,status,stage,snapshot) VALUES (?,?,?,'completed','completed','{}')",(rid,series,model))
        runs.append(rid)
    return study,series,runs


class ParserTests(unittest.TestCase):
    def test_negation_uncertainty_stability_prior_units_and_unicode_spans(self):
        text='😀 RUL 0.5 cm nodule, unchanged. No pleural effusion. 심낭삼출은 배제할 수 없음. 이전 CT 4 mm 결절. 3개월 후 추적 권고.'
        items=extract_report(text)
        for item in items:
            span=item['source_span'];self.assertEqual(text[span['start']:span['end']],span['text'])
            self.assertTrue(item['needs_review'])
        nodule=next(i for i in items if i['kind']=='nodule' and i['measurements'][0]['value']==.5)
        self.assertEqual(nodule['measurements'][0]['normalized_value'],5)
        self.assertEqual(nodule['locations'],['RUL'])
        self.assertEqual(next(i for i in items if i['kind']=='pleural_effusion')['presence'],'absent')
        self.assertEqual(next(i for i in items if i['kind']=='pericardial_effusion')['presence'],'uncertain')
        self.assertTrue(any(i['temporal_context']=='prior' for i in items))
        self.assertTrue(any(i['followup_text'] for i in items))

    def test_multiple_lesions_are_preserved_as_ambiguous_not_assigned_randomly(self):
        item=extract_report('RUL 5 mm nodule and LLL 7 mm nodule.')[0]
        self.assertTrue(item['ambiguous']);self.assertEqual(len(item['measurements']),2)
        self.assertEqual(item['locations'],['RUL','LLL'])
        self.assertEqual(extract_report('No interval change in a 5 mm RUL nodule.')[0]['presence'],'mentioned')
        self.assertEqual(extract_report('5 mm nodule without pleural effusion.')[0]['presence'],'mentioned')
        self.assertEqual(extract_report('5 mm nodule without pleural effusion.')[1]['presence'],'absent')


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.directory=TemporaryDirectory();self.root=Path(self.directory.name);self.store=Store(self.root)
        self.study,self.series,self.runs=seed_workflow(self.store)
        self.client=TestClient(create_app(self.root,analysis_enabled=False),base_url='http://127.0.0.1:8000');self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None,None,None);self.directory.cleanup()

    def extraction(self,text='RUL 5 mm nodule. No pleural effusion.'):
        report=self.client.post(f'/api/studies/{self.study}/reports',headers=HEADERS,json={'source':'hospital_transcription','text':text}).json()['id']
        extraction=self.client.post(f'/api/reports/{report}/extract',headers=HEADERS,json={}).json()
        for item in extraction['items']:item['confirmation']='confirmed';item['needs_review']=False
        return self.client.put(f"/api/extractions/{extraction['id']}",headers=HEADERS,json={'items':extraction['items']}).json()

    def comparison(self):
        extraction=self.extraction()
        response=self.client.post('/api/comparisons',headers=HEADERS,json={'extraction_id':extraction['id'],'series_id':self.series,'run_ids':self.runs})
        self.assertEqual(response.status_code,201,response.text)
        return extraction,response.json()

    def test_extraction_corrections_keep_original_and_reject_forged_spans(self):
        extraction=self.extraction()
        self.assertEqual(extraction['origin'],'user_correction')
        history=self.client.get(f'/api/studies/{self.study}/extractions').json()['items']
        self.assertEqual(len(history),2)
        items=extraction['items'];items[0]['source_span']['text']='forged quote'
        response=self.client.put(f"/api/extractions/{extraction['id']}",headers=HEADERS,json={'items':items})
        self.assertEqual(response.status_code,422)
        self.assertEqual(self.client.put(f"/api/extractions/{history[1]['id']}",headers=HEADERS,json={'items':history[1]['items']}).status_code,422)
        reports=self.client.get(f'/api/studies/{self.study}/reports').json()['items']
        self.assertEqual(reports[0]['text'],'RUL 5 mm nodule. No pleural effusion.')

    def test_proposals_confirmation_measurement_difference_and_restored_review(self):
        _,comparison=self.comparison();payload=comparison['payload']
        self.assertEqual(payload['report_counts']['candidate'],1)
        self.assertEqual(payload['report_counts']['not_comparable'],1)
        self.assertEqual(payload['edges'][0]['state'],'proposed')
        edge=payload['edges'][0];edge['state']='confirmed';edge['reason']='합성 위치/종류를 직접 확인'
        update=self.client.put(f"/api/comparisons/{comparison['id']}/links",headers=HEADERS,json={'edges':[edge]}).json()
        self.assertEqual(update['payload']['report_counts']['confirmed'],1)
        delta=update['payload']['edges'][0]['measurement_comparison']
        self.assertEqual(delta['difference'],1.)
        self.assertIn('NOT growth',delta['interpretation'])
        review={'target_type':'finding','target_id':edge['candidate_ref'],'decision':'deferred','note':'합성 검토 메모','question':'이 측정법 차이는?'}
        self.assertEqual(self.client.post(f'/api/studies/{self.study}/reviews',headers=HEADERS,json=review).status_code,201)
        with TestClient(create_app(self.root,analysis_enabled=False),base_url='http://127.0.0.1:8000') as restarted:
            self.assertEqual(restarted.get(f'/api/studies/{self.study}/reviews').json()['items'][0]['note'],'합성 검토 메모')
            self.assertEqual(len(restarted.get(f'/api/studies/{self.study}/comparisons').json()['items']),2)

    def test_unanalysed_is_not_normal_and_cross_study_or_negative_link_is_rejected(self):
        extraction=self.extraction('의심 결절 5 mm. 흉수 관찰되지 않음.')
        response=self.client.post('/api/comparisons',headers=HEADERS,json={'extraction_id':extraction['id'],'series_id':self.series,'run_ids':[self.runs[1]]})
        comparison=response.json();self.assertEqual(comparison['payload']['report_counts']['not_comparable'],2)
        self.assertEqual(comparison['payload']['report_counts']['report_only'],0)
        other,series,_=seed_workflow(self.store)
        self.assertEqual(self.client.post('/api/comparisons',headers=HEADERS,json={'extraction_id':extraction['id'],'series_id':series,'run_ids':self.runs}).status_code,422)
        _,comparison=self.comparison();negative=next(i for i in comparison['payload']['items'] if i['presence']=='absent')
        edge={**comparison['payload']['edges'][0],'report_item_id':negative['id'],'state':'confirmed','reason':'invalid negative link'}
        self.assertEqual(self.client.put(f"/api/comparisons/{comparison['id']}/links",headers=HEADERS,json={'edges':[edge]}).status_code,422)

    def test_json_snapshot_and_source_trace_are_immutable_after_review_change(self):
        _,comparison=self.comparison()
        summary=self.client.post(f'/api/studies/{self.study}/summaries',headers=HEADERS,json={'comparison_id':comparison['id']}).json()
        before=self.client.get(f"/api/summaries/{summary['id']}/export/json").json()
        self.assertEqual(before['report_sources'][0]['source'],'hospital_transcription')
        self.assertTrue(before['comparison']['payload']['candidates'][0]['source_instance_id'])
        self.client.post(f'/api/studies/{self.study}/reviews',headers=HEADERS,json={'target_type':'study','target_id':self.study,'decision':'deferred','note':'later','question':''})
        self.assertEqual(before,self.client.get(f"/api/summaries/{summary['id']}/export/json").json())
        actions=[r['action'] for r in self.client.get(f'/api/studies/{self.study}/audit').json()['items']]
        self.assertIn('summary_exported',actions);self.assertIn('extraction_corrected',actions)
