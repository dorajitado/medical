"""Ephemeral positive workflow UI fixture, never imported by production."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
from .qa_findings_fixture import create_fixture
from .analysis import AnalysisManager
from .analysis_runtime import ROOT,CONFIGURATIONS
from .storage import Store
from .app import create_app

directory=TemporaryDirectory(prefix='ct-remaining-synthetic-');root=Path(directory.name)
fixture=create_fixture(root);store=Store(root);manager=AnalysisManager(store,enabled=False)
try:
    # Copy the known fixture solely to exercise independent scores and manual
    # pairing. It is explicitly NOT a prediction or a clinical performance case.
    result=manager.result(fixture['runs']['lung_nodules']);identifier=str(uuid4());result['model_id']='monai_nodule'
    for index,finding in enumerate(result['findings']):
        finding.update(id=f'synthetic-box-{index}',model_id='monai_nodule',score=.25,volume_mm3=None,volume_ml=None,voxel_count=None,diameter_mm=None,representation='detection_box')
    folder=root/'analysis'/identifier;folder.mkdir();(folder/'result.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8');(folder/'metrics.json').write_text('{}')
    with store.connect() as c:
        study=c.execute('SELECT study_id FROM series WHERE id=?',(fixture['series_id'],)).fetchone()[0]
        c.execute("INSERT INTO analysis_runs(id,series_id,model_id,status,stage,snapshot) VALUES (?,?,'monai_nodule','completed','completed',?)",(identifier,fixture['series_id'],json.dumps({'configuration':CONFIGURATIONS['monai_nodule'],'runtime':{'source':'synthetic_not_model'}})))
        c.execute("INSERT INTO report_versions(id,study_id,source,text) VALUES (?,?,'hospital_transcription',?)",(str(uuid4()),study,'8 mm nodule. No pleural effusion.'))
finally:manager.close()
app=create_app(root,allowed_origins={'http://127.0.0.1:8004'},imaging_path=ROOT/'data'/'qa-imaging'/'orthanc.json',analysis_enabled=False)
