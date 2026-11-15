"""Local source-preserving JSON/PDF exports of immutable review snapshots."""
from html import escape
from io import BytesIO
import json
from pathlib import Path


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
    elements=[]
    def add(text,style='body'):
        elements.append(Paragraph(escape(str(text)).replace('\n','<br/>'),styles[style]))
    add('흉부 CT 검토 정리본','title')
    add('병원/사용자 입력 원문 · AI 후보 · 사용자 검토를 구별한 기록입니다. 확정 판독이 아닙니다.')
    study=summary['study']
    add(f"검사일: {study.get('study_date') or '미기재'} | 검사: {study.get('description') or '미기재'}")
    add(f"정리본 ID: {summary['summary_id']} | 형식: {summary['schema_version']}",'small')
    add('적용 범위와 한계','heading')
    for text in summary['limitations']: add(text)
    add('입력 원문과 출처','heading')
    if not summary['report_sources']: add('등록된 입력 원문이 없습니다.')
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
        add(f"{run['model_id']} | {run['status']} | 실행 {run['id']}")
        add(f"시리즈 {run['series_id']} | 설정 {run['snapshot'].get('configuration',{}).get('version','미기재')}",'small')
        if run.get('error'): add(run['error'])
    comparison=summary.get('comparison')
    add('소견과 AI 후보의 연결','heading')
    if not comparison: add('선택한 대조 버전이 없습니다. 일치/정상을 추정하지 않습니다.')
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
        add(f"{review['decision']} | {review['created_at']} | {review['target_type']}")
        add(f"메모: {review['note']}\n질문: {review['question']}")
        add(f"사용자 검토 버전 {review['id']} | 대상 {review['target_id']}",'small')
    buffer=BytesIO()
    def page(canvas,doc):
        canvas.saveState();canvas.setFont('WorkspaceKorean',7);canvas.setFillColor(colors.HexColor('#536777'))
        canvas.drawString(40,24,'로컬 검토 기록 - 원문/AI/사용자 판단 구분 - 임상 성능 미검증')
        canvas.drawRightString(A4[0]-40,24,str(doc.page));canvas.restoreState()
    SimpleDocTemplate(buffer,pagesize=A4,rightMargin=40,leftMargin=40,topMargin=40,bottomMargin=43,
                      title='흉부 CT 검토 정리본',author='Local CT Review').build(elements,onFirstPage=page,onLaterPages=page)
    return buffer.getvalue()
