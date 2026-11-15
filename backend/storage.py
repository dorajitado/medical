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
                UPDATE import_jobs SET status='interrupted', last_issue='Application restarted'
                    WHERE status='running';
                PRAGMA user_version=2;
            ''')
        # Only managed staging files are disposable; originals are never removed here.
        for file in (self.root / 'staging').glob('*.part'):
            file.unlink(missing_ok=True)
