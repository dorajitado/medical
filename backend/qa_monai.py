"""Actual MONAI smoke test on the public QA source, never the user workspace."""
import json
from pathlib import Path
import time
from fastapi.testclient import TestClient
from .analysis_runtime import ROOT
from .app import create_app

if __name__=='__main__':
    root=(ROOT/'data'/'qa-week3').resolve();evidence=json.loads((root/'last-run.json').read_text(encoding='utf-8'))
    directory=Path(evidence['workspace']).resolve()
    if directory.parent!=root or not directory.name.startswith('workspace-'):raise RuntimeError('Not the public QA workspace')
    headers={'X-Workspace-Request':'1'}
    with TestClient(create_app(directory),base_url='http://127.0.0.1:8000') as client:
        response=client.post(f"/api/series/{evidence['series_id']}/analyses",headers=headers,json={'model_id':'monai_nodule','confirmed':True});response.raise_for_status();rid=response.json()['id']
        previous=None;deadline=time.monotonic()+900
        while time.monotonic()<deadline:
            runs=client.get(f"/api/series/{evidence['series_id']}/analyses").json()['items'];run=next(r for r in runs if r['id']==rid)
            if run['stage']!=previous:print(json.dumps({'run_id':rid,'status':run['status'],'stage':run['stage']}),flush=True);previous=run['stage']
            if run['status'] not in {'queued','running'}:break
            time.sleep(.5)
        if run['status']!='completed':raise RuntimeError(run['error'] or run['status'])
        result=client.get(f'/api/analyses/{rid}/result').json()
        surfaces=client.get(f'/api/analyses/{rid}/surfaces');surfaces.raise_for_status()
        output={'run_id':rid,'model_id':'monai_nodule','finding_count':result['finding_count'],'metrics':result['metrics'],
                'representation':result['representation'],'score_semantics':'class confidence, not malignancy probability','clinical_validation':False}
        target=ROOT/'data'/'qa-remaining';target.mkdir(exist_ok=True)
        (target/'monai-smoke.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
        print(json.dumps(output),flush=True)
