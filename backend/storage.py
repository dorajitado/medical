from contextlib import contextmanager
from pathlib import Path
import sqlite3


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.database = root / 'workspace.sqlite3'

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.database, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def initialize(self):
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / 'originals').mkdir(exist_ok=True)
        (self.root / 'staging').mkdir(exist_ok=True)
        with self.connect() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS studies (
                    id TEXT PRIMARY KEY, study_uid TEXT NOT NULL UNIQUE,
                    study_date TEXT, description TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS preferences (
                    id INTEGER PRIMARY KEY CHECK(id=1),
                    show_structure INTEGER NOT NULL CHECK(show_structure IN (0,1))
                );
                INSERT OR IGNORE INTO preferences VALUES (1,1);
                CREATE TABLE IF NOT EXISTS series (
                    id TEXT PRIMARY KEY, series_uid TEXT UNIQUE NOT NULL,
                    study_id TEXT NOT NULL REFERENCES studies(id), metadata TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS instances (
                    id TEXT PRIMARY KEY, sop_uid TEXT UNIQUE NOT NULL,
                    series_id TEXT NOT NULL REFERENCES series(id),
                    sha256 TEXT NOT NULL, stored_name TEXT UNIQUE NOT NULL,
                    metadata TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS import_jobs (
                    id TEXT PRIMARY KEY, status TEXT NOT NULL,
                    total INTEGER NOT NULL, imported INTEGER NOT NULL DEFAULT 0,
                    duplicates INTEGER NOT NULL DEFAULT 0, excluded INTEGER NOT NULL DEFAULT 0,
                    failed INTEGER NOT NULL DEFAULT 0, last_issue TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS report_versions (
                    id TEXT PRIMARY KEY, study_id TEXT NOT NULL REFERENCES studies(id),
                    source TEXT NOT NULL, text TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                -- Each attempt has its own immutable source/configuration snapshot.
                -- Only status/stage/timing changes; previous completed outputs survive reruns.
                CREATE TABLE IF NOT EXISTS analysis_runs (
                    id TEXT PRIMARY KEY, series_id TEXT NOT NULL REFERENCES series(id),
                    model_id TEXT NOT NULL, status TEXT NOT NULL,
                    stage TEXT NOT NULL, snapshot TEXT NOT NULL,
                    error TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    started_at TEXT, finished_at TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS analysis_series ON analysis_runs(series_id,created_at);
                -- Appended versions keep machine extraction, source text and
                -- user interpretation separate. Payloads are immutable JSON.
                CREATE TABLE IF NOT EXISTS extraction_versions (
                    id TEXT PRIMARY KEY, report_id TEXT NOT NULL REFERENCES report_versions(id),
                    study_id TEXT NOT NULL REFERENCES studies(id), parent_id TEXT,
                    origin TEXT NOT NULL, items TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS comparison_versions (
                    id TEXT PRIMARY KEY, study_id TEXT NOT NULL REFERENCES studies(id),
                    extraction_id TEXT NOT NULL REFERENCES extraction_versions(id),
                    parent_id TEXT, origin TEXT NOT NULL, payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS review_versions (
                    id TEXT PRIMARY KEY, study_id TEXT NOT NULL REFERENCES studies(id),
                    target_type TEXT NOT NULL, target_id TEXT NOT NULL,
                    decision TEXT NOT NULL, note TEXT NOT NULL, question TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS summary_versions (
                    id TEXT PRIMARY KEY, study_id TEXT NOT NULL REFERENCES studies(id),
                    payload TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS audit_events (
                    id TEXT PRIMARY KEY, study_id TEXT, action TEXT NOT NULL,
                    entity_id TEXT NOT NULL, details TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS source_documents (
                    id TEXT PRIMARY KEY, study_id TEXT NOT NULL REFERENCES studies(id),
                    media_type TEXT NOT NULL, sha256 TEXT NOT NULL,
                    stored_name TEXT NOT NULL, status TEXT NOT NULL, pages TEXT,
                    error TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS longitudinal_versions (
                    id TEXT PRIMARY KEY, current_study TEXT NOT NULL REFERENCES studies(id),
                    prior_study TEXT NOT NULL REFERENCES studies(id),
                    payload TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS model_comparison_versions (
                    id TEXT PRIMARY KEY, study_id TEXT NOT NULL REFERENCES studies(id),
                    parent_id TEXT, payload TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS evaluation_cases (
                    id TEXT PRIMARY KEY, study_id TEXT REFERENCES studies(id), split TEXT NOT NULL,
                    reference_source TEXT NOT NULL, reviewer TEXT NOT NULL,
                    payload TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                -- Never expose partially written files as completed after a restart.
                UPDATE analysis_runs SET status='failed',stage='interrupted',
                    error='서버 재시작으로 중단되었습니다. 새 실행을 시작해 주세요.',
                    finished_at=CURRENT_TIMESTAMP WHERE status IN ('queued','running');
                UPDATE import_jobs SET status='interrupted', last_issue='Application restarted'
                    WHERE status='running';
                UPDATE source_documents SET status='failed',error='서버 재시작으로 문서 추출이 중단되었습니다. 원본을 다시 등록해 주세요.'
                    WHERE status='running';
                PRAGMA user_version=4;
            ''')
        # Only managed staging files are disposable; originals are never removed here.
        for file in (self.root / 'staging').glob('*.part'):
            file.unlink(missing_ok=True)
        # Restore file moves from a deletion interrupted before its DB commit.
        from .maintenance import recover_deletions
        recover_deletions(self)
