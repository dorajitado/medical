"""Candidate registry; no model is executable until its adapter and weights are verified."""
from importlib.metadata import PackageNotFoundError, version


def model_registry():
    try:
        installed = version('TotalSegmentator')
    except PackageNotFoundError:
        installed = None
    tasks = [
        ('total', '해부학 구조', '다양한 CT 조건 대상. 분할 결과는 질환 판정이 아닙니다.'),
        ('lung_nodules', '폐결절 후보', '조영 CT에서의 별도 성능 확인이 필요합니다. 악성 확률을 출력하지 않습니다.'),
        ('pleural_pericard_effusion', '흉수·심낭삼출 후보', '작은 별도 학습 자료의 한계를 확인해야 합니다.'),
    ]
    return [{'id': task, 'name': f'TotalSegmentator / {task}', 'target': label,
             'package_version': installed, 'weights_version': None, 'weights_sha256': None,
             'configuration_version': 'candidate-1', 'status': 'not_configured' if installed else 'not_installed',
             'executable': False, 'validation_status': 'not_evaluated', 'input': '3D CT; 시리즈 적합성 확인 필요',
             'license': 'Apache-2.0 (해당 공개 task; 가중치 연결 시 재확인)',
             'source': 'https://github.com/wasserth/TotalSegmentator#subtasks', 'limitation': limitation}
            for task, label, limitation in tasks]
