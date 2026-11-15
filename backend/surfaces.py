"""Derive display-only surfaces from a completed run's source-grid labels.

Marching cubes is performed on a padded, cropped binary label at level 0.5.
Vertices are transformed into DICOM LPS millimetres. Surface decimation is for
display only: all candidate volumes and Feret sizes use original voxels.
"""
import numpy as np
from skimage.measure import marching_cubes
from .geometry import GeometryError

ALGORITHM = 'source-mask-marching-cubes-1'


def surface(mask, affine_lps, offset=None, max_faces=50000):
    """Return a bounded triangle mesh; never silently drop a tiny candidate.

    Large anatomical regions use a coarser marching step when necessary. Tiny
    candidates remain step 1. Padding closes field-of-view edges; boundary flags
    in the result warn that this is not a complete anatomical organ volume.
    """
    positions = np.argwhere(mask)
    if not len(positions):
        return None
    low = positions.min(axis=0)
    high = positions.max(axis=0) + 1
    box = tuple(slice(int(a), int(b)) for a, b in zip(low, high))
    cropped = np.pad(mask[box], 1).astype(np.uint8)
    origin = low - 1 + (np.array(offset) if offset is not None else 0)
    step = 1
    while True:
        vertices, faces, _, _ = marching_cubes(cropped, level=.5, step_size=step, allow_degenerate=False)
        if len(faces) <= max_faces or step >= 8 or min(cropped.shape) <= step + 2:
            break
        step += 1
    # Complete the coordinate transform before rounding for JSON size. The
    # 0.001 mm rendering precision is not used by quantitative measurements.
    world = (affine_lps @ np.c_[vertices + origin, np.ones(len(vertices))].T).T[:, :3]
    if len(faces) > 150000:
        raise GeometryError('이 구조의 3D 표면이 초기 표시 한도를 초과했습니다. 원본 CT 마스크에서 검토해 주세요.')
    return {'vertices_lps_mm': np.round(world, 3).ravel().tolist(),
            'triangles': faces.astype(np.uint32).ravel().tolist(),
            'marching_step': step, 'vertex_count': int(len(vertices)), 'face_count': int(len(faces))}


def build_surfaces(labels, result, components=None):
    """Use run-local candidate selection IDs, never label numbers across tasks."""
    affine_lps = np.diag([-1., -1., 1., 1.]) @ np.array(result['source']['affine_ras'])
    objects = []
    if result.get('model_id')=='monai_nodule':
        # A wire box is a detector localization, never an inferred organ surface.
        triangles=[0,1,3,0,3,2,4,6,7,4,7,5,0,4,5,0,5,1,2,3,7,2,7,6,0,2,6,0,6,4,1,5,7,1,7,3]
        return {'coordinate_system':'DICOM LPS','unit':'mm','algorithm':ALGORITHM,'objects':[
            {'id':f"box-{f['id']}",'candidate_id':f['id'],'title':f['title'],'color':f['color'],
             'vertices_lps_mm':np.array(f['box_vertices_lps_mm']).ravel().tolist(),'triangles':triangles,
             'marching_step':1,'vertex_count':8,'face_count':12,'representation':'detection_box_not_segmentation'}
            for f in result.get('findings',[])], 'measurement_source':'detector boxes; no segmentation volume',
            'limitations':['탐지상자이며 분할 표면이 아닙니다.']}
    if result.get('model_id', 'total') == 'total':
        targets = [{'id': f"structure-{s['label']}", 'label': s['label'], 'title': s['title'], 'color': s['color'],
                    'candidate_id': None} for s in result['structures'] if s['voxel_count']]
    else:
        targets = [{'id': f"finding-{s['selection_label']}", 'label': s['selection_label'], 'title': s['title'],
                    'color': s['color'], 'candidate_id': s['id']} for s in result.get('findings', [])]
    for target in targets:
        source = labels if target['candidate_id'] is None else components
        mesh = surface(source == target['label'], affine_lps)
        if mesh:
            objects.append({**target, **mesh})
            if sum(obj['face_count'] for obj in objects) > 600000:
                raise GeometryError('3D 전체 표면이 초기 표시 한도를 초과했습니다. 원본 CT 마스크는 보존됩니다.')
    return {'coordinate_system': 'DICOM LPS', 'unit': 'mm', 'algorithm': ALGORITHM,
            'objects': objects, 'measurement_source': 'original voxels; never display surfaces',
            'limitations': ['표면은 0.5 등가면의 시각화입니다. 큰 구조는 marching step을 조정합니다.',
                           '영상 경계는 닫힌 표면으로 표현되며 실제 해부학 경계와 다를 수 있습니다.']}
