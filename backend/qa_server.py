"""Browser test server: isolated temporary DB, never production data."""
from pathlib import Path
from tempfile import TemporaryDirectory
from .app import create_app

directory = TemporaryDirectory(prefix='chest-review-qa-')
app = create_app(Path(directory.name), allowed_origins={'http://127.0.0.1:8001'}, imaging_path=Path(__file__).resolve().parents[1]/'data'/'qa-imaging'/'orthanc.json', analysis_enabled=False)
