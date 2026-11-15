"""Versioned report extraction, evidence matching, review and summaries.

All state is local. Machine proposals, hospital/user-entered source text and
user decisions remain separate records. Missing/failed analysis is never normal.
"""
import json
from uuid import uuid4

from .report_parser import extract_report, validate_items

KIND_MODEL = {'nodule': 'lung_nodules', 'pleural_effusion': 'pleural_pericard_effusion', 'pericardial_effusion': 'pleural_pericard_effusion'}
KIND_MODELS={k:{v} for k,v in KIND_MODEL.items()};KIND_MODELS['nodule'].add('monai_nodule')
FINDING_KIND = {'lung_nodules': 'nodule', 'pleural_effusion': 'pleural_effusion', 'pericardial_effusion': 'pericardial_effusion'}


def audit(c, action, entity_id, study_id=None, details=None):
    """Store identifiers/settings in the audit trail, not PHI in process logs."""
    c.execute('INSERT INTO audit_events(id,study_id,action,entity_id,details) VALUES (?,?,?,?,?)',
              (str(uuid4()), study_id, action, entity_id, json.dumps(details or {}, ensure_ascii=False)))


class Workflow:
    def __init__(self, store, analysis):
        self.store, self.analysis = store, analysis

    def row(self, table, identifier):
        # Table is an internal constant, never supplied by a request parameter.
        with self.store.connect() as c:
            row = c.execute(f'SELECT * FROM {table} WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise KeyError('기록을 찾을 수 없습니다.')
        return dict(row)

    def extractions(self, study_id):
        self.row('studies', study_id)
        with self.store.connect() as c:
            return [{**dict(r), 'items': json.loads(r['items'])} for r in c.execute('SELECT * FROM extraction_versions WHERE study_id=? ORDER BY created_at DESC,rowid DESC', (study_id,))]

    def extraction(self, identifier):
        row = self.row('extraction_versions', identifier)
        return {**row, 'items': json.loads(row['items'])}

    def extract(self, report_id):
        report = self.row('report_versions', report_id)
        items = extract_report(report['text'])
        rid = str(uuid4())
        with self.store.connect() as c:
            c.execute('INSERT INTO extraction_versions(id,report_id,study_id,origin,items) VALUES (?,?,?,?,?)',
                      (rid, report_id, report['study_id'], 'local_rule_extraction_v1', json.dumps(items, ensure_ascii=False)))
            audit(c, 'report_extracted', rid, report['study_id'], {'report_id':report_id, 'item_count':len(items)})
        return self.extraction(rid)

    def correct(self, identifier, items):
        previous = self.extraction(identifier)
        report = self.row('report_versions', previous['report_id'])
        validate_items(items, report['text'])
        rid = str(uuid4())
        with self.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            latest = c.execute('SELECT id FROM extraction_versions WHERE report_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1', (report['id'],)).fetchone()
            if latest['id'] != identifier:
                raise ValueError('더 최신 구조화 버전이 있습니다. 다시 불러온 뒤 수정해 주세요.')
            c.execute('INSERT INTO extraction_versions(id,report_id,study_id,parent_id,origin,items) VALUES (?,?,?,?,?,?)',
                      (rid, report['id'], report['study_id'], identifier, 'user_correction', json.dumps(items, ensure_ascii=False)))
            audit(c, 'extraction_corrected', rid, report['study_id'], {'parent_id':identifier})
        return self.extraction(rid)

    def compare(self, extraction_id, series_id, run_ids):
        extraction = self.extraction(extraction_id)
        series = self.row('series', series_id)
        if extraction['study_id'] != series['study_id']:
            raise ValueError('서로 다른 검사 소견/영상을 연결할 수 없습니다.')
        if not run_ids or len(set(run_ids)) != len(run_ids) or len(run_ids) > 20:
            raise ValueError('완료 분석 실행을 1~20개 선택해 주세요.')
        runs, candidates = [], []
        source_fingerprint = None
        models = set()
        for rid in run_ids:
            run = self.analysis.get(rid)
            if run['series_id'] != series_id or run['model_id'] in models:
                raise ValueError('같은 시리즈에서 모델당 한 버전만 대조에 포함해 주세요.')
            result = self.analysis.result(rid)
            fingerprint = [(s['instance_id'], s['sha256']) for s in result['source']['sources']]
            if source_fingerprint is not None and fingerprint != source_fingerprint:
                raise ValueError('분석 입력 원본 목록이 다릅니다. 다른 공간/등록 시점의 실행을 혼합하지 않습니다.')
            source_fingerprint = fingerprint
            models.add(run['model_id'])
            runs.append({'run_id':rid, 'model_id':run['model_id'], 'status':'completed', 'finding_status':result.get('finding_status', 'anatomy_only')})
            for finding in result.get('findings', []):
                candidates.append({**finding, 'ref':f"{rid}/{finding['id']}", 'run_id':rid, 'kind':FINDING_KIND.get(finding['kind'],'other'), 'locations':[]})
        # Infer a lobe only from a same-input completed anatomy mask. Position
        # signs alone cannot establish a lung side or lobe in DICOM coordinates.
        anatomy = next((r for r in runs if r['model_id']=='total'), None)
        if anatomy:
            import numpy as np
            labels = np.load(self.analysis.directory(anatomy['run_id'])/'labels.npy', mmap_mode='r')
            names = {10:'LUL',11:'LLL',12:'RUL',13:'RML',14:'RLL'}
            for candidate in candidates:
                index = tuple(candidate['representative_index_xyz'])
                if all(0 <= v < n for v,n in zip(index,labels.shape)):
                    label = int(labels[index])
                    candidate['locations'] = [names[label]] if label in names else []
        edges = []
        for item in extraction['items']:
            if item.get('excluded') or item['presence'] != 'mentioned' or item['temporal_context'] != 'current' or item['confirmation'] != 'confirmed' or item.get('ambiguous'):
                continue
            for candidate in candidates:
                if candidate['kind'] != item['kind']:
                    continue
                if item['locations'] and candidate['locations'] and not set(item['locations']).intersection(candidate['locations']):
                    continue
                edges.append({'id':str(uuid4()), 'report_item_id':item['id'], 'candidate_ref':candidate['ref'],
                              'state':'proposed', 'reason':'종류 일치; ' + ('해부학 마스크 위치 겹침' if candidate['locations'] and item['locations'] else '위치 미확인, 사용자 검토 필요'), 'measurement_index':None})
        payload = {'schema_version':1, 'series_id':series_id, 'report_id':extraction['report_id'],
                   'items':extraction['items'], 'runs':runs, 'candidates':candidates, 'edges':edges,
                   'warnings':['자동 연결은 후보입니다. 연결 확인이 진단 정확도/측정값 일치를 뜻하지 않습니다.',
                               '병원 미언급은 정상, AI만 제안은 확정 누락, 모델 미탐은 질환 배제가 아닙니다.']}
        latest={}
        for run in self.analysis.list(series_id):
            latest.setdefault(run['model_id'],run['status'])
        payload['omitted_model_statuses']={task:latest.get(task,'not_analysed') if latest.get(task)!='completed' else 'completed_not_selected' for task in set(KIND_MODEL.values())-models}
        return self.save_comparison(extraction, payload, 'automatic_proposal')

    def save_comparison(self, extraction, payload, origin, parent=None):
        rid = str(uuid4())
        payload = classify(payload)
        with self.store.connect() as c:
            c.execute('INSERT INTO comparison_versions(id,study_id,extraction_id,parent_id,origin,payload) VALUES (?,?,?,?,?,?)',
                      (rid, extraction['study_id'], extraction['id'], parent, origin, json.dumps(payload, ensure_ascii=False)))
            audit(c, 'comparison_saved', rid, extraction['study_id'], {'parent_id':parent, 'origin':origin})
        return self.comparison(rid)

    def comparison(self, identifier):
        row = self.row('comparison_versions', identifier)
        return {**row, 'payload':json.loads(row['payload'])}

    def comparisons(self, study_id):
        self.row('studies',study_id)
        with self.store.connect() as c:
            ids = [r[0] for r in c.execute('SELECT id FROM comparison_versions WHERE study_id=? ORDER BY created_at DESC,rowid DESC', (study_id,))]
        return [self.comparison(rid) for rid in ids]

    def update_links(self, identifier, edges):
        previous = self.comparison(identifier)
        payload = previous['payload']
        items = {i['id']:i for i in payload['items']}
        candidates = {c['ref']:c for c in payload['candidates']}
        seen = set()
        if len(edges)>10000:
            raise ValueError('연결 수 한도를 초과했습니다.')
        for edge in edges:
            key = (edge.get('report_item_id'), edge.get('candidate_ref'))
            if key in seen or key[0] not in items or key[1] not in candidates:
                raise ValueError('중복/다른 검사/없는 후보 연결입니다.')
            seen.add(key)
            item = items[key[0]]
            if item.get('excluded') or item['presence']=='absent' or item['temporal_context']!='current':
                raise ValueError('제외·부정·과거 소견은 현재 병변으로 확정 연결하지 않습니다. 원문 정정 해석은 별도 버전으로 저장해 주세요.')
            if edge.get('state') not in {'proposed','confirmed','rejected'} or not isinstance(edge.get('reason'),str):
                raise ValueError('연결 상태와 근거를 입력해 주세요.')
            if edge['state']=='confirmed' and not edge['reason'].strip():
                raise ValueError('연결 확인 근거가 필요합니다.')
            if edge['state']=='confirmed' and (item['confirmation']!='confirmed' or item.get('ambiguous')):
                raise ValueError('먼저 원문 구조화 항목의 모호함을 정정하고 확인해 주세요.')
            index = edge.get('measurement_index')
            if index is not None and (type(index) is not int or not 0 <= index < len(item.get('measurements',[]))):
                raise ValueError('비교할 원문 측정값을 확인해 주세요.')
        payload['edges']=edges
        return self.save_comparison(self.extraction(previous['extraction_id']), payload, 'user_link_review', identifier)

    def review(self, study_id, target_type, target_id, decision, note, question):
        self.row('studies',study_id)
        if target_type=='study':
            if target_id != study_id: raise ValueError('검사 대상이 일치하지 않습니다.')
        elif target_type=='finding':
            rid, _, fid = target_id.partition('/')
            run = self.analysis.get(rid)
            if self.row('series',run['series_id'])['study_id'] != study_id or not any(f['id']==fid for f in self.analysis.result(rid).get('findings',[])):
                raise ValueError('검사에 속하지 않는 후보입니다.')
        elif target_type=='comparison':
            if self.comparison(target_id)['study_id']!=study_id: raise ValueError('검사 대조 대상이 다릅니다.')
        else: raise ValueError('지원하지 않는 검토 대상입니다.')
        if decision not in {'accepted','excluded','deferred','not_reviewed'}:
            raise ValueError('검토 상태가 유효하지 않습니다.')
        rid = str(uuid4())
        with self.store.connect() as c:
            c.execute('INSERT INTO review_versions(id,study_id,target_type,target_id,decision,note,question) VALUES (?,?,?,?,?,?,?)',
                      (rid,study_id,target_type,target_id,decision,note,question))
            audit(c,'review_saved',rid,study_id,{'target_type':target_type,'target_id':target_id,'decision':decision})
        return self.row('review_versions',rid)

    def reviews(self,study_id):
        with self.store.connect() as c:
            return [dict(r) for r in c.execute('SELECT * FROM review_versions WHERE study_id=? ORDER BY created_at DESC,rowid DESC', (study_id,))]

    def summary(self,study_id,comparison_id=None):
        study=self.row('studies',study_id)
        comparison=self.comparison(comparison_id) if comparison_id else None
        if comparison and comparison['study_id']!=study_id: raise ValueError('다른 검사의 대조입니다.')
        with self.store.connect() as c:
            reports=[dict(r) for r in c.execute('SELECT * FROM report_versions WHERE study_id=? ORDER BY created_at,rowid', (study_id,))]
            runs=[dict(r) for r in c.execute('SELECT a.* FROM analysis_runs a JOIN series s ON s.id=a.series_id WHERE s.study_id=? ORDER BY a.created_at,a.rowid', (study_id,))]
            documents=[{**dict(r),'pages':json.loads(r['pages']) if r['pages'] else []} for r in c.execute('SELECT * FROM source_documents WHERE study_id=?',(study_id,))]
            accepted={r['entity_id']:json.loads(r['details']).get('document_id') for r in c.execute("SELECT entity_id,details FROM audit_events WHERE study_id=? AND action='document_transcript_accepted'",(study_id,))}
            model_comparisons=[{**dict(r),'payload':json.loads(r['payload'])} for r in c.execute('SELECT * FROM model_comparison_versions WHERE study_id=? ORDER BY created_at DESC,rowid DESC',(study_id,))]
            longitudinal=[{**dict(r),'payload':json.loads(r['payload'])} for r in c.execute('SELECT * FROM longitudinal_versions WHERE current_study=? ORDER BY created_at DESC,rowid DESC',(study_id,))]
        for report in reports:report['document_id']=accepted.get(report['id'])
        payload={'schema_version':'chest-review-1','study':{k:study[k] for k in ['id','study_date','description']},
                 'report_sources':reports,'source_documents':documents,'comparison':comparison,'user_reviews':self.reviews(study_id),
                 'model_comparisons':model_comparisons,'longitudinal_reviews':longitudinal,
                 'analysis_runs':[{**r,'snapshot':json.loads(r['snapshot'])} for r in runs],
                 'limitations':['검토용 정리본이며 병원 원문·AI 후보·사용자 판단을 구별합니다.',
                                '미분석·실패·후보 없음은 정상 판정이 아닙니다. 진료 적용 성능은 검증되지 않았습니다.']}
        rid=str(uuid4()); payload['summary_id']=rid
        with self.store.connect() as c:
            c.execute('INSERT INTO summary_versions(id,study_id,payload) VALUES (?,?,?)', (rid,study_id,json.dumps(payload,ensure_ascii=False)))
            audit(c,'summary_created',rid,study_id,{'comparison_id':comparison_id})
        return {**self.row('summary_versions',rid),'payload':payload}


def classify(payload):
    """Compute mutually exclusive report/AI states from actual links and input status."""
    report_counts={key:0 for key in ['candidate','confirmed','report_only','not_comparable']}
    ai_counts={key:0 for key in ['candidate','confirmed','ai_only','not_comparable']}
    done={r['model_id'] for r in payload['runs'] if r['status']=='completed'}
    usable=[e for e in payload['edges'] if e['state']!='rejected']
    for item in payload['items']:
        links=[e for e in usable if e['report_item_id']==item['id']]
        if any(e['state']=='confirmed' for e in links): status='confirmed'
        elif links: status='candidate'
        elif item.get('excluded') or item['presence']!='mentioned' or item['confirmation']!='confirmed' or item['temporal_context']!='current' or item.get('ambiguous') or not KIND_MODELS.get(item['kind'],set()).intersection(done): status='not_comparable'
        else: status='report_only'
        item['comparison_status']=status; report_counts[status]+=1
        item['comparison_reason']=('excluded_by_user' if item.get('excluded') else 'negative_or_uncertain_report' if item['presence']!='mentioned' else 'historical_context' if item['temporal_context']!='current' else 'extraction_needs_review' if item['confirmation']!='confirmed' or item.get('ambiguous') else 'model_'+payload.get('omitted_model_statuses',{}).get(KIND_MODEL.get(item['kind']),'unsupported') if not KIND_MODELS.get(item['kind'],set())&done else 'same_examination_candidate_comparison')
    for candidate in payload['candidates']:
        links=[e for e in usable if e['candidate_ref']==candidate['ref']]
        status='confirmed' if any(e['state']=='confirmed' for e in links) else 'candidate' if links else 'ai_only'
        candidate['comparison_status']=status; ai_counts[status]+=1
    items={i['id']:i for i in payload['items']}; candidates={c['ref']:c for c in payload['candidates']}
    for edge in payload['edges']:
        item,candidate=items[edge['report_item_id']],candidates[edge['candidate_ref']]
        values=item.get('measurements',[]); index=edge.get('measurement_index')
        measurement=values[index] if index is not None else next((m for m in values if m['dimension']=='length' and m.get('temporal_context')=='current'),None)
        ai=candidate.get('diameter_mm') if measurement and measurement['dimension']=='length' else candidate.get('volume_mm3')
        report=measurement.get('normalized_value') if measurement else None
        edge['measurement_comparison']={'report_value':report,'ai_value':ai,'unit':measurement.get('normalized_unit') if measurement else None,
                                        'difference':ai-report if ai is not None and report is not None else None,
                                        'interpretation':'same-examination measurement-method difference; NOT growth',
                                        'ai_method':candidate.get('diameter_method') if measurement and measurement['dimension']=='length' else 'original voxel count × voxel volume',
                                        'report_method':'not specified; inspect source quote'}
    payload['report_counts']=report_counts; payload['ai_counts']=ai_counts
    return payload
