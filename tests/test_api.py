import pytest
from fastapi.testclient import TestClient
from promptlab import api, db
from promptlab.config import DEFAULT_PROMPT


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.sqlite3")
    # Contract tests never launch a nested evaluation process.
    monkeypatch.setattr(api, "execute_run", lambda run_id: None)
    with TestClient(api.app) as client:
        yield client


def test_prompt_versions_are_immutable_and_duplicate_content_is_rejected(client):
    original = client.get("/api/prompts").json()[0]
    body = {"name": original["name"], "template": DEFAULT_PROMPT + "\nBe concise."}
    saved = client.post("/api/prompts", json=body)
    assert saved.status_code == 201
    assert saved.json()["version"] == 2
    assert client.post("/api/prompts", json=body).status_code == 409
    versions = {p["version"]: p for p in client.get("/api/prompts").json()}
    assert versions[1]["template"] == original["template"]


def test_missing_placeholder_is_rejected(client):
    assert client.post("/api/prompts", json={"name": "invalid", "template": "No placeholder"}).status_code == 422


def test_run_captures_saved_prompt_and_dataset_without_initial_results(client):
    prompt = client.get("/api/prompts").json()[0]
    response = client.post("/api/runs", json={"prompt_id": prompt["id"]})
    assert response.status_code == 202
    run = client.get(f"/api/runs/{response.json()['id']}").json()
    assert run["template"] == prompt["template"]
    assert run["total"] == 200 and run["evaluated"] == 0
    assert run["release_gate_passed"] is False
    assert run["dataset_sha"] == client.get("/api/health").json()["dataset_sha"]


def test_running_run_cannot_be_used_as_baseline(client):
    prompt = client.get("/api/prompts").json()[0]
    baseline = client.post("/api/runs", json={"prompt_id": prompt["id"]}).json()
    response = client.post("/api/runs", json={"prompt_id": prompt["id"], "baseline_id": baseline["id"]})
    assert response.status_code == 409
