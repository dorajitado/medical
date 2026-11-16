"""Dedicated synthetic CT-only UI test server; never imported by production.

The real queue/enqueue/DB/cancel paths run, but its worker copies labelled known
fixtures instead of running a neural network. Public actual-model QA is separate.
"""
from itertools import product
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch
from uuid import uuid4
import numpy as np
from .analysis import AnalysisManager
from .analysis_runtime import ROOT, CONFIGURATIONS
from .app import create_app
from .qa_findings_fixture import create_fixture
from .storage import Store

directory = TemporaryDirectory(prefix='ct-summary-synthetic-')
root = Path(directory.name)
fixture = create_fixture(root)
store = Store(root)

# Known duplicate boxes exercise independent-model proposals without faking a
# segmentation volume. All eight box vertices use the same source LPS affine.
reference = root/'analysis'/fixture['runs']['lung_nodules']
rid = str(uuid4()); folder = root/'analysis'/rid
folder.mkdir()
for name in ['input.nii.gz', 'source.json', 'metrics.json']:
    shutil.copyfile(reference/name, folder/name)
result = json.loads((reference/'result.json').read_text(encoding='utf-8'))
result.update(model_id='monai_nodule', structures=[], representation='detection_boxes_not_segmentation')
result.pop('components_sha256', None)
affine = np.diag([-1., -1., 1., 1.]) @ np.array(result['source']['affine_ras'])
for index, finding in enumerate(result['findings']):
    corners = np.array(list(product(*zip(*finding['bounds_index_xyz']))))
    finding.update(id=f'synthetic-box-{index}', model_id='monai_nodule', score=.25, score_meaning='synthetic fixture; not malignancy',
                   volume_mm3=None, volume_ml=None, diameter_mm=None, voxel_count=None,
                   representation='detection_box_not_segmentation', diameter_method='not provided; detector box only',
                   box_vertices_lps_mm=(affine @ np.c_[corners, np.ones(8)].T).T[:, :3].tolist())
np.save(folder/'labels.npy', np.zeros(result['shape_xyz'], dtype=np.uint8), allow_pickle=False)
result['labels_sha256'] = hashlib.sha256((folder/'labels.npy').read_bytes()).hexdigest()
(folder/'result.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
fixture['runs']['monai_nodule'] = rid
with store.connect() as c:
    c.execute("INSERT INTO analysis_runs(id,series_id,model_id,status,stage,snapshot) VALUES (?,?,'monai_nodule','completed','completed',?)", (rid, fixture['series_id'], json.dumps({'configuration': CONFIGURATIONS['monai_nodule'], 'runtime': {'source': 'synthetic_not_model'}})))


class SyntheticQueue(AnalysisManager):
    fail_next = set()

    def execute(self, identifier):
        """Use owned fake outputs only; inherited single-thread pool orders jobs."""
        if not self.active(identifier): return
        self.update(identifier, 'running', 'inference')
        deadline = time.monotonic() + 1.2
        while time.monotonic() < deadline:
            if not self.active(identifier): return
            time.sleep(.05)
        model = self.get(identifier)['model_id']
        if model in self.fail_next:
            self.fail_next.remove(model)
            self.update(identifier, 'failed', 'failed', '합성 시험용 모델 실패 — 정상 결과 아님')
            return
        shutil.copytree(root/'analysis'/fixture['runs'][model], self.directory(identifier))
        self.update(identifier, 'completed', 'completed')


# These patches live only in this isolated server process. Production imports
# neither this module nor its fixture/runtime inventory overrides.
inventory = {'ready': True, 'reason': None, 'weights_digest': 'synthetic-fixture-only'}
analysis_inventory = patch('backend.analysis.runtime_status', return_value=inventory); analysis_inventory.start()
review_inventory = patch('backend.ct_review.runtime_status', return_value=inventory); review_inventory.start()
with patch('backend.app.AnalysisManager', SyntheticQueue):
    app = create_app(root, allowed_origins={'http://127.0.0.1:8005'}, imaging_path=ROOT/'data'/'qa-imaging'/'orthanc.json')


@app.post('/api/qa/fail-next/{model}')
def fail_next(model: str):
    if model not in CONFIGURATIONS: raise ValueError('Unknown test model')
    SyntheticQueue.fail_next.add(model)
    return {'source': 'synthetic_test_only', 'model': model}

# create_app appends its static '/' mount last. Put the QA-only control before
# that catch-all mount, retaining the app's Origin/header mutation protection.
qa_route = app.router.routes.pop()
app.router.routes.insert(0, qa_route)
