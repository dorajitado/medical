"""Candidate registry; no model is executable until its adapter and weights are verified."""
from importlib.metadata import PackageNotFoundError, version
from .analysis_runtime import CONFIGURATION, CONFIGURATIONS, runtime_status


def model_registry():
    try:
        installed = version('TotalSegmentator')
    except PackageNotFoundError:
        installed = None
    tasks = [
        ('total', '해부학 구조', '다양한 CT 조건 대상. 분할 결과는 질환 판정이 아닙니다.'),
        ('lung_nodules', '폐결절 후보', '조영 CT에서의 별도 성능 확인이 필요합니다. 악성 확률을 출력하지 않습니다.'),
        ('pleural_pericard_effusion', '흉수·심낭삼출 후보', '작은 별도 학습 자료의 한계를 확인해야 합니다.'),
        ('monai_nodule','MONAI 결절 탐지','LUNA16 기반 독립 탐지상자·모델 점수. 조영 CT 임상 성능은 미평가입니다.'),
    ]
    registry = [{'id': task, 'name': f'TotalSegmentator / {task}', 'target': label,
             'package_version': installed, 'weights_version': None, 'weights_sha256': None,
             'configuration_version': 'candidate-1', 'status': 'not_configured' if installed else 'not_installed',
             'executable': False, 'validation_status': 'not_evaluated', 'input': '3D CT; 시리즈 적합성 확인 필요',
             'license': 'Apache-2.0 (해당 공개 task; 가중치 연결 시 재확인)',
             'source': 'https://github.com/wasserth/TotalSegmentator#subtasks', 'limitation': limitation}
            for task, label, limitation in tasks]
    # Each adapter checks its own checkpoints, including the lung cropping model.
    # A present Python package alone never makes an uninstalled task executable.
    for entry in registry:
        task = entry['id']
        runtime = runtime_status(model_id=task)
        if not runtime['ready']:
            continue
        entry.update({'package_version': runtime.get('totalsegmentator',runtime.get('package_version')),
                            'weights_version': runtime['weights_id'],
                            'weights_sha256': runtime['weights_digest'],
                            'configuration_version': CONFIGURATIONS[task]['version'],
                            'status': 'ready', 'executable': True,
                            'validation_status': 'technical_only; clinical_not_evaluated',
                            'configuration': CONFIGURATIONS[task],
                            'limitation': ('폐엽 5개·기관·심장·대동맥의 3 mm 해부학 분할. 질환/정상 판정이 아닙니다.' if task == 'total'
                                           else entry['limitation'] + ' AI 후보이며 정상 판정·질환 배제가 아닙니다. 점수는 제공하지 않습니다.')})
        if task=='monai_nodule':
            entry.update({'name':'MONAI / lung_nodule_ct_detection','input':'3D CT; initial spacing ≤3 mm; model-specific RAS resampling',
                          'source':'https://huggingface.co/MONAI/lung_nodule_ct_detection',
                          'limitation':'독립 탐지상자이며 분할 크기/부피를 제공하지 않습니다. 모델 점수는 악성 확률이 아니며 다른 모델과 평균하지 않습니다.'})
    return registry
