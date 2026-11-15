"""Project-owned AI runtime inventory; installation is separate from inference."""
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AI_HOME = ROOT / 'runtime' / 'models'
AI_PYTHON = ROOT / 'runtime' / 'ai-venv' / 'Scripts' / 'python.exe'
CONFIGURATION = {'version': 'anatomy-fast-1', 'task': 'total', 'fast': True,
                 'device': 'gpu', 'model_spacing_mm': 3.0,
                 'retained_classes': [10, 11, 12, 13, 14, 16, 51, 52],
                 'network_access': 'blocked', 'report_input': False}

# Allowlisted adapters: callers cannot supply arbitrary nnUNet tasks or flags.
# Keep the old total configuration identifier so earlier run snapshots remain valid.
CONFIGURATIONS = {
    'total': CONFIGURATION,
    'lung_nodules': {'version': 'nodules-1', 'task': 'lung_nodules', 'fast': False,
                     'device': 'gpu', 'model_spacing_mm': 1.5, 'retained_classes': [2],
                     'network_access': 'blocked', 'report_input': False,
                     'component_connectivity': 26, 'score': 'not_provided'},
    'pleural_pericard_effusion': {'version': 'effusion-1', 'task': 'pleural_pericard_effusion', 'fast': False,
                                'device': 'gpu', 'model_spacing_mm': None, 'retained_classes': [2, 3],
                                'network_access': 'blocked', 'report_input': False, 'score': 'not_provided'},
    'monai_nodule':{'version':'monai-retinanet-1','task':'monai_nodule','device':'gpu','fast':False,
                    'roi_size':[192,192,96],'score_threshold':.02,'nms_threshold':.22,'network_access':'blocked',
                    'report_input':False,'representation':'detection_boxes_not_segmentation'},
}


def runtime_status(home=AI_HOME, python=AI_PYTHON, verify=False, model_id='total'):
    """A manifest alone is insufficient: all declared weights must still exist.

    Full SHA-256 verification occurs before each run; lightweight polling checks
    sizes to avoid hashing hundreds of megabytes every few seconds in the UI.
    """
    try:
        if model_id=='monai_nodule':
            folder=ROOT/'runtime'/'monai-bundle'
            manifest=json.loads((folder/'manifest.json').read_text())
            for entry in manifest['files']:
                path=(folder/entry['path']).resolve()
                if not path.is_relative_to(folder.resolve()) or not path.is_file() or path.stat().st_size!=entry['bytes'] or (verify and hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']):
                    raise ValueError('MONAI files changed')
            package=python.parent.parent/'Lib'/'site-packages'/'monai'/'__init__.py'
            if not package.is_file():raise ValueError('MONAI package missing')
            return {'ready':True,'reason':None,'model_id':model_id,'package_version':'MONAI 1.5.1',
                    'weights_id':manifest['repository']+'@'+manifest['commit'], 'weights_digest':hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest(),
                    'weights_files':manifest['files'],'license':'Apache-2.0','manifest':manifest}
        manifest = json.loads((home / 'manifest.json').read_text(encoding='utf-8'))
        if model_id not in CONFIGURATIONS:
            raise ValueError('unknown adapter')
        if not python.is_file() or manifest['totalsegmentator'] != '2.18.0' or not manifest['cuda_available']:
            raise ValueError('runtime mismatch')
        # An old manifest must not keep a removed package marked executable.
        packages = python.parent.parent / 'Lib' / 'site-packages'
        if not (packages / 'totalsegmentator' / 'python_api.py').is_file() or not (packages / 'torch' / '__init__.py').is_file():
            raise ValueError('runtime package missing')
        # v1 manifests contain only anatomy. v2 inventories each task and its
        # required crop-model checkpoint independently; missing tasks stay unavailable.
        entry = manifest.get('models', {}).get(model_id)
        if entry is None and model_id != 'total':
            raise ValueError('task weights not installed')
        entry = entry or manifest
        files = entry['weights_files']
        if not files or not any(f['path'].endswith('.pth') for f in files):
            raise ValueError('missing checkpoint')
        for item in files:
            path = (home / item['path']).resolve()
            if not path.is_relative_to(home.resolve()) or not path.is_file() or path.stat().st_size != item['bytes']:
                raise ValueError('missing or changed weights')
            if verify and hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
                raise ValueError('weights hash mismatch')
        common = {k: v for k, v in manifest.items() if k != 'models'}
        return {**common, **entry, 'model_id': model_id, 'ready': True, 'reason': None}
    except (OSError, ValueError, KeyError, TypeError):
        return {'ready': False, 'reason': '모델 환경 또는 가중치가 준비되지 않았습니다. setup-ai.ps1을 실행해 주세요.'}


def inference_environment():
    """Disable telemetry and keep model files, temporary files and imports local.

    sitecustomize propagates the network guard into Windows spawned workers.
    Ordinary loopback IPC remains permitted for multiprocessing.
    """
    env = os.environ.copy()
    env.update({'TOTALSEG_HOME_DIR': str(AI_HOME), 'TOTALSEG_WEIGHTS_PATH': str(AI_HOME / 'weights'),
                'DO_NOT_TRACK': '1', 'HF_HUB_OFFLINE': '1', 'OMP_NUM_THREADS': '4',
                'nnUNet_compile': 'false', 'CHEST_OFFLINE_INFERENCE': '1',
                'PYTHONPATH': str(ROOT / 'backend' / 'offline') + os.pathsep + str(ROOT)})
    return env
