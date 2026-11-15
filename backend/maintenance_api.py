"""Loopback maintenance endpoints; restore itself is deliberately offline."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict
from .maintenance import backup_path, create_backup, verify_backup, deletion_preview, delete_study, cleanup_deleted


class Confirm(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    confirmation:str


def create_maintenance_router(store,imaging):
    router=APIRouter(prefix='/api/maintenance')
    def call(function,*args):
        try:return function(*args)
        except KeyError:raise HTTPException(404,'관리 대상을 찾을 수 없습니다.')
        except (ValueError,OSError) as exc:raise HTTPException(422,str(exc) if isinstance(exc,ValueError) else '관리 파일 접근에 실패했습니다.')

    @router.get('/backups')
    def backups():
        folder=store.root/'backups'
        return {'items':[{'id':p.stem,'bytes':p.stat().st_size} for p in sorted(folder.glob('*.zip'),key=lambda p:p.stat().st_mtime,reverse=True)]}

    @router.post('/backups',status_code=201)
    def backup():return call(create_backup,store)

    @router.post('/backups/{identifier}/verify')
    def verify(identifier:str):
        manifest=call(verify_backup,call(backup_path,store,identifier))
        return {'status':'verified','id':identifier,'file_count':len(manifest['files']),
                'restore_instruction':f'앱/영상 서비스 종료 후 restore-backup.ps1 -BackupId {identifier} 실행. 확인 입력 RESTORE {identifier}',
                'scope':'현재 앱 작업 공간을 교체하고 기존 데이터/영상 캐시는 recovery에 보존. 외부 원본 폴더·모델·기존 백업은 유지.'}

    @router.get('/backups/{identifier}/download')
    def download(identifier:str):
        path=call(backup_path,store,identifier)
        if not path.is_file():raise HTTPException(404,'백업이 없습니다.')
        # FileResponse streams without loading a potentially large archive into RAM.
        from fastapi.responses import FileResponse
        return FileResponse(path,media_type='application/zip',filename=f'{identifier}.zip')

    @router.get('/studies/{study_id}/delete-preview')
    def preview(study_id:str):return call(deletion_preview,store,study_id)

    @router.post('/studies/{study_id}/delete')
    def delete(study_id:str,value:Confirm):return call(delete_study,store,study_id,value.confirmation,imaging)

    @router.get('/pending-cleanup')
    def pending():
        # UUIDs are all the browser needs to retry; never expose filesystem paths.
        folder=store.root/'trash'
        return {'items':[{'id':p.parent.name} for p in folder.glob('*/deletion.json')]}

    @router.post('/pending-cleanup/{identifier}')
    def cleanup(identifier:str):return call(cleanup_deleted,store,identifier)
    return router
