"""Validated rectilinear CT geometry in DICOM patient LPS coordinates (mm)."""
import hashlib
import json
import re
from pathlib import Path
import numpy as np
import pydicom
from .storage import Store


class GeometryError(ValueError):
    pass


def source_path(store: Store, name: str) -> Path:
    if not re.fullmatch(r'[0-9a-f-]{36}\.dcm', name):
        raise GeometryError('관리 저장 경로가 유효하지 않습니다.')
    root = (store.root / 'originals').resolve()
    path = (root / name).resolve()
    if path.parent != root:
        raise GeometryError('원본 저장 경로를 벗어났습니다.')
    return path


def validate_series(store: Store, series_id: str):
    with store.connect() as c:
        if c.execute("SELECT id FROM import_jobs WHERE status='running'").fetchone():
            raise GeometryError('파일 등록이 진행 중입니다. 처리 완료 후 영상을 열어 주세요.')
        series = c.execute('SELECT * FROM series WHERE id=?', (series_id,)).fetchone()
        rows = c.execute('SELECT * FROM instances WHERE series_id=?', (series_id,)).fetchall()
        if series is None:
            raise KeyError('시리즈가 없습니다.')
        if not rows:
            raise GeometryError('영상 인스턴스가 없습니다.')
    metadata = [json.loads(r['metadata']) for r in rows]
    reference = metadata[0]
    a, b = np.array(reference['orientation'][:3]), np.array(reference['orientation'][3:])
    if max(abs(np.linalg.norm(a)-1), abs(np.linalg.norm(b)-1), abs(np.dot(a,b))) > 1e-4:
        raise GeometryError('방향 벡터가 직교 단위 벡터가 아닙니다.')
    normal = np.cross(a,b)
    normal = normal / np.linalg.norm(normal)
    shape = (reference['rows'], reference['columns'])
    for m in metadata:
        if (m['rows'],m['columns']) != shape:
            raise GeometryError('한 시리즈에 영상 크기가 섞여 있습니다.')
        if not np.allclose(m['orientation'],reference['orientation'],atol=1e-4,rtol=0):
            raise GeometryError('한 시리즈에 방향이 다른 영상이 섞여 있습니다.')
        if not np.allclose(m['pixel_spacing'],reference['pixel_spacing'],atol=1e-4,rtol=0):
            raise GeometryError('한 시리즈에 픽셀 간격이 섞여 있습니다.')
    order = sorted(range(len(rows)), key=lambda i: float(np.dot(metadata[i]['position'],normal)))
    rows = [rows[i] for i in order]
    metadata = [metadata[i] for i in order]
    positions = np.array([m['position'] for m in metadata], dtype=float)
    distances = positions @ normal
    spacing_z = None
    if len(rows) > 1:
        gaps = np.diff(distances)
        if min(gaps) <= 1e-4:
            raise GeometryError('중복 또는 겹치는 절편 위치가 있습니다.')
        spacing_z = float(np.median(gaps))
        if not np.allclose(gaps,spacing_z,atol=max(.01,spacing_z*.01),rtol=0):
            raise GeometryError('절편 간격이 불규칙합니다. 누락 또는 혼합 시리즈를 확인해 주세요.')
        residual = np.diff(positions,axis=0)-gaps[:,None]*normal
        if float(np.max(np.linalg.norm(residual,axis=1))) > .05:
            raise GeometryError('Gantry tilt 또는 비직교 절편 이동은 초기 MPR에서 지원하지 않습니다.')
    # Decode once during validation. Do not retain an entire volume in memory.
    for row in rows:
        path = source_path(store,row['stored_name'])
        try:
            if hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
                raise GeometryError('등록한 원본 파일의 해시가 달라졌습니다.')
            ds = pydicom.dcmread(path)
            if getattr(ds,'SamplesPerPixel',0) != 1 or getattr(ds,'PhotometricInterpretation','') not in {'MONOCHROME1','MONOCHROME2'}:
                raise GeometryError('지원하지 않는 픽셀 형식입니다.')
            pixels = ds.pixel_array
            if pixels.shape != shape:
                raise GeometryError('픽셀 크기와 DICOM 메타데이터가 다릅니다.')
        except GeometryError:
            raise
        except Exception as exc:
            raise GeometryError('원본 픽셀을 읽을 수 없습니다. 손상 또는 미지원 형식입니다.') from exc
    summary = {
        'series_id':series_id, 'supported':True, 'coordinate_system':'DICOM LPS', 'unit':'mm',
        'shape_xyz':[shape[1],shape[0],len(rows)],
        'spacing_xyz':[reference['pixel_spacing'][1],reference['pixel_spacing'][0],spacing_z],
        'origin':positions[0].tolist(), 'column_direction':a.tolist(),
        'row_direction':b.tolist(), 'slice_normal':normal.tolist(),
        'positions':positions.tolist(), 'mpr_supported':len(rows)>=3,
        'instances':[{'id':r['id'],'sop_uid':r['sop_uid']} for r in rows],
        'warnings':[] if len(rows)>=3 else ['MPR에는 최소 3개 절편을 등록해 주세요.'],
    }
    return summary, rows, metadata


def patient_point(info, x, y, z):
    return np.array(info['positions'][z]) + x*info['spacing_xyz'][0]*np.array(info['column_direction']) + y*info['spacing_xyz'][1]*np.array(info['row_direction'])


def probe(store, series_id, x, y, z):
    info, rows, metadata = validate_series(store,series_id)
    w,h,d = info['shape_xyz']
    if not (0<=x<w and 0<=y<h and 0<=z<d):
        raise GeometryError('측정 위치가 영상 범위를 벗어났습니다.')
    ds = pydicom.dcmread(source_path(store,rows[z]['stored_name']))
    raw = int(ds.pixel_array[y,x])
    padding = getattr(ds,'PixelPaddingValue',None)
    padded = padding is not None and min(int(padding),int(getattr(ds,'PixelPaddingRangeLimit',padding))) <= raw <= max(int(padding),int(getattr(ds,'PixelPaddingRangeLimit',padding)))
    value = None if padded else raw*metadata[z]['slope']+metadata[z]['intercept']
    return {'hu':value,'padding':padded,'raw_value':raw,'patient_lps_mm':patient_point(info,x,y,z).tolist(),
            'source_instance_id':rows[z]['id'],'sample_kind':'original_voxel','index_xyz':[x,y,z]}


def distance(store,series_id,start,end):
    info,_,_ = validate_series(store,series_id)
    for xyz in [start,end]:
        if len(xyz)!=3 or not all(0<=v<limit for v,limit in zip(xyz,info['shape_xyz'])):
            raise GeometryError('측정 위치가 영상 범위를 벗어났습니다.')
    p1,p2 = patient_point(info,*start),patient_point(info,*end)
    return {'distance_mm':float(np.linalg.norm(p2-p1)),'start_lps_mm':p1.tolist(),'end_lps_mm':p2.tolist(),'method':'DICOM patient-coordinate Euclidean distance'}
