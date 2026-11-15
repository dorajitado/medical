"""Isolated GPU entry point. Receives only a prepared CT volume and run folder.

No report text or patient demographics are passed to the neural network.
The API captures output privately; a sanitized error code is returned to users.
"""
import json
from pathlib import Path
import sys
import time


def main(directory: Path):
    """Run the pinned public task once; process exit releases CUDA allocations."""
    import torch
    from totalsegmentator.python_api import totalsegmentator
    from .analysis_runtime import CONFIGURATION, CONFIGURATIONS
    from .analysis_volume import restore_output

    started = time.monotonic()
    if not torch.cuda.is_available():
        raise RuntimeError('GPU_UNAVAILABLE')
    torch.set_num_threads(4)
    torch.cuda.reset_peak_memory_stats()
    # Each persisted run carries an allowlisted configuration snapshot. Earlier
    # anatomy runs have no request.json and retain their original adapter.
    request_path = directory / 'request.json'
    request = json.loads(request_path.read_text()) if request_path.exists() else {'model_id': 'total'}
    model_id = request['model_id']
    configuration = CONFIGURATIONS[model_id]
    if request.get('configuration', configuration) != configuration:
        raise RuntimeError('Queued model configuration changed; start a new run')
    if model_id=='monai_nodule':
        from .monai_worker import run_monai
        run_monai(directory)
    else:
        totalsegmentator(directory / 'input.nii.gz', directory / 'prediction.nii.gz',
                     ml=True, fast=configuration['fast'], task=model_id, device='gpu',
                     nr_thr_resamp=1, nr_thr_saving=1, quiet=True, statistics=False,
                     skip_saving=False)
        restore_output(directory, model_id)
    metrics = {'elapsed_seconds': time.monotonic() - started,
               'cuda_peak_allocated_bytes': torch.cuda.max_memory_allocated(),
               'cuda_peak_reserved_bytes': torch.cuda.max_memory_reserved(),
               'gpu': torch.cuda.get_device_name(), 'configuration': configuration}
    (directory / 'metrics.json').write_text(json.dumps(metrics), encoding='utf-8')


if __name__ == '__main__':
    # Windows spawn imports this module; main guard prevents recursive inference.
    folder = Path(sys.argv[1]).resolve()
    try:
        main(folder)
    except Exception as exc:
        # Do not expose paths, image headers or report text via API/logs.
        message = str(exc).lower()
        code = 'out_of_memory' if 'out of memory' in message else 'inference_failed'
        (folder / 'failure.json').write_text(json.dumps({'code': code}), encoding='utf-8')
        import traceback
        traceback.print_exc()
        sys.exit(1)
