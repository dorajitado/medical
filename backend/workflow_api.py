"""Strict local API boundary for source-linked workflow versions and exports."""
import json
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from .workflow import Workflow, audit
from .exports import json_bytes, pdf_bytes
from .documents import ingest_document, document_info, accept_document, MAX_DOCUMENT_BYTES
from .maintenance import managed
from .editorial import polish_summary


class StrictInput(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)

class Correction(StrictInput):
    items:list[dict]=Field(max_length=1000)

class CompareInput(StrictInput):
    extraction_id:str
    series_id:str
    run_ids:list[str]=Field(min_length=1,max_length=20)

class LinksInput(StrictInput):
    edges:list[dict]=Field(max_length=10000)

class ReviewInput(StrictInput):
    target_type:str
    target_id:str
    decision:str
    note:str=Field(default='',max_length=100000)
    question:str=Field(default='',max_length=10000)

class SummaryInput(StrictInput):
    comparison_id:str|None=None

class DocumentAccept(StrictInput):
    text:str=Field(min_length=1,max_length=100000)
    confirmed:bool


def create_workflow_router(store,analysis):
    router=APIRouter(prefix='/api')
    service=Workflow(store,analysis)
    def call(function,*args):
        try: return function(*args)
        except KeyError: raise HTTPException(404,'대상 기록을 찾을 수 없습니다.')
        except ValueError as exc: raise HTTPException(422,str(exc))
        except OSError: raise HTTPException(422,'출처 파일을 읽을 수 없습니다. 원본과 분석 상태를 확인해 주세요.')

    @router.post('/reports/{report_id}/extract',status_code=201)
    def extract(report_id:str): return call(service.extract,report_id)

    @router.get('/studies/{study_id}/extractions')
    def extractions(study_id:str): return {'items':call(service.extractions,study_id)}

    @router.put('/extractions/{extraction_id}')
    def correct(extraction_id:str,value:Correction): return call(service.correct,extraction_id,value.items)

    @router.post('/comparisons',status_code=201)
    def compare(value:CompareInput): return call(service.compare,value.extraction_id,value.series_id,value.run_ids)

    @router.get('/studies/{study_id}/comparisons')
    def comparisons(study_id:str): return {'items':call(service.comparisons,study_id)}

    @router.put('/comparisons/{comparison_id}/links')
    def links(comparison_id:str,value:LinksInput): return call(service.update_links,comparison_id,value.edges)

    @router.get('/studies/{study_id}/reviews')
    def reviews(study_id:str): return {'items':call(service.reviews,study_id)}

    @router.post('/studies/{study_id}/reviews',status_code=201)
    def review(study_id:str,value:ReviewInput):
        return call(service.review,study_id,value.target_type,value.target_id,value.decision,value.note,value.question)

    @router.post('/studies/{study_id}/summaries',status_code=201)
    def summary(study_id:str,value:SummaryInput): return call(service.summary,study_id,value.comparison_id)

    @router.get('/studies/{study_id}/summaries')
    def summaries(study_id:str):
        call(service.row,'studies',study_id)
        with store.connect() as c:
            return {'items':[{**dict(r),'payload':json.loads(r['payload'])} for r in c.execute('SELECT * FROM summary_versions WHERE study_id=? ORDER BY created_at DESC,rowid DESC',(study_id,))]}

    @router.post('/summaries/{summary_id}/polish',status_code=201)
    def polish(summary_id:str):return call(polish_summary,store,analysis,summary_id)

    @router.get('/summaries/{summary_id}/export/{format}')
    def export(summary_id:str,format:str):
        if format not in {'json','pdf'}: raise HTTPException(404,'지원하지 않는 출력 형식입니다.')
        row=call(service.row,'summary_versions',summary_id)
        payload=json.loads(row['payload'])
        data=call(pdf_bytes if format=='pdf' else json_bytes,payload)
        with store.connect() as c: audit(c,'summary_exported',summary_id,row['study_id'],{'format':format})
        return Response(data,media_type='application/pdf' if format=='pdf' else 'application/json',
                        headers={'Content-Disposition':f'attachment; filename="ct-review-{summary_id}.{format}"'})

    @router.get('/studies/{study_id}/audit')
    def history(study_id:str):
        call(service.row,'studies',study_id)
        with store.connect() as c:
            return {'items':[{**dict(r),'details':json.loads(r['details'])} for r in c.execute('SELECT * FROM audit_events WHERE study_id=? ORDER BY created_at DESC,rowid DESC',(study_id,))]}

    @router.get('/studies/{study_id}/documents')
    def documents(study_id:str):
        call(service.row,'studies',study_id)
        with store.connect() as c:ids=[r[0] for r in c.execute('SELECT id FROM source_documents WHERE study_id=? ORDER BY created_at DESC,rowid DESC',(study_id,))]
        return {'items':[document_info(store,i) for i in ids]}

    @router.post('/studies/{study_id}/documents',status_code=201)
    async def document(study_id:str,request:Request):
        from starlette.concurrency import run_in_threadpool
        data=bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data)>MAX_DOCUMENT_BYTES:raise HTTPException(413,'문서당 32 MiB 한도입니다.')
        return await run_in_threadpool(call,ingest_document,store,study_id,bytes(data),request.headers.get('content-type',''))

    @router.get('/documents/{identifier}/page/{page}')
    def document_page(identifier:str,page:int):
        info=call(document_info,store,identifier)
        if not 1<=page<=max(1,len(info['pages'])):raise HTTPException(404,'페이지가 없습니다.')
        path=managed(store.root,store.root/'documents'/info['stored_name']/f'page-{page}.png')
        if not path.exists():raise HTTPException(404,'페이지 이미지가 없습니다.')
        from fastapi.responses import FileResponse
        return FileResponse(path,media_type='image/png')

    @router.get('/documents/{identifier}/original')
    def document_original(identifier:str):
        info=call(document_info,store,identifier)
        path=managed(store.root,store.root/'documents'/info['stored_name']/'original.bin')
        from fastapi.responses import FileResponse
        return FileResponse(path,media_type=info['media_type'],filename='original-document'+('.pdf' if info['media_type']=='application/pdf' else '.png' if info['media_type']=='image/png' else '.jpg'))

    @router.post('/documents/{identifier}/accept',status_code=201)
    def document_accept(identifier:str,value:DocumentAccept):return call(accept_document,store,identifier,value.text,value.confirmed)
    return router
