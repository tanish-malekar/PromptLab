import hashlib
import sqlite3
import threading
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator
from .dataset import dataset_hash, load_cases
from .db import connect, initialize, now, result_rows
from .evaluation import compare
from .runner import execute_run

slots = threading.BoundedSemaphore(2)


@asynccontextmanager
async def lifespan(app):
    initialize()
    # Local single-process service. Interrupted runs are never presented as complete.
    with connect() as db:
        db.execute("UPDATE runs SET status='interrupted',finished_at=?,error=? WHERE status='running'",
                   (now(), "Server restarted during evaluation"))
    yield


app = FastAPI(title="PromptLab", version="0.1.0", lifespan=lifespan)


class PromptInput(BaseModel):
    name: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    template: str = Field(min_length=1, max_length=20000)

    @field_validator("template")
    @classmethod
    def has_input(cls, value):
        if "{{input}}" not in value:
            raise ValueError("Include the {{input}} placeholder")
        return value


class RunInput(BaseModel):
    prompt_id: int = Field(gt=0)
    provider: Literal["mock", "http"] = "mock"
    model: str = Field(default="mock", min_length=1, max_length=200)
    baseline_id: int | None = Field(default=None, gt=0)


@app.get("/api/health")
def health():
    return {"status": "ok", "dataset_cases": len(load_cases()), "dataset_sha": dataset_hash()}


@app.get("/api/prompts")
def prompts():
    with connect() as db:
        return [dict(row) for row in db.execute("SELECT * FROM prompts ORDER BY id DESC")]


@app.post("/api/prompts", status_code=201)
def create_prompt(body: PromptInput):
    try:
        with connect() as db:
            # Reserve the next version while holding the writer lock.
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("SELECT COALESCE(MAX(version),0)+1 FROM prompts WHERE name=?",
                                 (body.name,)).fetchone()[0]
            cursor = db.execute("INSERT INTO prompts(name,version,template,sha256,created_at) VALUES(?,?,?,?,?)",
                                (body.name, version, body.template,
                                 hashlib.sha256(body.template.encode()).hexdigest(), now()))
            return dict(db.execute("SELECT * FROM prompts WHERE id=?", (cursor.lastrowid,)).fetchone())
    except sqlite3.IntegrityError:
        raise HTTPException(409, "This prompt content already exists under that name") from None


def run_summary(db, record):
    run = dict(record)
    rows = result_rows(db, run["id"])
    baseline = result_rows(db, run["baseline_id"]) if run["baseline_id"] else []
    compared = compare(rows, baseline)
    run.update(total=run["total_cases"], evaluated=len(rows),
               passed=sum(bool(r["format_ok"] and r["accuracy_ok"] and not r["error"]) for r in rows),
               execution_errors=sum(bool(r["error"]) for r in rows),
               format_failures=sum(not r["format_ok"] and not r["error"] for r in rows),
               accuracy_failures=sum(not r["accuracy_ok"] and not r["error"] for r in rows),
               regressions=sum(r["regression"] for r in compared))
    run["release_gate_passed"] = (run["status"] == "completed" and run["evaluated"] == run["total"]
                                  and run["passed"] == run["total"] and run["regressions"] == 0)
    return run


@app.get("/api/runs")
def runs():
    with connect() as db:
        records = db.execute("""SELECT r.*,p.name AS prompt_name,p.version AS prompt_version
                             FROM runs r JOIN prompts p ON p.id=r.prompt_id ORDER BY r.id DESC LIMIT 100""").fetchall()
        return [run_summary(db, row) for row in records]


@app.get("/api/runs/{run_id}")
def run_details(run_id: int):
    with connect() as db:
        record = db.execute("""SELECT r.*,p.name AS prompt_name,p.version AS prompt_version
                            FROM runs r JOIN prompts p ON p.id=r.prompt_id WHERE r.id=?""", (run_id,)).fetchone()
        if record is None:
            raise HTTPException(404, "Run not found")
        result = run_summary(db, record)
        baseline = result_rows(db, record["baseline_id"]) if record["baseline_id"] else []
        result["results"] = compare(result_rows(db, run_id), baseline)
        return result


def finish_run(run_id):
    try:
        execute_run(run_id)
    except Exception:
        with connect() as db:
            db.execute("UPDATE runs SET status='failed',finished_at=?,error=? WHERE id=? AND status='running'",
                       (now(), "Internal evaluation failure", run_id))
    finally:
        slots.release()


@app.post("/api/runs", status_code=202)
def start_run(body: RunInput, tasks: BackgroundTasks):
    if not slots.acquire(blocking=False):
        raise HTTPException(429, "Two evaluations are already active; retry after completion")
    try:
        fingerprint = dataset_hash()
        with connect() as db:
            prompt = db.execute("SELECT * FROM prompts WHERE id=?", (body.prompt_id,)).fetchone()
            if prompt is None:
                raise HTTPException(404, "Prompt version not found")
            if body.baseline_id:
                baseline = db.execute("""SELECT r.*,p.name AS prompt_name FROM runs r
                                       JOIN prompts p ON p.id=r.prompt_id WHERE r.id=?""", (body.baseline_id,)).fetchone()
                if baseline is None or baseline["status"] != "completed":
                    raise HTTPException(409, "Baseline must be a completed run")
                if (baseline["dataset_sha"], baseline["provider"], baseline["model"], baseline["prompt_name"]) != (
                        fingerprint, body.provider, body.model, prompt["name"]):
                    raise HTTPException(409, "Baseline must match dataset, provider, model, and prompt name")
            cursor = db.execute("""INSERT INTO runs(prompt_id,template,dataset_sha,provider,model,total_cases,baseline_id,status,started_at)
                                 VALUES(?,?,?,?,?,?,?,'running',?)""",
                                (body.prompt_id, prompt["template"], fingerprint,
                                 body.provider, body.model, len(load_cases()), body.baseline_id, now()))
            run_id = cursor.lastrowid
        tasks.add_task(finish_run, run_id)
        return {"id": run_id, "status": "running"}
    except Exception:
        slots.release()
        raise
