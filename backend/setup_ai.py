"""Install-time only model download and reproducibility inventory.

Run with the project AI interpreter, after installing pinned requirements. No
user images are read. Later inference refuses downloads and verifies hashes.
"""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    home = root / 'runtime' / 'models'
    home.mkdir(parents=True, exist_ok=True)
    os.environ['TOTALSEG_HOME_DIR'] = str(home)
    os.environ['TOTALSEG_WEIGHTS_PATH'] = str(home / 'weights')
    # Explicitly disable telemetry BEFORE importing/calling TotalSegmentator.
    (home / 'config.json').write_text(json.dumps({'totalseg_id': 'local-workspace', 'send_usage_stats': False,
                                                'prediction_counter': 0, 'statistics_disclaimer_shown': True}), encoding='utf-8')
    import torch
    from totalsegmentator.libs import download_pretrained_weights
    from totalsegmentator.map_tasks_config import TASK_ID_WEIGHTS_CONFIGS
    # Both lesion tasks use a separate 6 mm lung cropping model. Download it
    # now, never when a patient's volume is being processed under the guard.
    tasks = {'total': [297], 'lung_nodules': [913, 298], 'pleural_pericard_effusion': [315, 298]}
    for task_id in sorted({i for ids in tasks.values() for i in ids}):
        download_pretrained_weights(task_id)
    models = {}
    for model_id, task_ids in tasks.items():
        files = []
        for task_id in sorted(task_ids):
            directory = home / 'weights' / TASK_ID_WEIGHTS_CONFIGS[task_id]['foldername']
            for file in sorted(directory.rglob('*')):
                if file.is_file():
                    files.append({'path': file.relative_to(home).as_posix(), 'bytes': file.stat().st_size,
                                  'sha256': hashlib.sha256(file.read_bytes()).hexdigest()})
        digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
        models[model_id] = {'weights_id': '; '.join(f"{TASK_ID_WEIGHTS_CONFIGS[i]['foldername']} / {TASK_ID_WEIGHTS_CONFIGS[i]['version']}" for i in task_ids),
                            'weights_digest': digest, 'weights_files': files}
    tracked = root / 'ai-weights-lock.json'
    # A subsequent installation must reproduce the reviewed weights exactly.
    old_lock = json.loads(tracked.read_text()) if tracked.exists() else {}
    old_models = old_lock.get('models', {'total': old_lock} if old_lock else {})
    for model_id, previous in old_models.items():
        if previous['weights_digest'] != models[model_id]['weights_digest']:
            raise RuntimeError(f'{model_id} weights differ from ai-weights-lock.json; installation is not ready.')
    manifest = {'totalsegmentator': importlib.metadata.version('TotalSegmentator'), 'torch': torch.__version__,
                'nnunetv2': importlib.metadata.version('nnunetv2'), 'cuda_available': torch.cuda.is_available(),
                'gpu': torch.cuda.get_device_name() if torch.cuda.is_available() else None,
                **models['total'], 'models': models, 'license': 'Apache-2.0',
                'source': 'https://github.com/wasserth/TotalSegmentator'}
    (home / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    tracked.write_text(json.dumps({**models['total'], 'models': models}, indent=2), encoding='utf-8')
    print(json.dumps({'totalsegmentator': manifest['totalsegmentator'], 'cuda_available': manifest['cuda_available'],
                      'models': {k: {'weights_digest': v['weights_digest']} for k, v in models.items()}}, indent=2))


if __name__ == '__main__':
    main()
