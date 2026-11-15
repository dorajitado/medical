"""Isolated synthetic acceptance tests. None assess clinical model accuracy."""
import hashlib
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4
import zipfile
import numpy as np
from .analysis import AnalysisManager
from .documents import ingest_document,accept_document
from .editorial import validate_order
from .exports import pdf_bytes
from .extended_workflow import ExtendedWorkflow
from .maintenance import create_backup,verify_backup,backup_path,restore_backup,delete_study,managed,cleanup_deleted
from .storage import Store
from .test_workflow import seed_workflow


class RemainingTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.store=Store(Path(self.temp.name)/'workspace');self.study,self.series,self.runs=seed_workflow(self.store)
        self.analysis=AnalysisManager(self.store,enabled=False);self.service=ExtendedWorkflow(self.store,self.analysis)

    def tearDown(self):self.analysis.close();self.temp.cleanup()

    def original(self):
        name=str(uuid4())+'.dcm';data=b'SYNTHETIC ORIGINAL';digest=hashlib.sha256(data).hexdigest()
        (self.store.root/'originals'/name).write_bytes(data)
        with self.store.connect() as c:c.execute('INSERT INTO instances(id,sop_uid,series_id,sha256,stored_name,metadata) VALUES (?,?,?,?,?,?)',(str(uuid4()),str(uuid4()),self.series,digest,name,'{}'))
        return name,data

    def test_backup_restore_preserves_versions_and_recovers_replaced_data(self):
        name,data=self.original();backup=create_backup(self.store);manifest=verify_backup(backup_path(self.store,backup['id']));self.assertTrue(manifest['files'])
        (self.store.root/'originals'/name).write_bytes(b'CHANGED')
        with self.assertRaises(ValueError):restore_backup(self.store,backup['id'],'wrong',False)
        restored=restore_backup(self.store,backup['id'],'RESTORE '+backup['id'],False)
        self.assertEqual((self.store.root/'originals'/name).read_bytes(),data)
        self.assertEqual((self.store.root/'recovery'/restored['recovery_id']/'originals'/name).read_bytes(),b'CHANGED')
        with self.store.connect() as c:self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')

    def test_backup_rejects_tampering_path_escape_and_duplicate_manifest(self):
        backup=create_backup(self.store);path=backup_path(self.store,backup['id']);bad=self.store.root/'bad.zip'
        with zipfile.ZipFile(path) as src,zipfile.ZipFile(bad,'w') as dst:
            for name in src.namelist():dst.writestr(name,b'corrupt' if name=='workspace.sqlite3' else src.read(name))
        with self.assertRaises(ValueError):verify_backup(bad)
        with self.assertRaises(ValueError):managed(self.store.root,self.store.root/'..'/'elsewhere')
        with self.assertRaises(ValueError):delete_study(self.store,self.study,'wrong')

    def test_delete_study_preserves_external_file_and_backups(self):
        external=Path(self.temp.name)/'external-ct.dcm';external.write_bytes(b'EXTERNAL ORIGINAL NEVER IMPORTED')
        name,_=self.original();backup=create_backup(self.store)
        result=delete_study(self.store,self.study,'DELETE '+self.study)
        self.assertEqual(result['status'],'deleted');self.assertFalse((self.store.root/'originals'/name).exists());self.assertTrue(backup_path(self.store,backup['id']).exists())
        with self.store.connect() as c:self.assertEqual(c.execute('SELECT count(*) FROM studies').fetchone()[0],0)
        self.assertEqual(external.read_bytes(),b'EXTERNAL ORIGINAL NEVER IMPORTED')

    def test_precommit_crash_recovers_file_moves_and_postcommit_cleanup_retries(self):
        name,data=self.original();identifier=str(uuid4());trash=self.store.root/'trash'/identifier;trash.mkdir(parents=True)
        (trash/'deletion.json').write_text(json.dumps({'status':'staged','study_id':self.study,'moves':[{'original':'originals/'+name,'saved':'0'}]}))
        (self.store.root/'originals'/name).replace(trash/'0')
        self.store.initialize();self.assertEqual((self.store.root/'originals'/name).read_bytes(),data)
        with patch('backend.maintenance.shutil.rmtree',side_effect=PermissionError('synthetic locked cleanup')):
            result=delete_study(self.store,self.study,'DELETE '+self.study)
        self.assertEqual(result['status'],'cleanup_pending');self.store.initialize()
        result=cleanup_deleted(self.store,result['cleanup_id']);self.assertEqual(result['status'],'deleted')

    def test_delete_locked_file_rolls_back_metadata_and_originals(self):
        name,data=self.original()
        original=Path.replace
        def locked(path,target):
            if path.name==name:raise PermissionError('synthetic locked file')
            return original(path,target)
        with patch.object(Path,'replace',locked),self.assertRaises(PermissionError):delete_study(self.store,self.study,'DELETE '+self.study)
        self.assertEqual((self.store.root/'originals'/name).read_bytes(),data)
        self.assertEqual(self.service.row('studies',self.study)['id'],self.study)

    def test_document_pdf_and_image_ocr_keep_original_and_require_confirmation(self):
        # Generated known text is a fixture, never a fabricated patient report.
        from PIL import Image,ImageDraw,ImageFont
        image=Image.new('RGB',(1400,220),'white');ImageDraw.Draw(image).text((40,50),'RUL 5 mm nodule. 흉수 없음.',font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',48),fill='black')
        output=BytesIO();image.save(output,format='PNG');data=output.getvalue()
        doc=ingest_document(self.store,self.study,data,'image/png');self.assertEqual(doc['status'],'extracted',doc['error']);self.assertIn('5 mm',doc['pages'][0]['text'])
        self.assertEqual(doc['sha256'],hashlib.sha256(data).hexdigest())
        with self.assertRaises(ValueError):accept_document(self.store,doc['id'],'RUL 5 mm',False)
        report=accept_document(self.store,doc['id'],'RUL 5 mm',True);self.assertEqual(report['source'],'document_ocr_unverified')
        snapshot=self.service.summary(self.study,None)['payload'];pdf=pdf_bytes(snapshot)
        from pypdf import PdfReader
        self.assertIn('흉부 CT 검토 정리본',PdfReader(BytesIO(pdf)).pages[0].extract_text())
        document=ingest_document(self.store,self.study,pdf,'application/pdf');self.assertEqual(document['status'],'extracted',document['error'])
        failed=ingest_document(self.store,self.study,b'not a PDF','application/pdf');self.assertEqual(failed['status'],'failed')
        self.assertTrue((self.store.root/'documents'/failed['stored_name']/'original.bin').exists())

    def test_model_comparison_retains_independent_scores_and_rejects_cross_input(self):
        monai=str(uuid4());source=self.analysis.result(self.runs[0]);source['model_id']='monai_nodule';source['findings'][0].update(score=.42,volume_mm3=None,diameter_mm=None)
        folder=self.store.root/'analysis'/monai;folder.mkdir();(folder/'result.json').write_text(json.dumps(source));(folder/'metrics.json').write_text('{}')
        with self.store.connect() as c:c.execute("INSERT INTO analysis_runs(id,series_id,model_id,status,stage,snapshot) VALUES (?,?,'monai_nodule','completed','completed','{}')",(monai,self.series))
        result=self.service.compare_models(self.study,[self.runs[0],monai]);p=result['payload'];self.assertEqual(p['groups'][1][0]['score'],.42);self.assertIsNone(p['groups'][0][0]['score']);self.assertEqual(len(p['edges']),1)
        edge=p['edges'][0];edge.update(state='confirmed',reason='synthetic same center');new=self.service.model_links(result['id'],[edge]);self.assertEqual(new['parent_id'],result['id'])
        source['source']['sources'][0]['sha256']='1'*64;(folder/'result.json').write_text(json.dumps(source))
        with self.assertRaises(ValueError):self.service.compare_models(self.study,[self.runs[0],monai])

    def test_longitudinal_explicit_identity_dates_methods_and_rigid_fit(self):
        prior,series,runs=seed_workflow(self.store)
        with self.store.connect() as c:c.execute("UPDATE studies SET study_date='20250102' WHERE id=?",(prior,))
        old=self.analysis.result(runs[0]);old['findings'][0]['diameter_mm']=3.;(self.store.root/'analysis'/runs[0]/'result.json').write_text(json.dumps(old))
        links=[{'current_ref':self.runs[0]+'/synthetic-nodule-1','prior_ref':runs[0]+'/synthetic-nodule-1','confirmed':True,'reason':'known synthetic lesion'}]
        with self.assertRaises(ValueError):self.service.longitudinal(self.study,prior,self.runs[0],runs[0],links,False,[])
        landmarks=[[[10,0,0],[0,0,0]],[[11,0,0],[1,0,0]],[[10,1,0],[0,1,0]]]
        result=self.service.longitudinal(self.study,prior,self.runs[0],runs[0],links,True,landmarks)['payload']
        self.assertEqual(result['days'],365);self.assertAlmostEqual(result['registration']['rms_mm'],0);np.testing.assert_allclose(np.array(result['registration']['matrix_lps'])[:3,3],[10,0,0],atol=1e-8)
        self.assertEqual(result['links'][0]['changes']['diameter_mm']['percent'],100.)
        old['findings'][0]['diameter_method']='incompatible';(self.store.root/'analysis'/runs[0]/'result.json').write_text(json.dumps(old))
        result=self.service.longitudinal(self.study,prior,self.runs[0],runs[0],links,True,[])['payload'];self.assertIsNone(result['links'][0]['changes']['diameter_mm']['delta'])

    def test_evaluation_preparation_is_not_clinical_pass_and_blocks_leakage(self):
        self.original();self.service.evaluation_case(self.study,'test','','',{'expert_reviewed':False,'counts':{}})
        with self.assertRaises(ValueError):self.service.evaluation_case(self.study,'development','','',{'expert_reviewed':False})
        summary=self.service.evaluation_summary();self.assertEqual(summary['clinical_acceptance'],'not_established');self.assertIsNone(summary['metrics']['test']['nodule']['sensitivity'])
        with self.assertRaises(ValueError):self.service.evaluation_case(self.study,'test','','',{'expert_reviewed':True,'counts':{'nodule':{'tp':1,'fp':0,'fn':0}}})

    def test_editorial_guard_preserves_every_fact_and_rejects_hallucination(self):
        clauses=[{'id':'a','text':'5 mm, no effusion'},{'id':'b','text':'의심, 이전 CT 비교 필요'}]
        self.assertEqual(validate_order(clauses,{'order':['b','a']})[0]['text'],clauses[1]['text'])
        for answer in [{'order':['a','a']},{'order':['a']},{'order':['a','b'],'text':'normal'},{'order':['a','new fact']}]:
            with self.assertRaises(ValueError):validate_order(clauses,answer)
