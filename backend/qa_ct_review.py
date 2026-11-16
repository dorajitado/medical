"""Actual four-model batch smoke on the retained public example only.

Original patient storage is never opened. Source SHA/path guards are required;
this proves orchestration/traceability, not contrast-CT diagnostic performance.
"""
import hashlib
import json
from pathlib import Path
import time
from fastapi.testclient import TestClient
from .analysis_runtime import ROOT
from .app import create_app


def main():
    base = (ROOT/'data'/'qa-week3').resolve()
    sample = base/'example_ct_sm.nii.gz'
    expected = 'e50c00b2914e2cac0aaee8e7f3b5f57d44d9f21bfd5c0577271c54c0cb49e9fb'
    if hashlib.sha256(sample.read_bytes()).hexdigest() != expected:
        raise RuntimeError('Public reference SHA differs')
    evidence = json.loads((base/'last-run.json').read_text(encoding='utf-8'))
    workspace = Path(evidence['workspace']).resolve()
    if workspace.parent != base or not workspace.name.startswith('workspace-'):
        raise RuntimeError('Not an isolated public-example workspace')
    output = ROOT/'data'/'qa-ct-review'; output.mkdir(exist_ok=True)
    headers = {'X-Workspace-Request': '1'}; started = time.monotonic()
    with TestClient(create_app(workspace), base_url='http://127.0.0.1:8000') as client:
        sid = evidence['series_id']
        response = client.post(f'/api/series/{sid}/ct-batches', headers=headers,
                               json={'model_ids':['total','lung_nodules','pleural_pericard_effusion','monai_nodule'], 'confirmed':True})
        response.raise_for_status(); identifier = response.json()['id']; previous = None
        while time.monotonic()-started < 900:
            batch = client.get(f'/api/ct-batches/{identifier}').json()
            status = [m['status'] for m in batch['models']]
            if status != previous:
                print(json.dumps({'status':batch['status'],'completed':batch['completed_count'],'models':status}), flush=True);previous = status
            if batch['status'] != 'running':break
            time.sleep(.5)
        else:
            client.post(f'/api/ct-batches/{identifier}/cancel', headers=headers, json={});raise RuntimeError('Public batch timed out')
        view_response = client.get(f'/api/series/{sid}/ct-review', params={'batch_id':identifier})
        view_response.raise_for_status();view = view_response.json()
        saved_response = client.post(f'/api/series/{sid}/ct-reviews', headers=headers, json={'batch_id':identifier})
        saved_response.raise_for_status();saved = saved_response.json()
        result = {'batch_id':identifier,'status':batch['status'],'completed':batch['completed_count'],'wall_seconds':time.monotonic()-started,
                  'source_sha256':expected,'review_status':view['status'],'proposal_count':view['proposal_count'],
                  'coverage':[{k:e[k] for k in ['model_id','status','run_id','candidate_count','issue']} for e in view['coverage']],
                  'summary_id':saved['id'],'report_context':view['report_context'],'clinical_evaluation':False,
                  'worker_metrics':{m['model_id']:client.get(f"/api/analyses/{m['run_id']}/result").json().get('metrics') for m in batch['models'] if m['status']=='completed'}}
        (output/'actual-batch.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k:result[k] for k in ['status','completed','wall_seconds','review_status','proposal_count','clinical_evaluation']}), flush=True)
        if batch['status']!='completed' or view['completed_models']!=4 or view['report_context']['enabled']:
            raise RuntimeError('Actual public CT batch/review did not pass')


if __name__=='__main__':main()
