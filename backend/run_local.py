"""Start the API and project-owned native imaging process, then stop owned children."""
import subprocess
import sys
from .native_imaging import ROOT, NativeImaging, configure, launch

if __name__=='__main__':
    native_process=None
    api_process=None
    interrupted=False
    try:
        if (ROOT/'runtime'/'orthanc'/'Orthanc.exe').is_file():
            config=configure(ROOT/'data'/'imaging')
            if not NativeImaging(config).status()['ready']:
                native_process=launch(config)
        else:
            print('Imaging runtime missing: run setup-imaging.ps1. Intake/report storage remains available.',flush=True)
        api_process=subprocess.Popen([sys.executable,'-m','uvicorn','backend.app:app','--host','127.0.0.1','--port','8000','--no-access-log'],cwd=str(ROOT))
        api_process.wait()
    except KeyboardInterrupt:
        interrupted=True
    finally:
        for child in [api_process,native_process]:
            if child is not None and child.poll() is None:
                child.terminate()
                child.wait(timeout=15)
    if not interrupted and api_process and api_process.returncode not in (0,None):
        sys.exit(api_process.returncode)
