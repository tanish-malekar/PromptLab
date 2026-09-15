"""API evaluations execute the same pytest suite users can invoke directly."""
import os
import subprocess
import sys
from .config import ROOT, DB_PATH
from .db import connect, now


def execute_run(run_id):
    env = {**os.environ, "PROMPTLAB_RUN_ID": str(run_id), "PROMPTLAB_DB": str(DB_PATH)}
    # Disable ambient plugins/options so unrelated local pytest configuration
    # cannot silently change the evaluation. This still loads our conftest.
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("PYTEST_PLUGINS", None)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_prompt_suite.py", "-q", "--tb=no"],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=3600, check=False,
        )
        with connect() as db:
            count = db.execute("SELECT COUNT(*) FROM results WHERE run_id=?", (run_id,)).fetchone()[0]
            total = db.execute("SELECT total_cases FROM runs WHERE id=?", (run_id,)).fetchone()[0]
            complete = result.returncode in (0, 1) and count == total
            db.execute("""UPDATE runs SET status=?,finished_at=?,exit_code=?,error=?
                       WHERE id=? AND status='running'""",
                       ("completed" if complete else "failed", now(), result.returncode,
                        None if complete else "Pytest did not persist the complete dataset", run_id))
    except (OSError, subprocess.TimeoutExpired):
        with connect() as db:
            db.execute("UPDATE runs SET status='failed',finished_at=?,error=? WHERE id=? AND status='running'",
                       (now(), "Evaluation process failed or exceeded one hour", run_id))
