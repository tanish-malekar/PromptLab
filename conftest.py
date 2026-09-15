import os
import pytest
from promptlab.config import DEFAULT_PROMPT
from promptlab.dataset import dataset_hash
from promptlab.db import connect
from promptlab.providers import make_provider


@pytest.fixture(scope="session")
def evaluation_context():
    raw_id = os.environ.get("PROMPTLAB_RUN_ID")
    if raw_id:
        with connect() as db:
            record = db.execute("SELECT * FROM runs WHERE id=?", (int(raw_id),)).fetchone()
            if record is None or record["status"] != "running":
                raise ValueError("Requested evaluation run is not running")
            if record["dataset_sha"] != dataset_hash():
                raise ValueError("Dataset changed after run admission")
            run = dict(record)
    else:
        # Direct pytest execution always defaults to mock; it cannot incur API costs.
        run = {"id": None, "template": DEFAULT_PROMPT, "provider": "mock", "model": "mock"}
    provider = make_provider(run["provider"], run["model"])
    yield run, provider
    provider.close()
