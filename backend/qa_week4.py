"""Run both new adapters on the retained public-example QA workspace only.

This is a technical smoke test of actual inference, not a sensitivity study.
Zero candidates are valid and are never replaced with synthetic predictions.
Positive synthetic UI fixtures are created separately by qa_findings_fixture.
"""
import json
from pathlib import Path
import time

from fastapi.testclient import TestClient
from .analysis_runtime import ROOT
from .app import create_app
from .test_intake import HEADERS


def main():
    qa_root = (ROOT / 'data' / 'qa-week3').resolve()
    evidence = json.loads((qa_root / 'last-run.json').read_text(encoding='utf-8'))
    workspace = Path(evidence['workspace']).resolve()
    if workspace.parent != qa_root or not workspace.name.startswith('workspace-'):
        raise RuntimeError('Not the public-example workspace')
    sid = evidence['series_id']
    jobs = {}
    with TestClient(create_app(workspace), base_url='http://127.0.0.1:8000') as client:
        for task in ['lung_nodules', 'pleural_pericard_effusion']:
            response = client.post(f'/api/series/{sid}/analyses', headers=HEADERS, json={'model_id': task, 'confirmed': True})
            response.raise_for_status()
            jobs[task] = response.json()['id']
        previous = {}
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            runs = {r['id']: r for r in client.get(f'/api/series/{sid}/analyses').json()['items']}
            for task, rid in jobs.items():
                run = runs[rid]
                if previous.get(task) != run['stage']:
                    print(json.dumps({'model': task, 'status': run['status'], 'stage': run['stage']}), flush=True)
                    previous[task] = run['stage']
            if all(runs[rid]['status'] not in {'queued', 'running'} for rid in jobs.values()):
                break
            time.sleep(.5)
        results = {}
        for task, rid in jobs.items():
            if runs[rid]['status'] != 'completed':
                client.post(f'/api/analyses/{rid}/cancel', headers=HEADERS)
                raise RuntimeError(f"{task}: {runs[rid]['status']} {runs[rid]['error']}")
            response = client.get(f'/api/analyses/{rid}/result')
            response.raise_for_status()
            result = response.json()
            meshes = client.get(f'/api/analyses/{rid}/surfaces')
            meshes.raise_for_status()
            results[task] = {'run_id': rid, 'finding_count': result['finding_count'],
                             'finding_status': result['finding_status'], 'metrics': result['metrics'],
                             'surface_objects': len(meshes.json()['objects'])}
        # Anatomical 3D uses a prior real segmentation; do not rerun it just to
        # generate a display artifact. Source-grid quantitative data stay intact.
        mesh = client.get(f"/api/analyses/{evidence['run_id']}/surfaces")
        mesh.raise_for_status()
        output = {**evidence, 'week4_models': results, 'anatomy_surface_objects': len(mesh.json()['objects'])}
        root = ROOT / 'data' / 'qa-week4'
        root.mkdir(exist_ok=True)
        (root / 'last-run.json').write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'models': results, 'anatomy_surface_objects': output['anatomy_surface_objects']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
