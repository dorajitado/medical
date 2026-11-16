"""Local source-preserving JSON/PDF exports of immutable review snapshots."""
from html import escape
from io import BytesIO
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone


def json_bytes(summary):
    """Round-trippable UTF-8, explicit schema and original numeric/null values."""
    return json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8')


def pdf_bytes(summary):
    """Render Korean using a local OS font; never load remote fonts or markup.

    User text is escaped before Paragraph parsing, so an <img> in a report can
    neither cause a file read nor issue a network request. Long CJK paragraphs
    flow across pages instead of overflowing a fixed-height table row.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    font=Path('C:/Windows/Fonts/malgun.ttf')
    if not font.is_file(): raise ValueError('로컬 한글 PDF 글꼴을 찾지 못했습니다. Windows 맑은 고딕 설치를 확인해 주세요.')
    if 'WorkspaceKorean' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('WorkspaceKorean',str(font)))
    styles={
        'title':ParagraphStyle('title',fontName='WorkspaceKorean',fontSize=19,leading=27,textColor=colors.HexColor('#244e77'),spaceAfter=16,wordWrap='CJK'),
        'heading':ParagraphStyle('heading',fontName='WorkspaceKorean',fontSize=12,leading=18,textColor=colors.HexColor('#244e77'),spaceBefore=14,spaceAfter=7,keepWithNext=True,wordWrap='CJK'),
        'body':ParagraphStyle('body',fontName='WorkspaceKorean',fontSize=9,leading=15,spaceAfter=7,wordWrap='CJK'),
        'small':ParagraphStyle('small',fontName='WorkspaceKorean',fontSize=7,leading=11,textColor=colors.HexColor('#536777'),spaceAfter=5,wordWrap='CJK'),
    }
    # Keep an execution title with its provenance line across page boundaries.
    styles['run_title'] = ParagraphStyle('run_title', parent=styles['body'], keepWithNext=True)
    elements=[]
    def add(text,style='body'):
        elements.append(Paragraph(escape(str(text)).replace('\n','<br/>'),styles[style]))
    integrated = summary.get('integrated_review')
    add('CT 종합 검토' if integrated else '흉부 CT 검토 정리본','title')
    add('CT의 AI 후보·분석 범위·사용자 검토 기록입니다. 병원 소견 대조는 선택입니다. 확정 판독이 아닙니다.' if integrated else '병원/사용자 입력 원문 · AI 후보 · 사용자 검토를 구별한 기록입니다. 확정 판독이 아닙니다.')
    study=summary['study']
    add(f"검사일: {study.get('study_date') or '미기재'} | 검사: {study.get('description') or '미기재'}")
    add(f"정리본 ID: {summary['summary_id']} | 형식: {summary['schema_version']}",'small')
    add('적용 범위와 한계','heading')
    for text in summary['limitations']: add(text)
    if integrated:
        add(integrated['headline'], 'heading')
        status_text = {'available':'선택 범위 분석 완료','processing':'분석 중','partial':'일부 범위만 분석됨','needs_attention':'분석 상태 확인 필요','not_analysed':'분석 전'}
        created = datetime.fromisoformat(integrated['generated_at']).astimezone(timezone(timedelta(hours=9))).strftime('%Y-%m-%d %H:%M:%S KST')
        add(f"생성 시각 {created} | {status_text[integrated['status']]} | 중복 가능한 제안 수 {integrated['proposal_count']}")
        add(f"CT 시리즈 {integrated['series_id']} | 원본 지문 {integrated['source']['digest']}", 'small')
        for entry in integrated['coverage']:
            add(f"{entry['title']}: {entry['status_text']} | 제안 {entry['candidate_count'] if entry['candidate_count'] is not None else '확인 전'}")
            if entry.get('issue'): add(entry['issue'], 'small')
        for candidate in integrated['candidates']:
            add(candidate['title'] + ' · ' + candidate['location'], 'heading')
            add(candidate['explanation']); add(candidate['measurement_text'])
            # Show the latest user record beside the candidate. The history
            # appendix below preserves earlier decisions without replacing AI.
            latest = candidate.get('user_review')
            labels = {'accepted':'사용자 확인 표시','excluded':'후보 제외 표시','deferred':'확인 보류','not_reviewed':'검토 전'}
            add('사용자 기록: ' + (labels[latest['decision']] if latest else '검토 전') + ' (진단 확정 아님)', 'small')
            if candidate['volume_mm3'] is not None: add(f"계산 부피 {candidate['volume_mm3']:.2f} mm³ ({candidate['volume_ml']:.3f} mL)")
            add(f"위치 근거: {candidate['location_basis']} | 단면 {candidate['slice_number']}/{candidate['slice_count']}", 'small')
            # Display precision is independent of the exact JSON/LPS source.
            point = ', '.join(f'{v:.3f}' for v in candidate['representative_lps_mm'])
            add(f"출처 {candidate['ref']} | 원본 {candidate['source_instance_id']} | LPS(mm) {point}", 'small')
            method = '원본 촬영 단면의 외곽 최대 너비 계산 (Feret)' if candidate['model_id']=='lung_nodules' else '탐지상자는 위치 표시용이며 병변 장경/부피를 측정하지 않음' if candidate['model_id']=='monai_nodule' else '원본 복셀 수 × 복셀 부피, 종류별 영역 합계'
            add(f"계측 방법 {method} | 독립 모델 점수 {candidate['score'] if candidate['score'] is not None else '제공 없음'} (악성 확률 아님)", 'small')
            if candidate['related_proposals']: add('가까운 위치의 다른 제안(동일 병변 미확정): ' + ', '.join(candidate['related_proposals']), 'small')
        add('선택한 병원 소견 대조', 'heading'); add(integrated['report_context']['text'])
    else:
        add('입력 원문과 출처','heading')
    if not summary['report_sources'] and not integrated: add('등록된 입력 원문이 없습니다.')
    for report in summary['report_sources']:
        add(f"출처: {report['source']} | 입력 시각: {report['created_at']} | 원문 버전: {report['id']}",'small')
        add(report['text'])
        if report.get('document_id'):add('첨부 문서 출처 ID: '+report['document_id'],'small')
    for document in summary.get('source_documents',[]):
        add(f"첨부 원본 {document['id']} | {document['media_type']} | {document['status']}",'small')
        add(f"SHA-256 {document['sha256']} | 페이지 {len(document['pages'])}",'small')
    add('분석 실행과 상태','heading')
    if not summary['analysis_runs']: add('분석하지 않았습니다. 정상 판정이 아닙니다.')
    for run in summary['analysis_runs']:
        entry = next((c for c in integrated['coverage'] if c['model_id']==run['model_id']), None) if integrated else None
        add(f"{entry['title'] if entry else run['model_id']} | {entry['status_text'] if entry else run['status']} | 실행 {run['id']}", 'run_title')
        add(f"시리즈 {run['series_id']} | 설정 {run['snapshot'].get('configuration',{}).get('version','미기재')}",'small')
        if run.get('error'): add(run['error'])
    comparison=summary.get('comparison')
    if comparison or not integrated: add('소견과 AI 후보의 연결','heading')
    if not comparison:
        if not integrated: add('선택한 대조 버전이 없습니다. 일치/정상을 추정하지 않습니다.')
    else:
        payload=comparison['payload']
        add(f"대조 버전 {comparison['id']} | 소견 구조화 버전 {comparison['extraction_id']}",'small')
        for item in payload['items']:
            quote=(item.get('source_span') or {}).get('text','원문 범위 없는 사용자 추가 해석')
            add(f"[{item['comparison_status']}] {item['kind']} | {', '.join(item['locations']) or '위치 미확인'} | {item['presence']} | {item['temporal_context']}")
            add(f"원문/출처: {quote}")
            add(f"항목 {item['id']} | 원문 버전 {payload['report_id']}",'small')
        for candidate in payload['candidates']:
            volume=f"{candidate['volume_mm3']:.2f} mm³" if candidate.get('volume_mm3') is not None else '탐지상자만 제공, 분할 부피 없음'
            add(f"AI [{candidate['comparison_status']}] {candidate['title']} | 부피 {volume}")
            if candidate.get('diameter_mm') is not None: add(f"장경 {candidate['diameter_mm']:.2f} mm | {candidate['diameter_method']}")
            add(f"AI 출처 {candidate['ref']} | LPS(mm) {candidate['representative_lps_mm']} | 원본 인스턴스 {candidate['source_instance_id']}",'small')
        for edge in payload['edges']:
            add(f"연결 [{edge['state']}] {edge['report_item_id']} -> {edge['candidate_ref']}",'small')
            add('근거: '+edge['reason'])
            m=edge['measurement_comparison']
            add(f"동일 검사 측정 차이: {m['difference'] if m['difference'] is not None else '계산 불가'} {m.get('unit') or ''}. 성장/이전 검사 변화가 아닙니다.")
    for comparison in summary.get('model_comparisons',[]):
        add('독립 결절 모델 검토 버전 '+comparison['id'],'heading')
        for group in comparison['payload']['groups']:
            for candidate in group:
                add(f"{candidate['model_id']} | {candidate['ref']} | 모델 점수 {candidate.get('score')} (악성 확률 아님)",'small')
        for edge in comparison['payload']['edges']:add(f"[{edge['state']}] {edge['left']} ↔ {edge['right']} | {edge['reason']}",'small')
    for longitudinal in summary.get('longitudinal_reviews',[]):
        add('이전 검사 비교 버전 '+longitudinal['id'],'heading');p=longitudinal['payload']
        add(f"이전 {p['prior_study']['study_date']} → 현재 {p['current_study']['study_date']} | {p['days']}일 간격")
        add(f"정합 {p['registration']['status']} | 기준점 RMS {p['registration']['rms_mm']} mm. 영상 자동 정렬·성장 판정 아님.")
        for link in p['links']:
            add(f"연결 근거 {link['reason']} | {link['prior_ref']} → {link['current_ref']}",'small')
            for field,change in link['changes'].items():add(f"{field}: {change['prior']} → {change['current']} | {change['status']} | 차이 {change['delta']}, 변화율 {change['percent']}%")
    if summary.get('editorial'):
        add('로컬 문장 배치 정리 (원문 문구 보존)','heading')
        for clause in summary['editorial']['clauses']:
            add(clause['text']);add(f"출처 {clause['report_id']} · {clause['id']}",'small')
        add(summary['editorial']['limitation'],'small')
    add('사용자 검토 · 메모 · 진료 질문','heading')
    if not summary['user_reviews']: add('저장된 사용자 판단이 없습니다.')
    for review in summary['user_reviews']:
        labels = {'accepted':'사용자 확인 표시','excluded':'후보 제외 표시','deferred':'확인 보류','not_reviewed':'검토 전'}
        add(f"{labels.get(review['decision'],review['decision']) if integrated else review['decision']} | {review['created_at']} UTC | {review['target_type']}")
        add(f"메모: {review['note']}\n질문: {review['question']}")
        add(f"사용자 검토 버전 {review['id']} | 대상 {review['target_id']}",'small')
    if integrated:
        add('용어 설명 참고 (개별 CT 판정 근거와 구별)','heading')
        glossary = {c['kind']:(c['title'],c['glossary_source']) for c in integrated['candidates']}
        for title, link in glossary.values(): add(f'{title}: {link}', 'small')
    buffer=BytesIO()
    def page(canvas,doc):
        canvas.saveState();canvas.setFont('WorkspaceKorean',7);canvas.setFillColor(colors.HexColor('#536777'))
        canvas.drawString(40,24,'로컬 검토 기록 - 원문/AI/사용자 판단 구분 - 임상 성능 미검증')
        canvas.drawRightString(A4[0]-40,24,str(doc.page));canvas.restoreState()
    SimpleDocTemplate(buffer,pagesize=A4,rightMargin=40,leftMargin=40,topMargin=40,bottomMargin=43,
                      title='흉부 CT 검토 정리본',author='Local CT Review').build(elements,onFirstPage=page,onLaterPages=page)
    return buffer.getvalue()
