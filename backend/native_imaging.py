"""Project-local Windows Orthanc/OHIF; credentials never enter the browser."""
import json
from pathlib import Path
import secrets
import subprocess
import time
from urllib.parse import urlencode
import httpx
from .geometry import source_path, validate_series
from .storage import Store

ROOT = Path(__file__).resolve().parents[1]

def configure(root: Path, port=8042, public_port=8000):
    root.mkdir(parents=True,exist_ok=True)
    path = root/'orthanc.json'
    if path.exists():
        return path
    native = ROOT/'runtime'/'orthanc'
    for name in ['Orthanc.exe','OrthancDicomWeb.dll','OrthancOHIF.dll']:
        if not (native/name).is_file():
            raise FileNotFoundError('Run setup-imaging.ps1 first')
    config = {
        'Name':'Chest Review Local', 'StorageDirectory':str((root/'storage').resolve()),
        'IndexDirectory':str((root/'index').resolve()), 'HttpPort':port,
        'DicomServerEnabled':False,'RemoteAccessAllowed':False,'AuthenticationEnabled':True,
        'RegisteredUsers':{'workspace':secrets.token_urlsafe(36)},
        'Plugins':[str((native/n).resolve()) for n in ['OrthancDicomWeb.dll','OrthancOHIF.dll']],
        'OHIF':{'DataSource':'dicom-web','RouterBasename':'/imaging/ohif/'},
        'DicomWeb':{'Enable':True,'Root':'/dicom-web/','PublicRoot':'/imaging/dicom-web/',
                    'Host':f'127.0.0.1:{public_port}','Ssl':False},
        'HttpCompressionEnabled':False,
    }
    path.write_text(json.dumps(config,indent=2),encoding='utf-8')
    return path

class NativeImaging:
    def __init__(self,path: Path):
        self.path = path

    def config(self):
        if not self.path.exists():
            raise RuntimeError('영상 서비스를 설치하고 실행해 주세요.')
        return json.loads(self.path.read_text(encoding='utf-8-sig'))

    def client(self):
        c = self.config()
        return httpx.Client(base_url=f"http://127.0.0.1:{int(c['HttpPort'])}",
                            auth=('workspace',c['RegisteredUsers']['workspace']),
                            timeout=60,trust_env=False,follow_redirects=False)

    def status(self):
        try:
            with self.client() as client:
                response = client.get('/system')
                response.raise_for_status()
                return {'ready':True,'orthanc_version':response.json()['Version'],'mode':'windows_native'}
        except Exception:
            return {'ready':False,'mode':'windows_native','reason':'로컬 영상 서비스가 실행되지 않았습니다.'}

    def open_series(self,store: Store,series_id: str):
        info,rows,metadata = validate_series(store,series_id)
        with self.client() as client:
            for row in rows:
                response = client.post('/instances',content=source_path(store,row['stored_name']).read_bytes(),headers={'Content-Type':'application/dicom'})
                response.raise_for_status()
        query = urlencode({'StudyInstanceUIDs':metadata[0]['study_uid'], 'SeriesInstanceUIDs':metadata[0]['series_uid']})
        return {'url':'/imaging/ohif/viewer?'+query, 'geometry':info}

def launch(config_path: Path):
    native = NativeImaging(config_path)
    if native.status()['ready']:
        raise RuntimeError('영상 서버가 이미 실행 중입니다. 중복 실행하지 않습니다.')
    with (config_path.parent/'service.log').open('ab') as output:
        process = subprocess.Popen([str(ROOT/'runtime'/'orthanc'/'Orthanc.exe'),str(config_path)],
                                   cwd=str(ROOT),stdout=output,stderr=output,
                                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    for _ in range(60):
        if process.poll() is not None:
            raise RuntimeError('영상 서버 시작 실패. 로컬 service.log를 확인하세요.')
        if native.status()['ready']:
            return process
        time.sleep(.25)
    process.terminate()
    process.wait(timeout=10)
    raise RuntimeError('영상 서버 시작 시간 초과')
