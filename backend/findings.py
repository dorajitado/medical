"""Measurements of immutable source-grid AI candidates, not clinical diagnoses.

Nodules are 26-connected components of the task's nodule label. Effusions are
one aggregate region per task class, preserving every disconnected component.
Volume always uses the original voxel lattice, never a decimated 3D surface.
"""
import numpy as np
from scipy import ndimage
from scipy.spatial import ConvexHull
from scipy.spatial.distance import pdist


def axial_feret(mask, inplane_basis):
    """Maximum source-slice Feret diameter of voxel *outer corners*, over slices.

    Explicitly not RECIST: no radiologist's caliper selection or clinical
    eligibility rules are applied. Including half-voxel extents gives a finite
    and documented size even for a single-voxel component. Millimetres only.
    """
    best = None
    for z in range(mask.shape[2]):
        plane = mask[:, :, z]
        if not plane.any():
            continue
        boundary = plane & ~ndimage.binary_erosion(plane, structure=np.ones((3, 3)), border_value=0)
        centres = np.argwhere(boundary).astype(float)
        corners = np.concatenate([centres + offset for offset in [(-.5, -.5), (-.5, .5), (.5, -.5), (.5, .5)]])
        points = np.unique(corners, axis=0)
        hull = points[ConvexHull(points).vertices]
        # Use the full DICOM in-plane basis, preserving accepted orientation
        # rounding/non-orthogonality rather than assuming perfectly orthogonal XY.
        basis = np.asarray(inplane_basis)
        world = hull * basis if basis.ndim == 1 else hull @ basis.T
        value = float(pdist(world).max())
        if best is None or value > best['diameter_mm']:
            best = {'diameter_mm': value, 'slice_z': z}
    return best


def quantify_findings(labels, source, model_id):
    """Return reproducible candidate IDs, source positions and a selection map.

    Representative location is an actual segmented voxel nearest the component
    centroid. A hollow/concave component's arithmetic centroid could lie outside
    the mask and would be a misleading navigation point. IDs are run-local.
    """
    from .analysis_volume import TASK_STRUCTURES
    catalog = TASK_STRUCTURES[model_id]
    affine_lps = np.diag([-1., -1., 1., 1.]) @ np.array(source['affine_ras'])
    voxel_volume = float(abs(np.linalg.det(affine_lps[:3, :3])))
    candidates = []
    selections = np.zeros(labels.shape, dtype=np.int32)
    for label, (name, title, color) in catalog.items():
        mask = labels == label
        if not mask.any():
            continue
        if model_id == 'lung_nodules':
            components, count = ndimage.label(mask, structure=np.ones((3, 3, 3)))
            boxes = ndimage.find_objects(components)
        else:
            # Each effusion class is an aggregate volume, not a list of nodules.
            components = mask.astype(np.int32)
            count = 1
            positions = np.argwhere(mask)
            boxes = [tuple(slice(int(lo), int(hi) + 1) for lo, hi in zip(positions.min(axis=0), positions.max(axis=0)))]
        for component in range(1, count + 1):
            box = boxes[component - 1]
            if box is None:
                continue
            local = components[box] == component
            start = np.array([s.start for s in box])
            positions = np.argwhere(local) + start
            centroid = positions.mean(axis=0)
            distances = np.sum(((positions - centroid) @ affine_lps[:3, :3].T) ** 2, axis=1)
            representative = positions[int(np.argmin(distances))]
            number = len(candidates) + 1
            selections[box][local] = number
            measured = axial_feret(local, affine_lps[:3, :2]) if model_id == 'lung_nodules' else None
            if measured:
                measured['slice_z'] += int(start[2])
            volume = len(positions) * voxel_volume
            candidates.append({'id': f'{name}-{component}', 'selection_label': number, 'kind': name,
                               'title': f'{title} {component}' if model_id == 'lung_nodules' else title,
                               'label': label, 'color': color, 'voxel_count': int(len(positions)),
                               'volume_mm3': volume, 'volume_ml': volume / 1000,
                               'diameter_mm': measured['diameter_mm'] if measured else None,
                               'diameter_slice_z': measured['slice_z'] if measured else None,
                               'diameter_method': 'maximum source-slice 2D Feret over outer voxel corners; not RECIST or patient-axial MPR' if measured else 'not applicable; aggregate effusion volume',
                               'representative_index_xyz': representative.tolist(),
                               'representative_lps_mm': (affine_lps @ np.r_[representative, 1.])[:3].tolist(),
                               'centroid_lps_mm': (affine_lps @ np.r_[centroid, 1.])[:3].tolist(),
                               'bounds_index_xyz': [positions.min(axis=0).tolist(), positions.max(axis=0).tolist()],
                               'touches_boundary': bool(np.any((positions == 0) | (positions == np.array(labels.shape) - 1))),
                               'score': None, 'score_meaning': 'not provided', 'model_id': model_id,
                               'source_instance_id': source['sources'][int(representative[2])]['instance_id'],
                               'review_status': 'unreviewed_ai_candidate'})
    return candidates, selections
