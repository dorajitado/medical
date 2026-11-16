"""Source-grid conversion and restoration, independent from the neural network.

Array axes are X(column), Y(row), Z(physically sorted slice). DICOM positions
are LPS millimetres; NIfTI affines are RAS millimetres. No axis guesses based
on filenames, InstanceNumber, or report text are permitted here.
"""
import hashlib
import json
from pathlib import Path

import nibabel as nib
from nibabel.processing import resample_from_to
import numpy as np
import pydicom
from itertools import product

from .geometry import GeometryError, patient_point, source_path, validate_series

# Initial resource boundary protects the API from unbounded 4-D/enormous inputs.
MAX_VOXELS = 160_000_000
STRUCTURES = {
    10: ('lung_upper_lobe_left', '왼쪽 위폐엽', '#5da9e9'),
    11: ('lung_lower_lobe_left', '왼쪽 아래폐엽', '#536dce'),
    12: ('lung_upper_lobe_right', '오른쪽 위폐엽', '#ed8b8b'),
    13: ('lung_middle_lobe_right', '오른쪽 중간폐엽', '#e5ac63'),
    14: ('lung_lower_lobe_right', '오른쪽 아래폐엽', '#c96d91'),
    16: ('trachea', '기관', '#65bdab'),
    51: ('heart', '심장', '#e55c67'),
    52: ('aorta', '대동맥', '#eac758'),
}

# Auxiliary lung labels emitted by the task are deliberately not lesion labels.
# Their class IDs are local to each task and must never be interpreted using total.
TASK_STRUCTURES = {
    'total': STRUCTURES,
    'lung_nodules': {2: ('lung_nodules', '폐결절 후보', '#f28b71')},
    'pleural_pericard_effusion': {
        2: ('pleural_effusion', '흉수 후보 영역', '#52b8dc'),
        3: ('pericardial_effusion', '심낭삼출 후보 영역', '#c694e7'),
    },
}


def source_digest(sources):
    """Canonical instance/content identity shared by batches and restored output.

    IDs remain local; their digest is safe for an audit reference. Sorting makes
    identity independent of import order without removing slice provenance.
    """
    pairs = sorted((dict(row).get('instance_id', dict(row).get('id')), row['sha256']) for row in sources)
    if not pairs or any(not identifier or not digest for identifier, digest in pairs):
        raise GeometryError('분석 원본 출처가 비어 있습니다.')
    return hashlib.sha256(json.dumps(pairs, separators=(',', ':')).encode()).hexdigest()


def affine_ras(info):
    """Map a zero-based source voxel centre into NIfTI RAS without reordering."""
    lps = np.eye(4)
    for axis, key in enumerate(('column_direction', 'row_direction', 'slice_normal')):
        lps[:3, axis] = np.array(info[key]) * info['spacing_xyz'][axis]
    lps[:3, 3] = info['origin']
    return np.diag([-1., -1., 1., 1.]) @ lps


def eligible(info, model_id='total'):
    """Require a supported 3-D grid; contrast tags alone never establish CTPA."""
    reasons = []
    if info['shape_xyz'][2] < 3:
        reasons.append('분할 분석에는 최소 3개의 연속 절편이 필요합니다.')
    if int(np.prod(info['shape_xyz'], dtype=np.int64)) > MAX_VOXELS:
        reasons.append('초기 분석 메모리 한도(1억 6천만 복셀)를 초과했습니다.')
    if info['shape_xyz'][2] >= 3:
        # The viewer tolerates small acquisition jitter. A NIfTI has one affine;
        # refuse accumulated drift instead of silently approximating slice origins.
        predicted = np.array(info['origin']) + np.arange(info['shape_xyz'][2])[:, None] * info['spacing_xyz'][2] * np.array(info['slice_normal'])
        if float(np.max(np.linalg.norm(np.array(info['positions']) - predicted, axis=1))) > .01:
            reasons.append('단일 NIfTI 격자로 표현할 수 없는 절편 위치 편차(0.01 mm 초과)가 있습니다.')
    # These are deliberately documented initial application limits, not claims
    # that a scanner protocol establishes diagnostic suitability or accuracy.
    limit = 3.0 if model_id in {'lung_nodules','monai_nodule'} else 5.0
    if model_id != 'total' and any(s is None or s > limit + 1e-4 for s in info['spacing_xyz']):
        reasons.append(f'이 모델의 초기 앱 지원은 각 축 간격 {limit:g} mm 이하 CT입니다. 임상 적합성 판정은 아닙니다.')
    return reasons


def convert_source(store, series_id, directory, model_id='total'):
    """Validate again at execution, convert per-slice rescale, snapshot provenance.

    Pixel padding is not tissue: replace it with air (-1024 HU) for the network,
    while retaining the originals and documenting this explicit substitution.
    """
    info, rows, metadata = validate_series(store, series_id)
    reasons = eligible(info, model_id)
    if reasons:
        raise GeometryError(' '.join(reasons))
    volume = np.empty(info['shape_xyz'], dtype=np.float32)
    sources = []
    for z, (row, meta) in enumerate(zip(rows, metadata)):
        path = source_path(store, row['stored_name'])
        ds = pydicom.dcmread(path)
        raw = ds.pixel_array
        hu = raw.astype(np.float32) * meta['slope'] + meta['intercept']
        padding = getattr(ds, 'PixelPaddingValue', None)
        if padding is not None:
            low, high = sorted([int(padding), int(getattr(ds, 'PixelPaddingRangeLimit', padding))])
            hu[(raw >= low) & (raw <= high)] = -1024
        if not np.all(np.isfinite(hu)):
            raise GeometryError('변환된 HU에 유효하지 않은 값이 있습니다.')
        volume[:, :, z] = hu.T
        sources.append({'instance_id': row['id'], 'sop_uid': row['sop_uid'], 'sha256': row['sha256']})
    affine = affine_ras(info)
    image = nib.Nifti1Image(volume, affine)
    image.set_sform(affine, code=1)
    image.set_qform(affine, code=1)
    nib.save(image, directory / 'input.nii.gz')
    with store.connect() as c:
        series = dict(c.execute('SELECT id,study_id,series_uid FROM series WHERE id=?', (series_id,)).fetchone())
    provenance = {**series, 'geometry': info, 'sources': sources,
                  'array_axes': 'XYZ: column,row,sorted slice', 'nifti_coordinate_system': 'RAS mm',
                  'affine_ras': affine.tolist(), 'affine_inverse': np.linalg.inv(affine).tolist(),
                  'hu_method': 'per-slice raw * RescaleSlope + RescaleIntercept; padding=-1024',
                  'input_sha256': hashlib.sha256((directory / 'input.nii.gz').read_bytes()).hexdigest()}
    (directory / 'source.json').write_text(json.dumps(provenance, ensure_ascii=False), encoding='utf-8')
    return provenance


def restore_output(directory: Path, model_id='total'):
    """Nearest-neighbour label restoration; floating labels/foreign classes fail.

    TotalSegmentator already restores its internal 3 mm grid. This additional
    explicit resampling handles a different valid model affine, and guarantees
    that volume and overlay refer to precisely the original voxel centres.
    """
    source = json.loads((directory / 'source.json').read_text(encoding='utf-8'))
    info = source['geometry']
    image = nib.load(directory / 'prediction.nii.gz')
    data = np.asanyarray(image.dataobj)
    catalog = TASK_STRUCTURES[model_id]
    max_label = {'total': 117, 'lung_nodules': 2, 'pleural_pericard_effusion': 3}[model_id]
    if data.ndim != 3 or not np.all(np.isfinite(data)) or not np.all(data == np.round(data)) or data.min() < 0 or data.max() > max_label:
        raise GeometryError('모델 출력이 해당 task의 유효한 정수 라벨맵이 아닙니다.')
    if not np.all(np.isfinite(image.affine)) or abs(np.linalg.det(image.affine[:3, :3])) < 1e-9:
        raise GeometryError('모델 출력의 공간 변환이 유효하지 않습니다.')
    target = (tuple(info['shape_xyz']), np.array(source['affine_ras']))
    corners = np.array(list(product(*[(0, n - 1) for n in image.shape])))
    source_indices = (np.linalg.inv(target[1]) @ image.affine @ np.c_[corners, np.ones(8)].T).T[:, :3]
    if np.any(source_indices.max(axis=0) < 0) or np.any(source_indices.min(axis=0) > np.array(target[0]) - 1):
        raise GeometryError('모델 출력과 원본 영상의 공간 범위가 겹치지 않습니다.')
    restored = resample_from_to(image, target, order=0, mode='constant', cval=0)
    labels = np.asanyarray(restored.dataobj).astype(np.uint8)
    labels[~np.isin(labels, list(catalog))] = 0
    np.save(directory / 'labels.npy', labels, allow_pickle=False)
    voxel_mm3 = float(abs(np.linalg.det(target[1][:3, :3])))
    structures = []
    for label, (name, title, color) in catalog.items():
        indices = np.argwhere(labels == label)
        count = int(len(indices))
        centroid = indices.mean(axis=0) if count else None
        # Affine is valid for fractional Z; patient_point indexes only integer Z.
        centre_lps = (np.diag([-1., -1., 1., 1.]) @ target[1] @ np.r_[centroid, 1.])[:3].tolist() if count else None
        structures.append({'label': label, 'name': name, 'title': title, 'color': color,
                           'voxel_count': count, 'volume_mm3': count * voxel_mm3,
                           'volume_ml': count * voxel_mm3 / 1000, 'centroid_lps_mm': centre_lps,
                           'status': 'segmented' if count else 'no_segment',
                           'touches_boundary': bool(count and np.any((indices == 0) | (indices == np.array(labels.shape) - 1)))})
    result = {'model_id': model_id, 'series_id': source['id'], 'study_id': source['study_id'], 'shape_xyz': info['shape_xyz'],
              'spacing_xyz': info['spacing_xyz'], 'structures': structures,
              'measurement_method': 'original-grid labelled voxel count × abs(det(affine)); 1000 mm³ = 1 mL',
              'restoration': 'nearest neighbour to original voxel centres; labels outside field of view=0',
              'source': source, 'prediction_affine_ras': image.affine.tolist(),
              'labels_sha256': hashlib.sha256((directory / 'labels.npy').read_bytes()).hexdigest(),
              'limitations': (['해부학 분할이며 질환 탐지/정상 판정이 아닙니다.', '3 mm 저해상도 모델이며 경계·부피 오차가 있습니다.'] if model_id == 'total'
                             else ['AI 분할 후보이며 확정 진단·질환 배제가 아닙니다.', '탐지 점수·악성 확률을 제공하지 않습니다. 임상 성능은 미평가입니다.'])
                             + ['촬영 범위를 벗어나는 구조의 부피는 부분 부피입니다.']}
    if model_id != 'total':
        from .findings import quantify_findings
        findings, component_map = quantify_findings(labels, source, model_id)
        np.save(directory / 'components.npy', component_map, allow_pickle=False)
        result.update({'findings': findings, 'finding_count': len(findings),
                       'components_sha256': hashlib.sha256((directory / 'components.npy').read_bytes()).hexdigest(),
                       'finding_status': 'candidates_present' if findings else 'no_candidates',
                       'connectivity': '26-neighbour 3D; per label',
                       'score_semantics': 'not provided; not malignancy probability'})
    # Publish only after all artifacts and statistics are valid; manager marks completed last.
    (directory / 'result.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    return result
