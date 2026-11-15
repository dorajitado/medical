"""Explicit synthetic positive fixtures for repeatable candidate navigation QA.

This module is imported ONLY by the separate QA server/unit tests. Production
startup never imports it, and its output is labelled SYNTHETIC / not model output.
"""
import json
from pathlib import Path
from uuid import uuid4

import nibabel as nib
import numpy as np
from pydicom.uid import generate_uid

from .analysis_runtime import CONFIGURATIONS
from .analysis_volume import convert_source, restore_output
from .intake import register_file
from .storage import Store
from .test_intake import ct_bytes


def create_fixture(root: Path):
    store = Store(root)
    store.initialize()
    study, series, jid = generate_uid(), generate_uid(), str(uuid4())
    with store.connect() as c:
        c.execute("INSERT INTO import_jobs(id,status,total) VALUES (?,'running',32)", (jid,))
    # Small but asymmetric physical phantom, with two disconnected nodule
    # masks on different source slices. No patient records or model predictions.
    x, y, z = np.ogrid[:96, :96, :32]
    lung_left = ((x - 30) * .8) ** 2 + ((y - 48) * .8) ** 2 + ((z - 16) * 2) ** 2 < 22 ** 2
    lung_right = ((x - 67) * .8) ** 2 + ((y - 48) * .8) ** 2 + ((z - 16) * 2) ** 2 < 22 ** 2
    a = ((x - 27) * .8) ** 2 + ((y - 43) * .8) ** 2 + ((z - 8) * 2) ** 2 < 4 ** 2
    b = ((x - 68) * .8) ** 2 + ((y - 54) * .8) ** 2 + ((z - 23) * 2) ** 2 < 5 ** 2
    hu = np.full((96, 96, 32), -900, dtype='<i2')
    hu[a | b] = 70
    for plane in range(32):
        payload = ct_bytes(study, series, Rows=96, Columns=96, PixelSpacing=[.8, .8],
                           ImagePositionPatient=[-30, -40, plane * 2], PixelRepresentation=1,
                           PixelData=hu[:, :, plane].T.copy().tobytes(), RescaleSlope=1, RescaleIntercept=0,
                           StudyDescription='SYNTHETIC FINDINGS QA ONLY', SeriesDescription='SYNTHETIC CANDIDATE PHANTOM',
                           SliceThickness=2, InstanceNumber=plane + 1)
        stage = root / 'staging' / f'{uuid4()}.part'
        stage.write_bytes(payload)
        if register_file(store, stage, jid)['outcome'] != 'imported':
            raise RuntimeError('Synthetic fixture registration failed')
    with store.connect() as c:
        c.execute("UPDATE import_jobs SET status='completed' WHERE id=?", (jid,))
        sid = c.execute('SELECT id FROM series WHERE series_uid=?', (series,)).fetchone()[0]
    cases = {}
    anatomy = np.zeros(hu.shape, dtype=np.uint8)
    anatomy[lung_left] = 10; anatomy[lung_right] = 12
    nodules = np.zeros_like(anatomy); nodules[a | b] = 2
    effusions = np.zeros_like(anatomy)
    effusions[lung_left & (y > 55)] = 2
    effusions[((x - 48) * .8) ** 2 + ((y - 48) * .8) ** 2 + ((z - 16) * 2) ** 2 < 8 ** 2] = 3
    for model_id, mask in [('total', anatomy), ('lung_nodules', nodules), ('pleural_pericard_effusion', effusions)]:
        rid = str(uuid4())
        folder = root / 'analysis' / rid
        folder.mkdir(parents=True)
        source = convert_source(store, sid, folder, model_id)
        nib.save(nib.Nifti1Image(mask, np.array(source['affine_ras'])), folder / 'prediction.nii.gz')
        result = restore_output(folder, model_id)
        result['limitations'].insert(0, '합성 검증용 마스크 — 실제 AI 모델 출력이 아닙니다.')
        result['verification_source'] = 'synthetic_fixture_not_model_prediction'
        (folder / 'result.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
        (folder / 'metrics.json').write_text(json.dumps({'elapsed_seconds': None, 'cuda_peak_allocated_bytes': None,
                                                        'cuda_peak_reserved_bytes': None, 'source': 'synthetic fixture; not inference measurements'}))
        snapshot = json.dumps({'configuration': CONFIGURATIONS[model_id], 'runtime': {'validation': 'synthetic_fixture_not_model'}})
        with store.connect() as c:
            c.execute("INSERT INTO analysis_runs(id,series_id,model_id,status,stage,snapshot,finished_at) VALUES (?,?,?,'completed','completed',?,CURRENT_TIMESTAMP)", (rid, sid, model_id, snapshot))
        cases[model_id] = rid
    return {'series_id': sid, 'runs': cases}
