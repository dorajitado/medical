"""Managed backup verification/restoration and bounded study removal.

Only UUID-derived paths inside this workspace are mutable. Backups exclude the
rebuildable Orthanc cache, model runtimes and logs, but include original DICOM,
documents, derived results, SQLite versions/reviews and source provenance.
"""
import hashlib
from contextlib import closing
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import socket
import sqlite3
from uuid import uuid4
import zipfile

from .workflow import audit

DIRECTORIES=('originals','analysis','documents','exports')
MAX_BACKUP_BYTES=100*1024**3


def stream_hash(source):
    """Bound memory even for multi-gigabyte model outputs or ZIP members."""
    digest=hashlib.sha256()
    while chunk:=source.read(1024*1024): digest.update(chunk)
    return digest.hexdigest()


def managed(root,path):
    """Resolve immediately before each mutation; never follow a workspace link."""
    root=root.resolve();path=Path(path)
    resolved=path.resolve()
    if resolved==root or not resolved.is_relative_to(root) or any(p.is_symlink() for p in [path,*path.parents] if p!=root and p.is_relative_to(root)):
        raise ValueError('앱 관리 저장 경로를 벗어났습니다.')
    return resolved


def require_idle(store):
    with store.connect() as c:
        if c.execute("SELECT 1 FROM analysis_runs WHERE status IN ('queued','running')").fetchone() or c.execute("SELECT 1 FROM import_jobs WHERE status='running'").fetchone() or c.execute("SELECT 1 FROM source_documents WHERE status='running'").fetchone():
            raise ValueError('진행 중인 등록/분석/문서 처리를 완료하거나 취소한 뒤 실행해 주세요.')


def backup_path(store,identifier):
    if not re.fullmatch(r'[0-9a-f-]{36}',identifier): raise ValueError('백업 식별자가 유효하지 않습니다.')
    return managed(store.root,store.root/'backups'/f'{identifier}.zip')


def create_backup(store):
    require_idle(store)
    identifier=str(uuid4());directory=managed(store.root,store.root/'backups');directory.mkdir(exist_ok=True)
    stage=managed(store.root,store.root/'staging'/f'{identifier}.backup');stage.mkdir()
    try:
        # SQLite online backup yields a consistent DB, including committed WAL.
        database=stage/'workspace.sqlite3'
        with store.connect() as source, closing(sqlite3.connect(database)) as destination: source.backup(destination)
        files=[('workspace.sqlite3',database)]
        for name in DIRECTORIES:
            folder=store.root/name
            if folder.exists():
                for file in sorted(folder.rglob('*')):
                    if file.is_file(): files.append((file.relative_to(store.root).as_posix(),managed(store.root,file)))
        total=sum(file.stat().st_size for _,file in files)
        if len(files)>200000 or total>MAX_BACKUP_BYTES: raise ValueError('초기 백업 파일/100 GiB 한도를 초과했습니다.')
        if shutil.disk_usage(store.root).free<total+256*1024**2: raise ValueError('백업을 위한 여유 디스크 공간이 부족합니다.')
        entries=[]
        final=backup_path(store,identifier);target=stage/'archive.zip'
        with zipfile.ZipFile(target,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as archive:
            for name,file in files:
                with file.open('rb') as source: digest=stream_hash(source)
                entries.append({'path':name,'bytes':file.stat().st_size,'sha256':digest})
                archive.write(file,name)
            archive.writestr('manifest.json',json.dumps({'schema':'ct-backup-1','id':identifier,'files':entries,
                                                       'scope':'SQLite + original DICOM/documents + analysis/exports; Orthanc cache rebuilt'},ensure_ascii=False))
        # Publish only a fully closed, verified archive. Partial ZIPs never appear
        # in the browser backup list after disk/permission/process failures.
        verify_backup(target);target.replace(final)
        with store.connect() as c: audit(c,'backup_created',identifier,details={'file_count':len(entries)})
        return {'id':identifier,'file_count':len(entries),'bytes':final.stat().st_size,'scope':'원본/분석/문서/검토 DB 포함; 모델·영상 캐시·기존 백업 제외'}
    finally:
        if stage.exists(): shutil.rmtree(managed(store.root,stage))


def verify_backup(path):
    """Reject zip-slip, symlink, duplicate/extra files, bombs and changed bytes."""
    with zipfile.ZipFile(path) as archive:
        infos=archive.infolist(); names=[i.filename for i in infos]
        if len(names)>200001 or len(names)!=len(set(names)) or 'manifest.json' not in names or sum(i.file_size for i in infos)>MAX_BACKUP_BYTES:
            raise ValueError('백업 구조 또는 크기 한도가 유효하지 않습니다.')
        if archive.getinfo('manifest.json').file_size>64*1024**2: raise ValueError('백업 목록 크기를 초과했습니다.')
        manifest=json.loads(archive.read('manifest.json'))
        if manifest.get('schema')!='ct-backup-1' or not isinstance(manifest.get('files'),list): raise ValueError('지원하지 않는 백업 형식입니다.')
        expected={f['path']:f for f in manifest['files']}
        if len(expected)!=len(manifest['files']): raise ValueError('중복 백업 항목입니다.')
        if set(names)!={*expected,'manifest.json'} or 'workspace.sqlite3' not in expected: raise ValueError('백업 목록이 실제 파일과 다릅니다.')
        for info in infos:
            name=PurePosixPath(info.filename)
            if name.is_absolute() or '..' in name.parts or '\\' in info.filename or ':' in info.filename or (info.external_attr>>16)&0o170000==0o120000:
                raise ValueError('백업에 허용되지 않는 경로/링크가 있습니다.')
            if info.filename=='manifest.json': continue
            if name.parts[0] not in {*DIRECTORIES,'workspace.sqlite3'}: raise ValueError('앱 관리 파일 범위가 아닙니다.')
            with archive.open(info) as source: digest=stream_hash(source)
            if info.file_size!=expected[info.filename]['bytes'] or digest!=expected[info.filename]['sha256']:
                raise ValueError('백업 파일의 크기/해시가 일치하지 않습니다.')
        return manifest


def restore_backup(store,identifier,confirmation,check_ports=True):
    """Offline restore into managed directories, with rollback of replaced data.

    This is CLI-only: both app and native imaging must be stopped. Existing data
    are first moved into a named recovery directory, never recursively replaced
    across arbitrary client paths. The user sees this scope before confirming.
    """
    if confirmation!='RESTORE '+identifier: raise ValueError('백업 식별자를 포함한 복원 확인이 필요합니다.')
    if check_ports:
        for port in [8000,8042]:
            with socket.socket() as probe:
                if probe.connect_ex(('127.0.0.1',port))==0: raise ValueError('앱과 영상 서비스를 종료한 뒤 복원해 주세요.')
    require_idle(store)
    path=backup_path(store,identifier);manifest=verify_backup(path)
    stage=managed(store.root,store.root/'staging'/f'{uuid4()}.restore');stage.mkdir()
    recovery=managed(store.root,store.root/'recovery'/str(uuid4()));recovery.mkdir(parents=True)
    moved=[];installed=[]
    try:
        with zipfile.ZipFile(path) as archive:
            for item in manifest['files']:
                target=managed(stage,stage/item['path']);target.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(item['path']) as source,target.open('xb') as destination: shutil.copyfileobj(source,destination)
        with closing(sqlite3.connect(stage/'workspace.sqlite3')) as c:
            if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or c.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('복원 DB의 무결성 검증에 실패했습니다.')
        for name in ['workspace.sqlite3','workspace.sqlite3-wal','workspace.sqlite3-shm','workspace.sqlite3-journal',*DIRECTORIES,'imaging','trash']:
            original=store.root/name
            if original.exists():
                original=managed(store.root,original);saved=managed(store.root,recovery/name)
                original.replace(saved);moved.append((original,saved))
        for name in ['workspace.sqlite3',*DIRECTORIES]:
            source=stage/name
            if source.exists():
                target=managed(store.root,store.root/name);source.replace(target);installed.append(target)
        # Record restoration only after SQLite integrity and all file moves pass.
        store.initialize()
        with store.connect() as c: audit(c,'backup_restored',identifier,details={'recovery':recovery.name})
        return {'status':'restored','backup_id':identifier,'recovery_id':recovery.name,'imaging':'rebuild_from_originals'}
    except Exception:
        for target in installed:
            if target.exists():
                if target.is_dir(): shutil.rmtree(managed(store.root,target))
                else: managed(store.root,target).unlink()
        for original,saved in moved:
            if saved.exists(): managed(store.root,saved).replace(managed(store.root,original))
        raise
    finally:
        if stage.exists(): shutil.rmtree(managed(store.root,stage))


def deletion_preview(store,study_id):
    with store.connect() as c:
        study=c.execute('SELECT id FROM studies WHERE id=?',(study_id,)).fetchone()
        if study is None: raise KeyError('검사가 없습니다.')
        originals=c.execute('SELECT COUNT(*) FROM instances i JOIN series s ON s.id=i.series_id WHERE s.study_id=?',(study_id,)).fetchone()[0]
        runs=c.execute('SELECT COUNT(*) FROM analysis_runs a JOIN series s ON s.id=a.series_id WHERE s.study_id=?',(study_id,)).fetchone()[0]
    return {'study_id':study_id,'original_instances':originals,'analysis_runs':runs,
            'confirmation':'DELETE '+study_id,'scope':'이 앱의 해당 검사 원본 복사본·분석·소견/검토·영상 미러 삭제. 선택했던 외부 CT 폴더와 기존 백업/복구 보관본은 유지.'}


def delete_study(store,study_id,confirmation,imaging=None):
    preview=deletion_preview(store,study_id)
    if confirmation!=preview['confirmation']: raise ValueError('검사 ID를 포함한 삭제 확인이 필요합니다.')
    require_idle(store)
    with store.connect() as c:
        uid=c.execute('SELECT study_uid FROM studies WHERE id=?',(study_id,)).fetchone()[0]
        originals=[r[0] for r in c.execute('SELECT i.stored_name FROM instances i JOIN series s ON s.id=i.series_id WHERE s.study_id=?',(study_id,))]
        runs=[r[0] for r in c.execute('SELECT a.id FROM analysis_runs a JOIN series s ON s.id=a.series_id WHERE s.study_id=?',(study_id,))]
        docs=[r[0] for r in c.execute('SELECT stored_name FROM source_documents WHERE study_id=?',(study_id,))]
    if imaging and imaging.path.exists():
        if not imaging.status()['ready']: raise ValueError('영상 미러 정리를 위해 로컬 영상 서비스를 실행해 주세요.')
        with imaging.client() as client:
            found=client.post('/tools/find',json={'Level':'Study','Query':{'StudyInstanceUID':uid}});found.raise_for_status()
            for identifier in found.json(): client.delete('/studies/'+identifier).raise_for_status()
    # Validate every final target before destructive work begins.
    targets=[managed(store.root,store.root/'originals'/name) for name in originals]
    targets += [managed(store.root,store.root/'analysis'/rid) for rid in runs]
    targets += [managed(store.root,store.root/'documents'/name) for name in docs]
    # Stage files before committing metadata removal. If a file is locked or the
    # DB transaction fails, restore every moved target. A committed cleanup can
    # be retried by journal ID without a now-deleted Study row.
    identifier=str(uuid4());trash=managed(store.root,store.root/'trash'/identifier);trash.mkdir(parents=True)
    moved=[]
    try:
        (trash/'deletion.json').write_text(json.dumps({'status':'staged','study_id':study_id,
            'moves':[{'original':target.relative_to(store.root.resolve()).as_posix(),'saved':str(index)} for index,target in enumerate(targets)]}),encoding='utf-8')
        for index,target in enumerate(targets):
            if target.exists():
                saved=managed(store.root,trash/str(index));target.replace(saved);moved.append((target,saved))
        with store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            for table in ['model_comparison_versions','summary_versions','review_versions','comparison_versions','extraction_versions','source_documents','report_versions']:
                c.execute(f'DELETE FROM {table} WHERE study_id=?',(study_id,))
            c.execute('DELETE FROM longitudinal_versions WHERE current_study=? OR prior_study=?',(study_id,study_id))
            c.execute('DELETE FROM evaluation_cases WHERE study_id=?',(study_id,))
            c.execute('DELETE FROM analysis_runs WHERE series_id IN (SELECT id FROM series WHERE study_id=?)',(study_id,))
            c.execute('DELETE FROM instances WHERE series_id IN (SELECT id FROM series WHERE study_id=?)',(study_id,))
            c.execute('DELETE FROM series WHERE study_id=?',(study_id,));c.execute('DELETE FROM studies WHERE id=?',(study_id,))
            audit(c,'study_deleted',study_id,details={'original_instances':len(originals),'analysis_runs':len(runs),'cleanup_id':identifier})
    except Exception:
        for target,saved in reversed(moved):
            if saved.exists(): saved.replace(managed(store.root,target))
        if trash.exists(): shutil.rmtree(managed(store.root,trash))
        raise
    try:
        cleanup_deleted(store,identifier)
        return {'status':'deleted','scope':preview['scope']}
    except OSError:
        return {'status':'cleanup_pending','cleanup_id':identifier,'scope':preview['scope'],
                'detail':'검사 메타데이터는 삭제되었지만 잠긴 파일 정리가 남았습니다. 파일을 닫고 정리를 재시도하세요.'}


def cleanup_deleted(store,identifier):
    """Delete only a committed UUID trash journal, never a caller-supplied path."""
    if not re.fullmatch(r'[0-9a-f-]{36}',identifier): raise ValueError('정리 식별자가 유효하지 않습니다.')
    target=managed(store.root,store.root/'trash'/identifier)
    journal=json.loads((target/'deletion.json').read_text(encoding='utf-8'))
    # SQLite is the commit authority, including a crash after the DB commit.
    with store.connect() as c:
        exists=c.execute('SELECT 1 FROM studies WHERE id=?',(journal['study_id'],)).fetchone()
        events=c.execute("SELECT details FROM audit_events WHERE action='study_deleted' AND entity_id=?",(journal['study_id'],)).fetchall()
    if exists or not any(json.loads(row['details']).get('cleanup_id')==identifier for row in events):
        raise ValueError('확정된 삭제 정리 작업이 아닙니다.')
    shutil.rmtree(target)
    with store.connect() as c: audit(c,'study_files_cleaned',identifier,details={'study_id':journal['study_id']})
    return {'status':'deleted','cleanup_id':identifier}


def recover_deletions(store):
    """Undo a pre-commit process crash using the durable bounded move journal.

    A post-commit deletion stays in the explicit pending-cleanup UI; no existing
    original is overwritten during recovery. Restore moves old trash aside.
    """
    for file in (store.root/'trash').glob('*/deletion.json'):
        file=managed(store.root,file);journal=json.loads(file.read_text(encoding='utf-8'))
        with store.connect() as c:exists=c.execute('SELECT 1 FROM studies WHERE id=?',(journal['study_id'],)).fetchone()
        if not exists:continue
        for move in reversed(journal.get('moves',[])):
            target=managed(store.root,store.root/move['original']);saved=managed(store.root,file.parent/move['saved'])
            if saved.exists():
                if target.exists():raise ValueError('삭제 복구 파일이 충돌했습니다. 원본을 덮어쓰지 않았습니다.')
                target.parent.mkdir(parents=True,exist_ok=True);saved.replace(target)
        shutil.rmtree(managed(store.root,file.parent))
        with store.connect() as c:audit(c,'interrupted_deletion_rolled_back',journal['study_id'],journal['study_id'])

