"""Typed local routes for independent comparisons and evaluation preparation."""
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from .extended_workflow import ExtendedWorkflow


class Input(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)

class ModelInput(Input):
    run_ids:list[str]=Field(min_length=2,max_length=2)

class ModelLinks(Input):
    edges:list[dict]=Field(max_length=10000)

class PriorInput(Input):
    prior_study:str
    current_run:str
    prior_run:str
    links:list[dict]=Field(max_length=1000)
    same_patient_confirmed:bool
    landmarks:list=Field(default_factory=list,max_length=30)

class EvaluationInput(Input):
    split:str
    reference_source:str=Field(default='',max_length=10000)
    reviewer:str=Field(default='',max_length=1000)
    payload:dict


def create_extended_router(store,analysis):
    router=APIRouter(prefix='/api');service=ExtendedWorkflow(store,analysis)
    def call(function,*args):
        try:return function(*args)
        except KeyError:raise HTTPException(404,'대상 출처를 찾을 수 없습니다.')
        except (ValueError,TypeError) as e:raise HTTPException(422,str(e))

    @router.post('/studies/{study_id}/model-comparisons',status_code=201)
    def compare(study_id:str,value:ModelInput):return call(service.compare_models,study_id,value.run_ids)

    @router.put('/model-comparisons/{identifier}/links')
    def links(identifier:str,value:ModelLinks):return call(service.model_links,identifier,value.edges)

    @router.get('/studies/{study_id}/model-comparisons')
    def model_history(study_id:str):
        call(service.row,'studies',study_id)
        with store.connect() as c:return {'items':[{**dict(r),'payload':json.loads(r['payload'])} for r in c.execute('SELECT * FROM model_comparison_versions WHERE study_id=? ORDER BY created_at DESC,rowid DESC',(study_id,))]}

    @router.post('/studies/{study_id}/longitudinal',status_code=201)
    def prior(study_id:str,value:PriorInput):return call(service.longitudinal,study_id,value.prior_study,value.current_run,value.prior_run,value.links,value.same_patient_confirmed,value.landmarks)

    @router.get('/studies/{study_id}/longitudinal')
    def prior_history(study_id:str):
        call(service.row,'studies',study_id)
        with store.connect() as c:return {'items':[{**dict(r),'payload':json.loads(r['payload'])} for r in c.execute('SELECT * FROM longitudinal_versions WHERE current_study=? ORDER BY created_at DESC,rowid DESC',(study_id,))]}

    @router.post('/studies/{study_id}/evaluation-cases',status_code=201)
    def evaluation(study_id:str,value:EvaluationInput):return call(service.evaluation_case,study_id,value.split,value.reference_source,value.reviewer,value.payload)

    @router.get('/evaluation')
    def evaluation_status():return call(service.evaluation_summary)

    @router.get('/evaluation/export')
    def evaluation_export():
        from fastapi.responses import Response
        payload={'schema':'ct-evaluation-register-1',**call(service.evaluation_summary)}
        return Response(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False),media_type='application/json',headers={'Content-Disposition':'attachment; filename="evaluation-register.json"'})

    @router.get('/capabilities')
    def capabilities():
        # Conditional modules are explicit gaps, never a successful negative test.
        return {'items':[
            {'id':'AI-09','name':'폐색전','status':'not_supported','requirements':['CTPA 프로토콜·폐동맥 조영 적합성 확인','고정 공개 가중치/전처리 어댑터','전문의 정답·외부 평가'],'reason':'일반 조영 CT를 CTPA로 간주하지 않습니다. 검증된 연결 모델 없음.','source':'https://arxiv.org/abs/2509.18308'},
            {'id':'AI-10-A','name':'폐혈관·기도','status':'not_connected','requirements':['독립 lung_vessels 가중치/라이선스 확인','얇은 절편·정답 분할 평가'],'reason':'현재 기관/대동맥 해부학 분할과 구분. 혈관 폐색/협착 진단 기능 아님.','source':'https://github.com/wasserth/TotalSegmentator'},
            {'id':'AI-10-B','name':'심장방·대동맥 정량화','status':'not_connected','requirements':['heartchambers_highres 별도 라이선스/가중치','sub-mm 영상·계측 기준·심장 주기/정답 평가'],'reason':'심장 전체 부피를 심장방별 기능/질환 판정으로 바꾸지 않습니다.','source':'https://github.com/wasserth/TotalSegmentator'},
            {'id':'AI-10-C','name':'림프절·침윤·기종·기흉 등 추가 소견','status':'not_supported','requirements':['소견별 개별 모델·출력·정답·성능 기준 정의'],'reason':'모든 흉부 질환을 탐지하는 단일 연결 모델은 없습니다.','source':'https://github.com/wasserth/TotalSegmentator'}]}
    return router
