"""Ephemeral, synthetic-only UI QA. Never uses the production data directory."""
from pathlib import Path
from tempfile import TemporaryDirectory
from .analysis_runtime import ROOT
from .qa_findings_fixture import create_fixture
from .app import create_app

directory = TemporaryDirectory(prefix='ct-week4-synthetic-')
fixture = create_fixture(Path(directory.name))
app = create_app(Path(directory.name), allowed_origins={'http://127.0.0.1:8003'},
                 imaging_path=ROOT / 'data' / 'qa-imaging' / 'orthanc.json', analysis_enabled=False)
