import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from .config import DB_PATH, DEFAULT_PROMPT


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize():
    with connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS prompts (
          id INTEGER PRIMARY KEY, name TEXT NOT NULL, version INTEGER NOT NULL,
          template TEXT NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL,
          UNIQUE(name, version), UNIQUE(name, sha256)
        );
        CREATE TABLE IF NOT EXISTS runs (
          id INTEGER PRIMARY KEY, prompt_id INTEGER NOT NULL REFERENCES prompts(id),
          template TEXT NOT NULL, dataset_sha TEXT NOT NULL, provider TEXT NOT NULL,
          model TEXT NOT NULL, total_cases INTEGER NOT NULL, baseline_id INTEGER REFERENCES runs(id),
          status TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
          exit_code INTEGER, error TEXT
        );
        CREATE TABLE IF NOT EXISTS results (
          run_id INTEGER NOT NULL REFERENCES runs(id), case_id TEXT NOT NULL,
          input TEXT NOT NULL, expected TEXT NOT NULL, output TEXT NOT NULL,
          format_ok INTEGER NOT NULL, accuracy_ok INTEGER NOT NULL, error TEXT,
          latency_ms REAL NOT NULL, PRIMARY KEY(run_id, case_id)
        );
        """)
        db.execute("INSERT OR IGNORE INTO prompts(name,version,template,sha256,created_at) VALUES(?,?,?,?,?)",
                   ("ticket-classifier", 1, DEFAULT_PROMPT,
                    hashlib.sha256(DEFAULT_PROMPT.encode()).hexdigest(), now()))


def save_result(run_id, result):
    row = result.as_dict()
    with connect() as db:
        db.execute("""INSERT INTO results
          (run_id,case_id,input,expected,output,format_ok,accuracy_ok,error,latency_ms)
          VALUES(?,?,?,?,?,?,?,?,?)""",
          (run_id, row["case_id"], row["input"], json.dumps(row["expected"]), row["output"],
           row["format_ok"], row["accuracy_ok"], row["error"], row["latency_ms"]))


def result_rows(db, run_id):
    rows = []
    for record in db.execute("SELECT * FROM results WHERE run_id=? ORDER BY case_id", (run_id,)):
        row = dict(record)
        row["expected"] = json.loads(row["expected"])
        row["format_ok"] = bool(row["format_ok"])
        row["accuracy_ok"] = bool(row["accuracy_ok"])
        rows.append(row)
    return rows
