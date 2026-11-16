"""CT-first orchestration and source-linked, deterministic Korean review.

Reports are optional context and never image-model inputs. Candidate counts
are proposals (possibly duplicated across detectors), not diagnosed lesions.
No severity, malignancy probability, treatment or unanalysed normal is inferred.
"""
import hashlib
import json
import math
import threading
from datetime import datetime, timezone
from uuid import uuid4

import numpy as np
from .analysis_runtime import CONFIGURATIONS, runtime_status
from .analysis_volume import affine_ras, eligible, source_digest
from .geometry import GeometryError, source_path, validate_series
from .workflow import Workflow, audit

MODELS = {
    'total': ('구조와 위치 파악', '폐엽·기관·심장·대동맥의 위치 표시용 분할'),
    'lung_nodules': ('결절 의심 부위 찾기', '영역 분할과 계산 가능한 너비·부피'),
    'pleural_pericard_effusion': ('폐·심장 주위 액체 후보 찾기', '흉수·심낭삼출로 분류된 영역'),
    'monai_nodule': ('결절 의심 부위 추가 확인', '독립 모델의 위치 상자, 분할 크기·부피 없음'),
}
KINDS = {
    'nodule': {'title': '결절 후보', 'explanation': 'AI가 폐의 작은 점처럼 보이는 부위를 결절 후보로 표시했습니다. 실제 결절인지는 해당 CT에서 확인해야 합니다.',
               'source': 'https://site.thoracic.org/advocacy-patients/patient-resources/what-is-a-lung-nodule'},
    'pleural_effusion': {'title': '폐 주위 액체 후보', 'explanation': '폐를 둘러싼 공간의 액체로 AI가 분류한 영역입니다. 종류별 합산 범위이며 원본 CT 확인이 필요합니다.',
                        'source': 'https://www.nhlbi.nih.gov/health/pleural-disorders'},
    'pericardial_effusion': {'title': '심장 주위 액체 후보', 'explanation': '심장을 둘러싼 공간의 액체로 AI가 분류한 영역입니다. 원본 CT 확인이 필요합니다.',
                           'source': 'https://www.cancer.gov/publications/dictionaries/cancer-terms/def/pericardial-effusion'},
}
KIND_MODELS = {'nodule': ['lung_nodules', 'monai_nodule'],
               'pleural_effusion': ['pleural_pericard_effusion'], 'pericardial_effusion': ['pleural_pericard_effusion']}
LOCATIONS = {10: '왼쪽 위폐엽', 11: '왼쪽 아래폐엽', 12: '오른쪽 위폐엽', 13: '오른쪽 중간폐엽', 14: '오른쪽 아래폐엽'}
STATUS = {'completed': '분석 완료', 'queued': '순서 대기', 'running': '분석 중', 'failed': '분석 실패',
          'cancelled': '취소됨', 'not_analysed': '아직 분석하지 않음', 'not_selected': '이번 분석 범위에서 제외',
          'not_supported': '현재 분석할 수 없음', 'preparing': '실행 준비 중', 'output_error': '결과 확인 실패'}
LIMITATIONS = ['AI가 표시한 확인 후보이며 확정 판독이 아닙니다. 진료 적용 성능은 아직 검증되지 않았습니다.',
               '미분석·실패·미지원·후보 없음은 정상 판정이나 질환 배제가 아닙니다.',
               '현재 범위는 위치용 구조 분할·결절 후보·흉수/심낭삼출 후보입니다. 폐색전·기흉·폐실질 이상·림프절 등 추가 소견은 이 종합 검토로 평가하지 않습니다.',
               '모델 간 중복 가능한 제안 수이며 확정 병변 수가 아닙니다. 모델 점수는 독립적이고 악성 확률로 변환하지 않습니다.']


def number(value, nullable=True):
    """Reject corrupt/non-finite/bool measurements instead of filling in zero."""
    if value is None and nullable:
        return None
    if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
        raise ValueError('결과의 측정값이 유효하지 않습니다.')
    return value


class CTReview(Workflow):
    def __init__(self, store, analysis):
        super().__init__(store, analysis)
        self._cache = {}
        self._lock = threading.RLock()

    def source(self, series_id):
        """Validate originals once per file/DB signature, not on every job poll.

        Changed sizes/mtime/metadata invalidate the bounded cache. Original SHA,
        geometry and pixels are then checked by the existing DICOM validator.
        """
        with self.store.connect() as c:
            if c.execute("SELECT 1 FROM import_jobs WHERE status='running'").fetchone():
                raise GeometryError('CT 파일 등록이 진행 중입니다. 등록 완료 후 다시 확인해 주세요.')
            rows = [dict(r) for r in c.execute('SELECT * FROM instances WHERE series_id=? ORDER BY id', (series_id,))]
        if not rows:
            self.row('series', series_id)
            raise GeometryError('이 시리즈에 CT 영상이 없습니다.')
        signature = []
        for row in rows:
            stat = source_path(self.store, row['stored_name']).stat()
            signature.append((row['id'], row['sha256'], row['metadata'], stat.st_size, stat.st_mtime_ns))
        with self._lock:
            old = self._cache.get(series_id)
            if old and old[0] == signature:
                return old[1]
            info, ordered, _ = validate_series(self.store, series_id)
            result = {'info': info, 'rows': [dict(r) for r in ordered], 'digest': source_digest(ordered),
                      'shape_xyz': info['shape_xyz'], 'affine_ras': affine_ras(info).tolist()}
            if len(self._cache) >= 8:
                self._cache.pop(next(iter(self._cache)))
            self._cache[series_id] = (signature, result)
            return result

    def plan(self, series_id):
        source = self.source(series_id)
        series = self.row('series', series_id)
        history = self.analysis.list(series_id)
        models = []
        for model, (title, purpose) in MODELS.items():
            reasons = list(eligible(source['info'], model))
            runtime = runtime_status(model_id=model)
            if not runtime['ready']:
                reasons.append(runtime['reason'])
            if not self.analysis.enabled:
                reasons.append('이 검증 서버에서는 실제 모델 실행을 비활성화했습니다.')
            if any(r['model_id'] == model and r['status'] in {'queued', 'running'} for r in history):
                reasons.append('이 시리즈의 해당 분석이 이미 진행 중입니다.')
            models.append({'id': model, 'title': title, 'purpose': purpose, 'eligible': not reasons, 'reasons': reasons,
                           'configuration_version': CONFIGURATIONS[model]['version']})
        return {'series_id': series_id, 'study_id': series['study_id'], 'source': {k: source[k] for k in ['digest', 'shape_xyz', 'affine_ras']},
                'models': models, 'limitations': LIMITATIONS, 'report_required': False}

    def start(self, series_id, model_ids, confirmed):
        if confirmed is not True:
            raise ValueError('선택한 CT 시리즈와 분석 범위를 확인해 주세요.')
        if not model_ids or len(model_ids) > len(MODELS) or len(set(model_ids)) != len(model_ids) or any(m not in MODELS for m in model_ids):
            raise ValueError('지원하는 분석을 중복 없이 선택해 주세요.')
        plan = self.plan(series_id)
        selected = [m for m in plan['models'] if m['id'] in model_ids]
        if any(not m['eligible'] for m in selected):
            raise ValueError('실행할 수 없는 분석이 포함되어 있습니다. 분석 범위와 사유를 다시 확인해 주세요.')
        identifier = str(uuid4())
        plan['selected_models'] = [m['id'] for m in selected]
        with self.store.connect() as c:
            # Reject a duplicate CT batch even if its first run already finished.
            active = c.execute("SELECT 1 FROM integrated_batches b LEFT JOIN integrated_batch_models m ON m.batch_id=b.id LEFT JOIN analysis_runs a ON a.id=m.run_id WHERE b.series_id=? AND (b.state='preparing' OR a.status IN ('queued','running'))", (series_id,)).fetchone()
            if active:
                raise ValueError('이 CT의 종합 분석이 이미 진행 중입니다.')
            c.execute("INSERT INTO integrated_batches(id,series_id,state,plan) VALUES (?,?,'preparing',?)", (identifier, series_id, json.dumps(plan, ensure_ascii=False)))
            for model in plan['selected_models']:
                c.execute('INSERT INTO integrated_batch_models(batch_id,model_id) VALUES (?,?)', (identifier, model))
            audit(c, 'ct_batch_created', identifier, plan['study_id'], {'series_id': series_id, 'models': plan['selected_models'], 'source_digest': plan['source']['digest']})
        # Each enqueue commits its run/member relationship atomically. A single
        # failed preparation is recorded while other selected tasks remain usable.
        for model in plan['selected_models']:
            try:
                self.analysis.enqueue(series_id, True, model, batch_id=identifier)
            except (ValueError, GeometryError, OSError):
                with self.store.connect() as c:
                    c.execute('UPDATE integrated_batch_models SET issue=? WHERE batch_id=? AND model_id=? AND run_id IS NULL', ('분석 준비에 실패했습니다. 현재 상태/입력과 모델 준비를 확인해 주세요.', identifier, model))
        with self.store.connect() as c:
            c.execute("UPDATE integrated_batches SET state='submitted' WHERE id=?", (identifier,))
        return self.batch(identifier)

    def batch(self, identifier):
        batch = self.row('integrated_batches', identifier)
        batch['plan'] = json.loads(batch['plan'])
        with self.store.connect() as c:
            members = [dict(r) for r in c.execute('SELECT * FROM integrated_batch_models WHERE batch_id=?', (identifier,))]
        order = {model: index for index, model in enumerate(batch['plan']['selected_models'])}
        members.sort(key=lambda member: order.get(member['model_id'], len(order)))
        for member in members:
            run = self.analysis.get(member['run_id']) if member['run_id'] else None
            member['run'] = run
            member['status'] = run['status'] if run else 'preparing' if batch['state'] == 'preparing' else 'cancelled' if batch['state'] == 'cancelled' else 'failed'
        states = [m['status'] for m in members]
        batch['models'] = members
        batch['completed_count'] = states.count('completed')
        batch['selected_count'] = len(states)
        batch['status'] = ('running' if any(s in {'preparing', 'queued', 'running'} for s in states) else
                           'completed' if states and all(s == 'completed' for s in states) else
                           'partial' if 'completed' in states else 'cancelled' if states and all(s == 'cancelled' for s in states) else
                           'interrupted' if batch['state'] == 'interrupted' else 'failed')
        return batch

    def batches(self, series_id):
        self.row('series', series_id)
        with self.store.connect() as c:
            ids = [r[0] for r in c.execute('SELECT id FROM integrated_batches WHERE series_id=? ORDER BY created_at DESC,rowid DESC', (series_id,))]
        return [self.batch(i) for i in ids]

    def cancel(self, identifier):
        batch = self.batch(identifier)
        for member in batch['models']:
            if member['run_id'] and member['status'] in {'queued', 'running'}:
                self.analysis.cancel(member['run_id'])
        study = self.row('series', batch['series_id'])['study_id']
        with self.store.connect() as c:
            c.execute("UPDATE integrated_batches SET state='cancelled' WHERE id=?", (identifier,))
            c.execute("UPDATE integrated_batch_models SET issue='실행 준비 전 취소했습니다.' WHERE batch_id=? AND run_id IS NULL", (identifier,))
            audit(c, 'ct_batch_cancel_requested', identifier, study)
        return self.batch(identifier)

    def _candidate(self, run, result, finding, source, reviews):
        """Validate one actual proposal and render plain, provenance-bound facts."""
        kind = 'nodule' if finding['kind'] == 'lung_nodules' else finding['kind']
        allowed = {'lung_nodules': {'nodule'}, 'monai_nodule': {'nodule'}, 'pleural_pericard_effusion': {'pleural_effusion', 'pericardial_effusion'}}
        if kind not in allowed.get(run['model_id'], set()):
            raise ValueError('모델과 후보 종류가 일치하지 않습니다.')
        index = finding['representative_index_xyz']
        point = finding['representative_lps_mm']
        if len(index) != 3 or any(type(i) is not int or not 0 <= i < n for i, n in zip(index, source['shape_xyz'])):
            raise ValueError('후보의 CT 위치가 유효하지 않습니다.')
        if len(point) != 3 or any(type(v) not in {int, float} or not math.isfinite(v) for v in point):
            raise ValueError('후보의 환자 좌표가 유효하지 않습니다.')
        expected = (np.diag([-1., -1., 1., 1.]) @ np.array(source['affine_ras']) @ [*index, 1])[:3]
        if not np.allclose(point, expected, atol=1e-3, rtol=0) or finding['source_instance_id'] != result['source']['sources'][index[2]]['instance_id']:
            raise ValueError('후보 위치와 원본 영상 연결이 일치하지 않습니다.')
        diameter = number(finding.get('diameter_mm'))
        volume = number(finding.get('volume_mm3'))
        score = number(finding.get('score'))
        if score is not None and score > 1:
            raise ValueError('모델 점수 범위가 유효하지 않습니다.')
        bounds = finding.get('bounds_index_xyz')
        if bounds is not None and (not isinstance(bounds, list) or len(bounds) != 2 or
                                   any(not isinstance(v, list) or len(v) != 3 for v in bounds) or
                                   any(type(v) not in {int, float} or not math.isfinite(v) for corner in bounds for v in corner) or
                                   any(not 0 <= bounds[0][i] <= bounds[1][i] < source['shape_xyz'][i] for i in range(3))):
            raise ValueError('후보 표시 범위가 유효하지 않습니다.')
        if run['model_id'] == 'monai_nodule' and (diameter is not None or volume is not None):
            raise ValueError('탐지상자의 크기를 분할 장경/부피로 사용할 수 없습니다.')
        reference = run['id'] + '/' + finding['id']
        return {'ref': reference, 'run_id': run['id'], 'finding_id': finding['id'], 'model_id': run['model_id'],
                'model_title': MODELS[run['model_id']][0], 'kind': kind, 'title': KINDS[kind]['title'],
                'explanation': KINDS[kind]['explanation'], 'glossary_source': KINDS[kind]['source'],
                'location': '폐 안 세부 위치 확인 전' if kind == 'nodule' else '폐 주위로 분류된 영역' if kind == 'pleural_effusion' else '심장 주위로 분류된 영역',
                'location_basis': '모델이 분류한 종류; 세부 해부학 위치 미확인',
                'diameter_mm': diameter, 'diameter_method': finding.get('diameter_method'),
                'volume_mm3': volume, 'volume_ml': volume / 1000 if volume is not None else None,
                'measurement_text': '크기 측정 없이 위치 상자만 제공' if run['model_id'] == 'monai_nodule' else
                                    f'한 단면에서 계산한 최대 너비 {diameter:.2f} mm' if diameter is not None else
                                    f'분류된 액체 영역 합계 {volume / 1000:.2f} mL' if volume is not None else '측정값 제공 없음',
                'score': score, 'score_meaning': finding.get('score_meaning', 'not provided'),
                'representative_index_xyz': index, 'representative_lps_mm': point, 'source_instance_id': finding['source_instance_id'],
                'slice_number': index[2] + 1, 'slice_count': source['shape_xyz'][2],
                'touches_boundary': bool(finding.get('touches_boundary')), 'bounds_index_xyz': bounds,
                'user_review': reviews.get(reference), 'related_proposals': []}

    def view(self, series_id, batch_id=None, include_report=False, comparison_id=None):
        source = self.source(series_id)
        series = self.row('series', series_id)
        study = self.row('studies', series['study_id'])
        history = self.analysis.list(series_id)
        batch = self.batch(batch_id) if batch_id else None
        if batch and batch['series_id'] != series_id:
            raise ValueError('다른 CT 시리즈의 종합 분석입니다.')
        slots = {m['model_id']: m for m in batch['models']} if batch else {}
        with self.store.connect() as c:
            review_rows = [dict(r) for r in c.execute("SELECT * FROM review_versions WHERE study_id=? AND target_type='finding' ORDER BY created_at DESC,rowid DESC", (study['id'],))]
        reviews = {}
        for row in review_rows:
            reviews.setdefault(row['target_id'], row)
        coverage, candidates, outputs, selected_runs = [], [], {}, []
        for model, (title, purpose) in MODELS.items():
            run = slots.get(model, {}).get('run') if batch else next((r for r in history if r['model_id'] == model), None)
            if run and (run['series_id'] != series_id or run['model_id'] != model):
                raise ValueError('종합 분석에 다른 CT/모델의 실행이 연결되어 있습니다.')
            state = run['status'] if run else slots.get(model, {}).get('status', 'not_selected' if batch else 'not_analysed')
            entry = {'model_id': model, 'title': title, 'purpose': purpose, 'status': state, 'run_id': run['id'] if run else None,
                     'candidate_count': None, 'issue': run.get('error') if run else slots.get(model, {}).get('issue'), 'configuration': run['snapshot'].get('configuration') if run else None}
            if run:
                selected_runs.append(run)
            if state == 'completed':
                try:
                    result = self.analysis.result(run['id'])
                    if (source_digest(result['source']['sources']) != source['digest'] or result['source']['geometry']['shape_xyz'] != source['shape_xyz'] or
                            [s['instance_id'] for s in result['source']['sources']] != [s['id'] for s in source['rows']] or
                            not np.allclose(result['source']['affine_ras'], source['affine_ras'], atol=1e-6, rtol=0)):
                        raise ValueError('원본 목록/공간이 다른 결과입니다.')
                    # Build into a temporary list: one malformed proposal cannot
                    # publish a half-valid model as a successfully empty result.
                    items = [self._candidate(run, result, f, source, reviews) for f in result.get('findings', [])]
                    if result.get('finding_count', len(items)) != len(items) or len({i['ref'] for i in items}) != len(items):
                        raise ValueError('후보 목록/개수가 일치하지 않습니다.')
                    outputs[model] = result
                    candidates.extend(items)
                    entry['candidate_count'] = len(items)
                    entry['limitations'] = result.get('limitations', [])
                except (KeyError, ValueError, TypeError, IndexError, OSError):
                    entry.update(status='output_error', issue='결과의 원본·위치·측정 정보를 확인하지 못했습니다. 이 모델의 후보는 요약에서 제외했습니다.')
            if not run and state in {'not_analysed', 'not_selected'}:
                reasons = eligible(source['info'], model)
                runtime = runtime_status(model_id=model)
                if not runtime['ready']:
                    reasons.append(runtime['reason'])
                if reasons:
                    entry.update(status='not_supported', issue=' '.join(reasons))
            entry['status_text'] = STATUS[entry['status']]
            coverage.append(entry)
        # A same-input anatomy map can explain nodule location; a coordinate sign
        # alone cannot establish left/right. An unreadable mask changes no finding.
        anatomy = outputs.get('total')
        if anatomy:
            try:
                path = self.analysis.directory(anatomy['run_id']) / 'labels.npy'
                if hashlib.sha256(path.read_bytes()).hexdigest() != anatomy['labels_sha256']:
                    raise ValueError('Anatomy label hash mismatch')
                labels = np.load(path, mmap_mode='r', allow_pickle=False)
                # A readable, correctly hashed file still needs the original
                # grid shape before it can supply an anatomical location.
                if labels.shape != tuple(source['shape_xyz']):
                    raise ValueError('Anatomy grid shape mismatch')
                for candidate in candidates:
                    if candidate['kind'] == 'nodule':
                        location = LOCATIONS.get(int(labels[tuple(candidate['representative_index_xyz'])]))
                        if location:
                            candidate.update(location=location, location_basis='같은 CT의 해부학 분할에서 대표점 위치 추정')
            except (KeyError, ValueError, IndexError, OSError):
                for entry in coverage:
                    if entry['model_id'] == 'total':
                        entry.update(status='output_error', status_text=STATUS['output_error'], candidate_count=None, issue='해부학 위치 지도를 확인할 수 없어 세부 위치 추정을 사용하지 않았습니다.')
        for left in candidates:
            for right in candidates:
                if left['model_id'] == right['model_id'] or left['kind'] != 'nodule' or right['kind'] != 'nodule':
                    continue
                a, b = left.get('bounds_index_xyz'), right.get('bounds_index_xyz')
                if a and b:
                    overlap = np.all(np.maximum(a[0], b[0]) <= np.minimum(a[1], b[1]))
                    distance = np.linalg.norm(np.array(left['representative_lps_mm']) - right['representative_lps_mm'])
                    if overlap and distance <= 10:
                        left['related_proposals'].append(right['ref'])
        modules = []
        by_model = {e['model_id']: e for e in coverage}
        for kind, info in KINDS.items():
            entries = [by_model[m] for m in KIND_MODELS[kind]]
            complete = sum(e['status'] == 'completed' for e in entries)
            items = [c for c in candidates if c['kind'] == kind]
            text = f"확인할 {info['title']} 제안 {len(items)}건" if items else '실행한 분석에서 표시된 후보 없음' if complete else '이 항목의 완료된 분석 없음'
            modules.append({'kind': kind, 'title': info['title'], 'proposal_count': len(items), 'completed_models': complete,
                            'available_models': len(entries), 'text': text, 'coverage_complete': complete == len(entries)})
        incomplete = [e for e in coverage if e['status'] != 'completed']
        completed = sum(e['status'] == 'completed' for e in coverage)
        processing = any(e['status'] in {'queued', 'running', 'preparing'} for e in coverage)
        errors = any(e['status'] in {'failed', 'cancelled', 'output_error'} for e in coverage)
        valid_models = {e['model_id'] for e in coverage if e['status'] == 'completed'}
        report_context, reports, comparison = self.report_context(study['id'], series_id, [r for r in selected_runs if r['model_id'] in valid_models], include_report, comparison_id)
        return {'schema_version': 'ct-integrated-review-1', 'generated_at': datetime.now(timezone.utc).isoformat(),
                'study': {k: study[k] for k in ['id', 'study_date', 'description']}, 'series_id': series_id,
                'source': {k: source[k] for k in ['digest', 'shape_xyz', 'affine_ras']}, 'batch_id': batch_id,
                'status': 'processing' if processing else 'partial' if completed and incomplete else 'available' if completed else 'needs_attention' if errors else 'not_analysed',
                'headline': f'CT에서 확인할 AI 후보 제안 {len(candidates)}건' if candidates else
                            'CT 분석이 진행 중입니다' if processing else
                            '실행한 분석에서 표시된 후보가 없습니다' if completed and any(e['model_id'] != 'total' and e['status'] == 'completed' for e in coverage) else
                            '분석을 마치지 못한 항목을 확인해 주세요' if errors else '위치 구조 분석만 완료했습니다' if completed else
                            'CT를 분석하면 확인할 후보가 여기에 표시됩니다',
                'proposal_count': len(candidates), 'unreviewed_count': sum(not c['user_review'] or c['user_review']['decision'] in {'not_reviewed', 'deferred'} for c in candidates),
                'completed_models': completed, 'coverage': coverage, 'modules': modules, 'candidates': candidates,
                'report_context': report_context, 'report_sources': reports, 'comparison': comparison,
                'analysis_runs': selected_runs, 'limitations': LIMITATIONS, 'clinical_validation': 'not_evaluated'}

    def report_context(self, study_id, series_id, runs, enabled, comparison_id):
        """Opt-out does not read/attach reports; opt-in without a report is valid."""
        if not enabled:
            return {'enabled': False, 'status': 'disabled', 'text': '병원 소견 대조를 사용하지 않습니다. CT만으로 검토합니다.'}, [], None
        comparison = None
        if comparison_id:
            row = self.comparison(comparison_id)
            if row['study_id'] != study_id or row['payload']['series_id'] != series_id:
                raise ValueError('다른 검사/시리즈의 소견 대조입니다.')
            report = self.row('report_versions', row['payload']['report_id'])
            matching = all(r['run_id'] in {x['id'] for x in runs} for r in row['payload']['runs'])
            comparison = row if matching else None
            status = 'compared' if matching else 'previous_analysis_comparison'
            text = '사용자가 저장한 소견 대조를 함께 표시합니다.' if matching else '선택한 대조의 분석 버전/근거가 현재 검토와 일치하지 않습니다. 현재 CT 후보와 자동으로 합치지 않습니다.'
        else:
            with self.store.connect() as c:
                value = c.execute('SELECT * FROM report_versions WHERE study_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1', (study_id,)).fetchone()
            report = dict(value) if value else None
            status = 'available_not_compared' if report else 'not_provided'
            text = '입력 소견은 있지만 연결 대조는 선택하지 않았습니다.' if report else '등록된 소견서가 없습니다. CT 분석·검토는 그대로 사용할 수 있습니다.'
        if report:
            with self.store.connect() as c:
                event = c.execute("SELECT details FROM audit_events WHERE entity_id=? AND action='document_transcript_accepted' ORDER BY created_at DESC,rowid DESC LIMIT 1", (report['id'],)).fetchone()
            report['document_id'] = json.loads(event['details']).get('document_id') if event else None
        return {'enabled': True, 'status': status, 'text': text, 'comparison_id': comparison_id}, [report] if report else [], comparison

    def snapshot(self, series_id, batch_id=None, include_report=False, comparison_id=None):
        review = self.view(series_id, batch_id, include_report, comparison_id)
        identifier = str(uuid4())
        allowed_refs = {c['ref'] for c in review['candidates']}
        reviews = [r for r in self.reviews(review['study']['id']) if r['target_type'] == 'study' or r['target_id'] in allowed_refs]
        documents = []
        for report in review['report_sources']:
            if report.get('document_id'):
                document = self.row('source_documents', report['document_id'])
                document['pages'] = json.loads(document['pages']) if document['pages'] else []
                documents.append(document)
        payload = {'schema_version': 'chest-review-2', 'summary_id': identifier, 'study': review['study'],
                   'integrated_review': review, 'report_sources': review['report_sources'], 'source_documents': documents,
                   'comparison': review['comparison'], 'analysis_runs': review['analysis_runs'], 'user_reviews': reviews,
                   'model_comparisons': [], 'longitudinal_reviews': [], 'limitations': LIMITATIONS}
        with self.store.connect() as c:
            c.execute('INSERT INTO summary_versions(id,study_id,payload) VALUES (?,?,?)', (identifier, review['study']['id'], json.dumps(payload, ensure_ascii=False, allow_nan=False)))
            audit(c, 'ct_review_saved', identifier, review['study']['id'], {'series_id': series_id, 'batch_id': batch_id, 'include_report': include_report})
        return {**self.row('summary_versions', identifier), 'payload': payload}
