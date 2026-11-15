"""Original-preserving document intake and local PDF text/OCR extraction."""
import hashlib
from io import BytesIO
import json
from pathlib import Path
import subprocess
import time
from uuid import uuid4

from .analysis_runtime import ROOT
from .maintenance import managed
from .workflow import audit
from .owned_process import spawn_owned,finish_owned

MAX_DOCUMENT_BYTES=32*1024*1024


def ingest_document(store,study_id,data,media_type):
    """An extraction is an unverified derivative, never a signed hospital original.

    Each page retains number, exact extracted text, method/confidence and source
    hash. Failed/blank extraction stays failed and cannot be accepted as a report.
    """
    with store.connect() as c:
        if not c.execute('SELECT id FROM studies WHERE id=?',(study_id,)).fetchone():raise KeyError('검사가 없습니다.')
    if len(data)>MAX_DOCUMENT_BYTES:raise ValueError('문서당 32 MiB 한도입니다.')
    if media_type not in {'application/pdf','image/png','image/jpeg'}:raise ValueError('PDF/PNG/JPEG만 지원합니다.')
    identifier=str(uuid4());folder=managed(store.root,store.root/'documents'/identifier);folder.mkdir(parents=True)
    original=folder/'original.bin';original.write_bytes(data)
    digest=hashlib.sha256(data).hexdigest()
    with store.connect() as c:
        c.execute("INSERT INTO source_documents(id,study_id,media_type,sha256,stored_name,status) VALUES (?,?,?,?,?,'running')",(identifier,study_id,media_type,digest,identifier))
        audit(c,'document_uploaded',identifier,study_id,{'media_type':media_type,'sha256':digest})
    pages=[];started=time.monotonic()
    try:
        if media_type=='application/pdf':
            from pypdf import PdfReader
            reader=PdfReader(BytesIO(data),strict=True)
            if reader.is_encrypted:raise ValueError('암호화 PDF는 지원하지 않습니다.')
            if len(reader.pages)>50:raise ValueError('초기 문서 지원은 최대 50쪽입니다.')
            import pypdfium2 as pdfium
            document=pdfium.PdfDocument(data)
            try:
                for index,page in enumerate(reader.pages):
                    if time.monotonic()-started>180:raise ValueError('문서 처리 시간 한도 180초를 초과했습니다. 원본을 보고 직접 입력해 주세요.')
                    text=page.extract_text() or ''
                    method='embedded_pdf_text';confidence=None
                    image_path=folder/f'page-{index+1}.png'
                    # Always render a local reference image for human correction.
                    pdf_page=document[index]
                    if pdf_page.get_width()*pdf_page.get_height()*4>20_000_000:
                        raise ValueError('페이지 렌더링 한도 2천만 픽셀을 초과했습니다.')
                    bitmap=pdf_page.render(scale=2)
                    bitmap.to_pil().save(image_path);bitmap.close()
                    if not text.strip():
                        ocr=ocr_page(image_path,min(120,max(1,180-(time.monotonic()-started))));text=ocr['text'];method=ocr['engine'];confidence=ocr['confidence']
                    pages.append({'page':index+1,'text':text,'method':method,'confidence':confidence,'needs_review':True})
            finally: document.close()
        else:
            from PIL import Image
            Image.MAX_IMAGE_PIXELS=20_000_000
            with Image.open(BytesIO(data)) as image:
                if image.width*image.height>20_000_000:raise ValueError('문서 이미지 픽셀 한도를 초과했습니다.')
                image.convert('RGB').save(folder/'page-1.png')
            ocr=ocr_page(folder/'page-1.png')
            pages=[{'page':1,'text':ocr['text'],'method':ocr['engine'],'confidence':ocr['confidence'],'needs_review':True}]
        if not pages or not any(p['text'].strip() for p in pages):raise ValueError('추출된 텍스트가 없습니다. 원본을 보고 직접 입력해 주세요.')
        with store.connect() as c:
            c.execute("UPDATE source_documents SET status='extracted',pages=? WHERE id=?",(json.dumps(pages,ensure_ascii=False),identifier))
            audit(c,'document_extracted',identifier,study_id,{'pages':len(pages)})
    except Exception as exc:
        message=str(exc) if isinstance(exc,ValueError) else '로컬 문서 추출에 실패했습니다. 원본은 보존했습니다. 설치 상태/문서를 확인해 주세요.'
        with store.connect() as c:c.execute("UPDATE source_documents SET status='failed',error=?,pages=? WHERE id=?",(message,json.dumps(pages,ensure_ascii=False),identifier))
    return document_info(store,identifier)


def ocr_page(image_path,timeout=120):
    """Owned Node/WASM process, bounded time, no patient content in logs."""
    output=image_path.with_suffix('.ocr.json')
    process=spawn_owned(['node',str(ROOT/'backend'/'ocr_worker.mjs'),str(image_path.resolve()),str(output.resolve())],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        if process.wait(timeout=timeout):raise ValueError('로컬 OCR 실행에 실패했습니다. setup-ocr.ps1 설치 상태를 확인해 주세요.')
    finally:finish_owned(process)
    return json.loads(output.read_text(encoding='utf-8'))


def document_info(store,identifier):
    with store.connect() as c:row=c.execute('SELECT * FROM source_documents WHERE id=?',(identifier,)).fetchone()
    if row is None:raise KeyError('문서가 없습니다.')
    return {**dict(row),'pages':json.loads(row['pages']) if row['pages'] else []}


def accept_document(store,identifier,text,confirmed):
    document=document_info(store,identifier)
    if document['status']!='extracted' or not confirmed or not text.strip():raise ValueError('추출 성공 문서의 원문/검사 연결을 확인하고 내용을 입력해 주세요.')
    rid=str(uuid4())
    # A source attachment is represented in audit details as well as a fixed
    # provenance header. This is an unverified OCR transcript, not authenticated.
    with store.connect() as c:
        c.execute('INSERT INTO report_versions(id,study_id,source,text) VALUES (?,?,?,?)',(rid,document['study_id'],'document_ocr_unverified',text))
        audit(c,'document_transcript_accepted',rid,document['study_id'],{'document_id':identifier,'sha256':document['sha256'],'user_confirmed':True})
    return {'id':rid,'document_id':identifier,'source':'document_ocr_unverified'}
