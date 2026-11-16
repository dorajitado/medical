"""Local CT intake and manually entered report storage. No inference yet."""
from contextlib import asynccontextmanager
import asyncio
import json
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .intake import register_file, record_result
from .models import model_registry
from .storage import Store
from .geometry import GeometryError, validate_series, probe, distance
from .native_imaging import NativeImaging
from .analysis import AnalysisManager
from .analysis_runtime import runtime_status
from .workflow_api import create_workflow_router
from .maintenance_api import create_maintenance_router
from .extended_api import create_extended_router
from .ct_review_api import create_ct_review_router

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ORIGINS = {'http://127.0.0.1:5173', 'http://localhost:5173', 'http://127.0.0.1:8000', 'http://localhost:8000'}
MAX_FILE_BYTES = 32 * 1024 * 1024

class Preferences(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    show_structure: bool = True

class NewImport(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    total: int = Field(ge=1, le=100000)

class ReportInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    text: str = Field(min_length=1, max_length=100000)
    source: str = Field(pattern='^(hospital_transcription|personal_note|user_authored)$')

class ProbeInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    z: int = Field(ge=0)

class DistanceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    start: tuple[int,int,int]
    end: tuple[int,int,int]

class AnalysisInput(BaseModel):
    """No paths, arbitrary model arguments, or report text cross this boundary."""
    model_config = ConfigDict(extra='forbid', strict=True)
    model_id: str = Field(pattern='^(total|lung_nodules|pleural_pericard_effusion|monai_nodule)$')
    confirmed: bool

def create_app(data_dir: Path = ROOT / 'data', allowed_origins: set[str] | None = None, imaging_path: Path | None = None, analysis_enabled: bool = True) -> FastAPI:
    store = Store(data_dir)
    imaging = NativeImaging(imaging_path or data_dir/'imaging'/'orthanc.json')
    origins = ALLOWED_ORIGINS if allowed_origins is None else allowed_origins
    import_lock = asyncio.Lock()
    mutation_lock = asyncio.Lock()
    analysis = AnalysisManager(store, enabled=analysis_enabled)
    @asynccontextmanager
    async def lifespan(app):
        store.initialize()
        try:
            yield
        finally:
            await run_in_threadpool(analysis.close)
    app = FastAPI(title='Chest Review Local API', version='0.7.0', lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost'])
    app.include_router(create_workflow_router(store,analysis))
    app.include_router(create_maintenance_router(store,imaging))
    app.include_router(create_extended_router(store,analysis))
    app.include_router(create_ct_review_router(store,analysis))

    @app.middleware('http')
    async def local_requests(request: Request, call_next):
        origin = request.headers.get('origin')
        if (origin and origin not in origins) or request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'detail': 'Request origin is not allowed'}, status_code=403)
        if request.method not in {'GET', 'HEAD', 'OPTIONS'} and request.headers.get('x-workspace-request') != '1':
            return JSONResponse({'detail': 'Workspace request header required'}, status_code=403)
        # Serialize browser mutations around backup/deletion snapshots. GPU
        # background tasks are separately checked by require_idle before them.
        if request.method not in {'GET','HEAD','OPTIONS'}:
            async with mutation_lock:
                response = await call_next(request)
        else:
            response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cross-Origin-Opener-Policy'] = 'same-origin'
        response.headers['Cross-Origin-Embedder-Policy'] = 'require-corp'
        return response

    @app.get('/api/health')
    def health():
        with store.connect() as c:
            c.execute('SELECT 1').fetchone()
        # Configured means install-time readiness, never an analysed/normal CT.
        return {'status': 'ready', 'storage': 'ready', 'version': app.version, 'imaging': 'configured' if imaging.path.exists() else 'not_connected', 'analysis': 'configured' if runtime_status()['ready'] else 'not_connected', 'intake': 'ready'}

    @app.get('/api/studies')
    def studies():
        with store.connect() as c:
            return {'items': [dict(r) for r in c.execute('SELECT id,study_date,description FROM studies ORDER BY created_at DESC,id')]}

    @app.get('/api/studies/{study_id}/series')
    def series(study_id: str):
        with store.connect() as c:
            require_study(c, study_id)
            result = []
            for row in c.execute('SELECT s.id,s.metadata,COUNT(i.id) AS instance_count FROM series s LEFT JOIN instances i ON i.series_id=s.id WHERE s.study_id=? GROUP BY s.id', (study_id,)):
                m = json.loads(row['metadata'])
                result.append({'id': row['id'], 'description': m['series_description'], 'instance_count': row['instance_count'], 'slice_thickness': m['slice_thickness'], 'contrast_agent': m['contrast_agent'], 'validation': 'metadata_only', 'ctpa': 'unknown', 'convolution_kernel':m.get('convolution_kernel'), 'image_type':m.get('image_type',[]), 'reconstruction_diameter':m.get('reconstruction_diameter')})
            return {'items': result}

    @app.get('/api/preferences', response_model=Preferences)
    def preferences():
        with store.connect() as c:
            return Preferences(show_structure=bool(c.execute('SELECT show_structure FROM preferences WHERE id=1').fetchone()[0]))

    @app.put('/api/preferences', response_model=Preferences)
    def save_preferences(value: Preferences):
        with store.connect() as c:
            c.execute('UPDATE preferences SET show_structure=? WHERE id=1', (int(value.show_structure),))
        return value

    @app.get('/api/models')
    def models():
        return {'items': model_registry()}

    def analysis_call(function, *args):
        """Translate only known user-facing failures, keeping internal paths private."""
        try:
            return function(*args)
        except KeyError:
            raise HTTPException(404, '시리즈 또는 분석 실행을 찾을 수 없습니다.')
        except GeometryError as exc:
            raise HTTPException(422, str(exc))
        except (OSError, ValueError):
            raise HTTPException(422, '분석 파일이 없거나 손상되었습니다. 새 실행이 필요합니다.')

    @app.get('/api/series/{series_id}/analysis-eligibility')
    def analysis_eligibility(series_id: str, model_id: str = 'total'):
        return analysis_call(analysis.eligibility, series_id, model_id)

    @app.get('/api/series/{series_id}/analyses')
    def analysis_runs(series_id: str):
        return {'items': analysis.list(series_id)}

    @app.post('/api/series/{series_id}/analyses', status_code=201)
    def create_analysis(series_id: str, value: AnalysisInput):
        return analysis_call(analysis.enqueue, series_id, value.confirmed, value.model_id)

    @app.post('/api/analyses/{run_id}/cancel')
    def cancel_analysis(run_id: str):
        return analysis_call(analysis.cancel, run_id)

    @app.get('/api/analyses/{run_id}/result')
    def analysis_result(run_id: str):
        return analysis_call(analysis.result, run_id)

    @app.get('/api/analyses/{run_id}/slices/{z}')
    def analysis_slice(run_id: str, z: int):
        return analysis_call(analysis.slice, run_id, z)

    @app.get('/api/analyses/{run_id}/surfaces')
    def analysis_surfaces(run_id: str):
        return analysis_call(analysis.surfaces, run_id)

    @app.get('/api/imports')
    def imports():
        with store.connect() as c:
            return {'items': [dict(row) for row in c.execute('SELECT * FROM import_jobs ORDER BY created_at DESC,rowid DESC LIMIT 30')]}

    @app.post('/api/imports', status_code=201)
    def create_import(value: NewImport):
        jid = str(uuid4())
        with store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute("SELECT id FROM import_jobs WHERE status='running'").fetchone():
                raise HTTPException(409, '다른 등록 작업이 진행 중입니다.')
            c.execute("INSERT INTO import_jobs(id,status,total) VALUES (?,'running',?)", (jid, value.total))
        return {'id': jid}

    def job_row(c, jid):
        row = c.execute('SELECT * FROM import_jobs WHERE id=?', (jid,)).fetchone()
        if not row:
            raise HTTPException(404, '작업을 찾을 수 없습니다.')
        return row

    @app.post('/api/imports/{job_id}/files')
    async def upload_file(job_id: str, request: Request):
        async with import_lock:
            return await receive_file(job_id, request)

    async def receive_file(job_id: str, request: Request):
        with store.connect() as c:
            row = job_row(c, job_id)
            if row['status'] != 'running' or sum(row[k] for k in ['imported', 'duplicates', 'excluded', 'failed']) >= row['total']:
                raise HTTPException(409, '파일을 받을 수 없는 작업 상태입니다.')
        if request.headers.get('content-type') != 'application/octet-stream':
            raise HTTPException(415, '파일 바이트 전송이 필요합니다.')
        stage = store.root / 'staging' / (str(uuid4()) + '.part')
        size = 0
        try:
            with stage.open('xb') as out:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_FILE_BYTES:
                        return record_result(store, job_id, 'excluded', '파일당 32MB 등록 한도를 초과했습니다.')
                    out.write(chunk)
            return await run_in_threadpool(register_file, store, stage, job_id)
        finally:
            stage.unlink(missing_ok=True)

    @app.post('/api/imports/{job_id}/{action}')
    def finish_import(job_id: str, action: str):
        if action not in {'finish', 'cancel'}:
            raise HTTPException(404, '지원하지 않는 작업입니다.')
        with store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = job_row(c, job_id)
            if row['status'] != 'running':
                raise HTTPException(409, '진행 중인 작업이 아닙니다.')
            if action == 'finish' and sum(row[k] for k in ['imported', 'duplicates', 'excluded', 'failed']) != row['total']:
                raise HTTPException(409, '처리하지 않은 파일이 남아 있습니다.')
            c.execute('UPDATE import_jobs SET status=? WHERE id=?', ('completed' if action == 'finish' else 'cancelled', job_id))
        return {'status': 'completed' if action == 'finish' else 'cancelled'}

    def require_study(c, study_id):
        if not c.execute('SELECT id FROM studies WHERE id=?', (study_id,)).fetchone():
            raise HTTPException(404, '검사를 찾을 수 없습니다.')

    @app.get('/api/studies/{study_id}/reports')
    def reports(study_id: str):
        with store.connect() as c:
            require_study(c, study_id)
            return {'items': [dict(r) for r in c.execute('SELECT * FROM report_versions WHERE study_id=? ORDER BY created_at DESC,rowid DESC', (study_id,))]}

    @app.post('/api/studies/{study_id}/reports', status_code=201)
    def save_report(study_id: str, value: ReportInput):
        if not value.text.strip():
            raise HTTPException(422, '내용을 입력해 주세요.')
        rid = str(uuid4())
        with store.connect() as c:
            require_study(c, study_id)
            c.execute('INSERT INTO report_versions(id,study_id,source,text) VALUES (?,?,?,?)', (rid, study_id, value.source, value.text))
            from .workflow import audit
            audit(c,'report_version_created',rid,study_id,{'source':value.source})
        return {'id': rid}

    @app.get('/api/imaging/status')
    def imaging_status():
        return imaging.status()

    @app.get('/api/series/{series_id}/geometry')
    def geometry(series_id: str):
        try:
            return validate_series(store,series_id)[0]
        except KeyError:
            raise HTTPException(404,'시리즈를 찾을 수 없습니다.')
        except GeometryError as exc:
            return {'supported':False,'reasons':[str(exc)],'series_id':series_id}

    def geometry_call(function,*args):
        try:
            return function(store,*args)
        except KeyError:
            raise HTTPException(404,'시리즈를 찾을 수 없습니다.')
        except GeometryError as exc:
            raise HTTPException(422,str(exc))

    @app.post('/api/series/{series_id}/probe')
    def voxel_probe(series_id: str, value: ProbeInput):
        return geometry_call(probe,series_id,value.x,value.y,value.z)

    @app.post('/api/series/{series_id}/distance')
    def voxel_distance(series_id: str,value: DistanceInput):
        return geometry_call(distance,series_id,value.start,value.end)

    @app.post('/api/series/{series_id}/open')
    def open_viewer(series_id: str):
        try:
            return imaging.open_series(store,series_id)
        except KeyError:
            raise HTTPException(404,'시리즈를 찾을 수 없습니다.')
        except GeometryError as exc:
            raise HTTPException(422,str(exc))
        except Exception:
            raise HTTPException(503,'로컬 영상 서비스에 연결하지 못했습니다. start-imaging.ps1 실행 상태를 확인해 주세요.')

    @app.get('/imaging/{path:path}')
    def imaging_proxy(path: str,request: Request):
        # Expose read-only viewer/DICOMweb, never Orthanc admin or arbitrary URLs.
        if not (path.startswith('ohif/') or path=='dicom-web/studies' or path.startswith('dicom-web/studies/')) or '..' in path or '\\' in path:
            raise HTTPException(404,'지원하지 않는 영상 경로입니다.')
        try:
            with imaging.client() as client:
                response = client.get('/'+path,params=request.query_params,
                                      headers={'Accept':request.headers.get('accept','*/*')})
            return Response(content=response.content,status_code=response.status_code,
                            headers={'Content-Type':response.headers.get('content-type','application/octet-stream')})
        except Exception:
            raise HTTPException(503,'영상 서비스 연결 실패')

    if (ROOT / 'dist' / 'index.html').is_file():
        app.mount('/', StaticFiles(directory=ROOT / 'dist', html=True), name='frontend')
    return app

app = create_app()
