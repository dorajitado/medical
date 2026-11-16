"""Persisted single-GPU analysis queue and completed artifact access.

The manager owns its worker processes and closes them on cancel/shutdown. Work
directories are generated UUIDs below this Store, never arbitrary client paths.
Only completed runs expose artifacts; cancellation cannot publish a late result.
"""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import subprocess
import threading
import time
from uuid import uuid4

import nibabel as nib
import numpy as np

from .analysis_runtime import AI_PYTHON, ROOT, CONFIGURATION, CONFIGURATIONS, inference_environment, runtime_status
from .analysis_volume import convert_source, eligible, source_digest
from .geometry import GeometryError, validate_series
from .workflow import audit

ERRORS = {'out_of_memory': 'GPU 메모리가 부족합니다. 다른 GPU 작업을 종료하고 새 실행을 시도해 주세요.',
          'inference_failed': '모델 실행 또는 출력 검증에 실패했습니다. 정상 결과로 취급하지 않습니다.'}


class AnalysisManager:
    """One executor serializes GPU runs; SQLite serializes enqueue/cancel updates."""

    def __init__(self, store, enabled=True):
        self.store = store
        self.enabled = enabled
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='ct-analysis')
        self.closed = threading.Event()
        # Surface generation can be CPU/memory intensive. Serialize and cache it
        # independently of the single-GPU inference queue, without re-running AI.
        self.surface_lock = threading.Lock()

    def directory(self, run_id):
        if not re.fullmatch(r'[0-9a-f-]{36}', run_id):
            raise KeyError('분석 실행이 없습니다.')
        return self.store.root / 'analysis' / run_id

    def get(self, run_id):
        with self.store.connect() as c:
            row = c.execute('SELECT * FROM analysis_runs WHERE id=?', (run_id,)).fetchone()
        if row is None:
            raise KeyError('분석 실행이 없습니다.')
        result = dict(row)
        result['snapshot'] = json.loads(result['snapshot'])
        return result

    def list(self, series_id):
        with self.store.connect() as c:
            ids = [r[0] for r in c.execute('SELECT id FROM analysis_runs WHERE series_id=? ORDER BY created_at DESC,rowid DESC', (series_id,))]
        return [self.get(rid) for rid in ids]

    def eligibility(self, series_id, model_id='total'):
        if model_id not in CONFIGURATIONS:
            raise GeometryError('지원하지 않는 분석 모델입니다.')
        info, _, _ = validate_series(self.store, series_id)
        reasons = eligible(info, model_id)
        runtime = runtime_status(model_id=model_id)
        if not runtime['ready']:
            reasons.append(runtime['reason'])
        if not self.enabled:
            reasons.append('이 검증 서버에서는 실제 추론 실행을 비활성화했습니다.')
        return {'eligible': not reasons, 'reasons': reasons, 'model_id': model_id, 'configuration': CONFIGURATIONS[model_id],
                'input_scope': '검증된 연속 CT; 일반 조영 CT 지원 대상, CTPA 판정과 무관',
                'anatomical_coverage': 'thoracic series must be confirmed by user; not inferred from contrast tags',
                'validation_status': 'technical_only; clinical_not_evaluated'}

    def enqueue(self, series_id, confirmed, model_id='total', batch_id=None):
        if self.closed.is_set():
            raise GeometryError('분석 서비스가 종료 중입니다. 앱을 다시 실행한 뒤 시도해 주세요.')
        if confirmed is not True:
            raise GeometryError('선택 시리즈와 분석 한계를 확인해 주세요.')
        possible = self.eligibility(series_id, model_id)
        if not possible['eligible']:
            raise GeometryError(' '.join(possible['reasons']))
        runtime = runtime_status(verify=True, model_id=model_id)
        if not runtime['ready']:
            raise GeometryError(runtime['reason'])
        rid = str(uuid4())
        snapshot = {'configuration': CONFIGURATIONS[model_id], 'runtime': runtime}
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if batch_id is not None:
                batch = c.execute('SELECT * FROM integrated_batches WHERE id=?', (batch_id,)).fetchone()
                slot = c.execute('SELECT run_id FROM integrated_batch_models WHERE batch_id=? AND model_id=?', (batch_id, model_id)).fetchone()
                if batch is None or batch['series_id'] != series_id or batch['state'] != 'preparing' or slot is None or slot['run_id'] is not None:
                    raise GeometryError('종합 분석의 시리즈/모델 연결이 유효하지 않습니다.')
                snapshot['batch_source'] = json.loads(batch['plan'])['source']
            if c.execute("SELECT id FROM analysis_runs WHERE series_id=? AND model_id=? AND status IN ('queued','running')", (series_id, model_id)).fetchone():
                raise GeometryError('이 시리즈·모델의 분석이 이미 대기 또는 실행 중입니다.')
            c.execute("INSERT INTO analysis_runs(id,series_id,model_id,status,stage,snapshot) VALUES (?,?,?,'queued','queued',?)",
                      (rid, series_id, model_id, json.dumps(snapshot)))
            if batch_id is not None:
                # A crash cannot leave a run unbound between these two writes.
                c.execute('UPDATE integrated_batch_models SET run_id=? WHERE batch_id=? AND model_id=?', (rid, batch_id, model_id))
            study=c.execute('SELECT study_id FROM series WHERE id=?',(series_id,)).fetchone()[0]
            audit(c,'analysis_queued',rid,study,{'model_id':model_id,'configuration_version':CONFIGURATIONS[model_id]['version']})
        try:
            self.pool.submit(self.execute, rid)
        except RuntimeError as exc:
            self.update(rid, 'failed', 'failed', '분석 작업 실행기를 시작하지 못했습니다. 앱을 다시 실행한 뒤 시도해 주세요.')
            raise GeometryError('분석 작업 실행기를 시작하지 못했습니다.') from exc
        return self.get(rid)

    def cancel(self, run_id):
        self.get(run_id)
        with self.store.connect() as c:
            # Immediately hide results and persist intent, even during conversion.
            c.execute("UPDATE analysis_runs SET cancel_requested=1,status='cancelled',stage='cancelled',finished_at=CURRENT_TIMESTAMP WHERE id=? AND status IN ('queued','running')", (run_id,))
        return self.get(run_id)

    def active(self, rid):
        return not self.closed.is_set() and self.get(rid)['status'] in {'queued', 'running'}

    def update(self, rid, status, stage, error=None):
        with self.store.connect() as c:
            # A cancellation always wins over a worker finishing at the same instant.
            c.execute("UPDATE analysis_runs SET status=?,stage=?,error=?,finished_at=CASE WHEN ? IN ('completed','failed') THEN CURRENT_TIMESTAMP ELSE finished_at END WHERE id=? AND status IN ('queued','running')",
                      (status, stage, error, status, rid))
            if c.execute('SELECT changes()').fetchone()[0]:
                study=c.execute('SELECT s.study_id FROM analysis_runs a JOIN series s ON s.id=a.series_id WHERE a.id=?',(rid,)).fetchone()[0]
                audit(c,'analysis_'+status,rid,study,{'stage':stage})

    @staticmethod
    def terminate_tree(process):
        """Stop only the owned subprocess and its spawned resampling children."""
        if process.poll() is None:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=20)
            process.wait(timeout=20)

    def execute(self, rid):
        process = None
        try:
            if not self.active(rid):
                return
            self.update(rid, 'running', 'converting')
            with self.store.connect() as c:
                c.execute('UPDATE analysis_runs SET started_at=CURRENT_TIMESTAMP WHERE id=?', (rid,))
            folder = self.directory(rid)
            folder.mkdir(parents=True, exist_ok=False)
            run = self.get(rid)
            # Recheck queued weights: installation may have changed while waiting.
            checked = runtime_status(verify=True, model_id=run['model_id'])
            if not checked['ready']:
                raise GeometryError(checked['reason'])
            if checked.get('weights_digest') != run['snapshot'].get('runtime', {}).get('weights_digest'):
                raise GeometryError('대기 중 모델 가중치 식별이 변경되었습니다. 새 실행이 필요합니다.')
            (folder / 'request.json').write_text(json.dumps({'model_id': run['model_id'], 'configuration': run['snapshot']['configuration']}), encoding='utf-8')
            source = convert_source(self.store, run['series_id'], folder, run['model_id'])
            expected = run['snapshot'].get('batch_source')
            if expected and (source_digest(source['sources']) != expected['digest'] or
                             source['geometry']['shape_xyz'] != expected['shape_xyz'] or
                             not np.allclose(source['affine_ras'], expected['affine_ras'], atol=1e-6, rtol=0)):
                raise GeometryError('종합 분석 대기 중 CT 원본/공간 정보가 바뀌었습니다. 현재 CT로 새 분석을 시작해 주세요.')
            if not self.active(rid):
                return
            self.update(rid, 'running', 'inference')
            # Logs contain only managed file paths, no source DICOM demographics.
            with (folder / 'worker.log').open('wb') as log:
                process = subprocess.Popen([str(AI_PYTHON), '-m', 'backend.inference_worker', str(folder.resolve())],
                                           cwd=ROOT, env=inference_environment(), stdout=log, stderr=subprocess.STDOUT,
                                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                while process.poll() is None:
                    if not self.active(rid):
                        self.terminate_tree(process)
                        return
                    time.sleep(.25)
            if not self.active(rid):
                return
            if process.returncode != 0:
                failure = json.loads((folder / 'failure.json').read_text()) if (folder / 'failure.json').exists() else {}
                self.update(rid, 'failed', 'failed', ERRORS.get(failure.get('code'), ERRORS['inference_failed']))
                return
            # Demand both complete restoration and measured execution metrics.
            result = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
            json.loads((folder / 'metrics.json').read_text())
            if result['series_id'] != self.get(rid)['series_id']:
                raise GeometryError('출력의 원본 시리즈가 일치하지 않습니다.')
            self.update(rid, 'completed', 'completed')
        except Exception as exc:
            message = str(exc) if isinstance(exc, GeometryError) else ERRORS['inference_failed']
            self.update(rid, 'failed', 'failed', message)
        finally:
            if process is not None and process.poll() is None:
                self.terminate_tree(process)
            if self.closed.is_set():
                self.update(rid, 'failed', 'interrupted', '앱 종료로 분석이 중단되었습니다.')

    def result(self, rid):
        row = self.get(rid)
        if row['status'] != 'completed':
            raise GeometryError('완료된 분석 결과가 없습니다. 미분석·실패·취소는 정상 판정이 아닙니다.')
        folder = self.directory(rid)
        result = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
        if result['series_id'] != row['series_id']:
            raise GeometryError('결과 시리즈 연결이 일치하지 않습니다.')
        if result.get('model_id', 'total') != row['model_id']:
            raise GeometryError('결과 모델 연결이 일치하지 않습니다.')
        return {**result, 'model_id': row['model_id'], 'run_id': rid, 'snapshot': row['snapshot'],
                'metrics': json.loads((folder / 'metrics.json').read_text())}

    def slice(self, rid, z):
        """Return one exact source-grid plane for client-side windowing/overlay.

        Flat order is row-major YX so canvas index=y*width+x; no left/right flips.
        Include physical corner coordinates instead of hardcoded anatomical labels
        that would be incorrect for oblique/reversed orientations.
        """
        result = self.result(rid)
        if not 0 <= z < result['shape_xyz'][2]:
            raise GeometryError('슬라이스가 분석 범위를 벗어났습니다.')
        folder = self.directory(rid)
        hu = np.asanyarray(nib.load(folder / 'input.nii.gz').dataobj)[:, :, z].T
        labels = np.load(folder / 'labels.npy', mmap_mode='r', allow_pickle=False)[:, :, z].T
        component_path = folder / 'components.npy'
        components = np.load(component_path, mmap_mode='r', allow_pickle=False)[:, :, z].T if component_path.exists() else None
        width, height, _ = result['shape_xyz']
        info = result['source']['geometry']
        from .geometry import patient_point
        return {'width': width, 'height': height, 'z': z,
                'hu': hu.ravel().tolist(), 'labels': labels.ravel().tolist(),
                'components': components.ravel().tolist() if components is not None else None,
                'source_instance': info['instances'][z], 'spacing_xy': info['spacing_xyz'][:2],
                'origin_lps_mm': patient_point(info, 0, 0, z).tolist(),
                'column_direction_lps': info['column_direction'], 'row_direction_lps': info['row_direction']}

    def surfaces(self, rid):
        """Expose surfaces only for a valid completed run and the exact label hash."""
        import hashlib
        from .surfaces import ALGORITHM, build_surfaces
        result = self.result(rid)
        folder = self.directory(rid)
        with self.surface_lock:
            label_hash = hashlib.sha256((folder / 'labels.npy').read_bytes()).hexdigest()
            if label_hash != result['labels_sha256']:
                raise GeometryError('분할 마스크의 해시가 달라졌습니다. 3D를 생성하지 않습니다.')
            component_path = folder / 'components.npy'
            if result.get('components_sha256') and hashlib.sha256(component_path.read_bytes()).hexdigest() != result['components_sha256']:
                raise GeometryError('후보 선택 마스크의 해시가 달라졌습니다.')
            if result.get('boxes_sha256') and hashlib.sha256((folder/'detection-boxes.json').read_bytes()).hexdigest()!=result['boxes_sha256']:
                raise GeometryError('탐지상자 출력의 해시가 달라졌습니다.')
            cache = folder / 'surfaces-v1.json'
            if cache.exists():
                payload = json.loads(cache.read_text(encoding='utf-8'))
                if payload.get('run_id') == rid and payload.get('labels_sha256') == label_hash and payload.get('algorithm') == ALGORITHM:
                    return payload
            labels = np.load(folder / 'labels.npy', mmap_mode='r', allow_pickle=False)
            components = np.load(component_path, mmap_mode='r', allow_pickle=False) if component_path.exists() else None
            payload = {**build_surfaces(labels, result, components), 'run_id': rid, 'series_id': result['series_id'],
                       'model_id': result.get('model_id', 'total'), 'labels_sha256': label_hash}
            temporary = folder / 'surfaces-v1.tmp'
            temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
            temporary.replace(cache)
            return payload

    def close(self):
        self.closed.set()
        self.pool.shutdown(wait=True, cancel_futures=True)
        with self.store.connect() as c:
            c.execute("UPDATE analysis_runs SET status='failed',stage='interrupted',error='앱 종료로 중단되었습니다.',finished_at=CURRENT_TIMESTAMP WHERE status IN ('queued','running')")
