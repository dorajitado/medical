"""Optional live UI QA against the retained PUBLIC EXAMPLE workspace only.

Run after python -m backend.qa_week3. This server deliberately cannot select the
production workspace; it binds to the separate test port via the CLI command.
"""
import json
from pathlib import Path
from .analysis_runtime import ROOT
from .app import create_app

qa_root = (ROOT / 'data' / 'qa-week3').resolve()
evidence = json.loads((qa_root / 'last-run.json').read_text(encoding='utf-8'))
workspace = Path(evidence['workspace']).resolve()
if workspace.parent != qa_root or not workspace.name.startswith('workspace-'):
    raise RuntimeError('Only the public-example QA workspace is allowed.')
app = create_app(workspace, allowed_origins={'http://127.0.0.1:8002'},
                 imaging_path=ROOT / 'data' / 'qa-imaging' / 'orthanc.json')
