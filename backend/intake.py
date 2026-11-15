import hashlib
import json
import math
from pathlib import Path
from uuid import uuid4

import pydicom
from pydicom.uid import CTImageStorage, ExplicitVRLittleEndian, ImplicitVRLittleEndian
from .storage import Store


class RejectedInput(ValueError):
    pass


def inspect_ct(path: Path) -> dict:
    try:
        ds = pydicom.dcmread(path, stop_before_pixels=True)
    except Exception as exc:
        raise RejectedInput('DICOM 형식으로 읽을 수 없습니다.') from exc
    required = ['Modality', 'StudyInstanceUID', 'SeriesInstanceUID', 'SOPInstanceUID', 'SOPClassUID',
                'ImagePositionPatient', 'ImageOrientationPatient', 'PixelSpacing',
                'Rows', 'Columns', 'RescaleSlope', 'RescaleIntercept']
    if any(not hasattr(ds, field) for field in required):
        raise RejectedInput('필수 UID·공간정보·HU 변환 정보가 없습니다.')
    if ds.Modality != 'CT' or str(ds.SOPClassUID) != str(CTImageStorage):
        raise RejectedInput('초기 지원 대상은 단일 프레임 CT Image Storage입니다.')
    if int(getattr(ds, 'NumberOfFrames', 1)) != 1 or 'LOCALIZER' in getattr(ds, 'ImageType', []):
        raise RejectedInput('로컬라이저 또는 다중 프레임 CT는 아직 지원하지 않습니다.')
    transfer = str(getattr(ds.file_meta, 'TransferSyntaxUID', ''))
    if transfer not in {str(ExplicitVRLittleEndian), str(ImplicitVRLittleEndian)}:
        raise RejectedInput('압축 또는 미지원 전송 형식입니다.')
    for uid in ['StudyInstanceUID', 'SeriesInstanceUID', 'SOPInstanceUID']:
        if not pydicom.uid.UID(str(getattr(ds, uid))).is_valid:
            raise RejectedInput('유효하지 않은 DICOM UID입니다.')
    if str(getattr(ds.file_meta, 'MediaStorageSOPInstanceUID', '')) != str(ds.SOPInstanceUID):
        raise RejectedInput('파일 메타와 영상 인스턴스 UID가 다릅니다.')
    try:
        position = [float(v) for v in ds.ImagePositionPatient]
        orientation = [float(v) for v in ds.ImageOrientationPatient]
        spacing = [float(v) for v in ds.PixelSpacing]
        slope, intercept = float(ds.RescaleSlope), float(ds.RescaleIntercept)
        if len(position) != 3 or len(orientation) != 6 or len(spacing) != 2:
            raise ValueError()
        if not all(math.isfinite(v) for v in position + orientation + spacing + [slope, intercept]):
            raise ValueError()
        if min(spacing) <= 0 or slope == 0 or min(int(ds.Rows), int(ds.Columns)) <= 0:
            raise ValueError()
        a, b = orientation[:3], orientation[3:]
        if abs(sum(v*v for v in a)-1) > .01 or abs(sum(v*v for v in b)-1) > .01 or abs(sum(x*y for x,y in zip(a,b))) > .01:
            raise ValueError()
    except (ValueError, TypeError):
        raise RejectedInput('공간정보 또는 HU 변환 값이 유효하지 않습니다.')
    return {
        'study_uid': str(ds.StudyInstanceUID), 'series_uid': str(ds.SeriesInstanceUID),
        'sop_uid': str(ds.SOPInstanceUID), 'study_date': str(getattr(ds, 'StudyDate', '')) or None,
        'description': str(getattr(ds, 'StudyDescription', '')) or None,
        'series_description': str(getattr(ds, 'SeriesDescription', '')) or None,
        'contrast_agent': str(getattr(ds, 'ContrastBolusAgent', '')) or None,
        'slice_thickness': str(getattr(ds, 'SliceThickness', '')) or None,
        'convolution_kernel': str(getattr(ds, 'ConvolutionKernel', '')) or None,
        'image_type': [str(v) for v in getattr(ds, 'ImageType', [])],
        'reconstruction_diameter': str(getattr(ds, 'ReconstructionDiameter', '')) or None,
        'position': position, 'orientation': orientation, 'pixel_spacing': spacing,
        'rows': int(ds.Rows), 'columns': int(ds.Columns), 'slope': slope, 'intercept': intercept,
        'transfer_syntax': transfer, 'validation': 'metadata_only', 'ctpa': 'unknown',
    }


def register_file(store: Store, path: Path, job_id: str) -> dict:
    try:
        metadata = inspect_ct(path)
    except RejectedInput as exc:
        return record_result(store, job_id, 'excluded', str(exc))
    except Exception:
        return record_result(store, job_id, 'failed', '파일 메타데이터 확인 중 오류가 발생했습니다.')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    moved = None
    try:
        with store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            job = c.execute('SELECT * FROM import_jobs WHERE id=?', (job_id,)).fetchone()
            if not job or job['status'] != 'running':
                raise ValueError('Import is not running')
            prior = c.execute('SELECT sha256 FROM instances WHERE sop_uid=?', (metadata['sop_uid'],)).fetchone()
            if prior:
                outcome = 'duplicates' if prior['sha256'] == digest else 'failed'
                issue = None if outcome == 'duplicates' else '동일 UID에 다른 파일이 있어 덮어쓰지 않았습니다.'
            else:
                study = c.execute('SELECT id FROM studies WHERE study_uid=?', (metadata['study_uid'],)).fetchone()
                study_id = study['id'] if study else str(uuid4())
                if not study:
                    c.execute('INSERT INTO studies(id,study_uid,study_date,description) VALUES (?,?,?,?)',
                              (study_id, metadata['study_uid'], metadata['study_date'], metadata['description']))
                series = c.execute('SELECT id,study_id FROM series WHERE series_uid=?', (metadata['series_uid'],)).fetchone()
                if series and series['study_id'] != study_id:
                    raise RejectedInput('시리즈 UID가 다른 검사에 이미 등록되어 있습니다.')
                series_id = series['id'] if series else str(uuid4())
                if not series:
                    c.execute('INSERT INTO series VALUES (?,?,?,?)', (series_id, metadata['series_uid'], study_id, json.dumps(metadata)))
                iid = str(uuid4())
                stored_name = iid + '.dcm'
                moved = store.root / 'originals' / stored_name
                path.replace(moved)
                c.execute('INSERT INTO instances VALUES (?,?,?,?,?,?)', (iid, metadata['sop_uid'], series_id, digest, stored_name, json.dumps(metadata)))
                outcome, issue = 'imported', None
            c.execute(f'UPDATE import_jobs SET {outcome}={outcome}+1,last_issue=? WHERE id=?', (issue, job_id))
        return {'outcome': outcome, 'issue': issue}
    except Exception:
        if moved:
            moved.unlink(missing_ok=True)
        return record_result(store, job_id, 'failed', '검사 연결 또는 파일 저장에 실패했습니다.')


def record_result(store: Store, job_id: str, outcome: str, issue: str) -> dict:
    if outcome not in {'excluded', 'failed'}:
        raise ValueError('Invalid outcome')
    with store.connect() as c:
        c.execute(f'UPDATE import_jobs SET {outcome}={outcome}+1,last_issue=? WHERE id=? AND status=?', (issue, job_id, 'running'))
    return {'outcome': outcome, 'issue': issue}
