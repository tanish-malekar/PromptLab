# PromptLab

Versioned prompt testing with **Python, FastAPI, pytest, SQLite, and React**.
Create immutable prompt versions, evaluate them against 200 checked-in synthetic
support tickets, and inspect format failures, classification errors, and changes
from a baseline in a React dashboard.

## How it works

```text
React dashboard
  -> FastAPI: save a new prompt version
  -> FastAPI: start an evaluation (optional baseline)
  -> background task launches a dedicated pytest process
  -> 200 parameterized case tests
       render saved template -> provider -> format + accuracy checks
       persist actual output and checks to SQLite
  -> React polls run history and per-case regression details
```

Each run records the immutable template, dataset SHA-256, provider kind, and model.
The pytest suite persists each evaluation before asserting the checks, so failed
cases remain visible. A pytest exit code of 1 is a completed evaluation when all
200 results exist; collection failures, missing results, and process timeouts mark
the run failed. Provider exceptions are stored as exception types and shown as
execution errors, separately from quality regressions.

## Setup

Use Python 3.11+ and a Node version matching `frontend/package.json`'s `engines`
field. Direct dependencies are pinned, and the frontend includes a dependency lockfile.
This repository is intended to run from its checkout, which contains the dataset,
pytest suite, and frontend source.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn promptlab.api:app --host 127.0.0.1 --port 8000 --workers 1
```

In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open [the dashboard](http://127.0.0.1:5173) or
[the API docs](http://127.0.0.1:8000/docs). Vite proxies `/api` to the local backend.
SQLite initializes automatically in `data/promptlab.sqlite3`, with a single seed
prompt and no evaluation results. The UI displays only data from actual runs.
The built frontend needs the same `/api` reverse proxy if deployed separately;
`npm run preview` alone does not configure that proxy.

## First evaluation

1. Select `ticket-classifier · v1`, keep the mock provider, and start an evaluation.
2. When it finishes, select its run as the baseline.
3. Edit the prompt and save a new version. Existing versions cannot be overwritten.
4. Evaluate the saved candidate against the baseline.
5. Select the candidate run to inspect expected output, actual output, baseline
   output, format and accuracy checks, latency, and regression flags.

The editor blocks evaluation while it contains unsaved changes. Saving identical
content under the same prompt name returns a conflict rather than a new version.
Prompt creation uses a SQLite write transaction to allocate versions atomically.

## Providers

### Mock

The mock adapter classifies ticket keywords without seeing expected test labels.
It returns JSON when the instruction portion of the prompt contains `JSON` and
uses urgent priority handling only when the instructions mention `urgent`.
Removing these instructions can exercise the regression UI. This behavior is a
simulation contract, not a demonstration that an LLM follows those instructions.
The fixtures contain correlated variations of 20 base examples, so mock pass rates
are not evidence of real-world model quality.

### OpenAI-compatible HTTP

Set these environment variables **before starting the backend**:

```sh
export PROMPTLAB_PROVIDER_URL=https://your-provider.example/v1/chat/completions
# Set LLM_API_KEY securely in your environment.
```

Select HTTP and enter the actual model name in the dashboard. The adapter sends a
single user message with temperature zero and reads the first text choice. Each
case is a separate request, so one evaluation can make 200 billable calls. Calls
have a 15-second timeout and a 1 MiB response limit, with no automatic retries.
Credentials stay server-side and are never sent to the dashboard.

Direct `python -m pytest` uses the mock provider by default and does not make paid
requests. API runs select their provider through a run ID passed to a dedicated
pytest subprocess. The API does not accept provider URLs from the browser.

## Checks and baseline comparison

The task expects a JSON object with exactly two string keys:

```json
{"category": "billing", "priority": "high"}
```

Allowed categories are `bug`, `billing`, `feature`, and `account`. Priority is
`normal` or `high`. Markdown fences, extra keys, invalid categories, and non-JSON
output fail format checks. Accuracy requires exact equality to the reviewed
expected labels after JSON parsing; it does not measure semantic prose quality.

A baseline must be completed and match the dataset hash, prompt name, provider
kind, and model. Comparison joins cases by ID:

- Format regression: baseline format passed, candidate format failed.
- Accuracy regression: baseline accuracy passed, candidate accuracy failed.
- Regressed cases: unique cases with either regression, counted once.
- Provider errors: visible separately and block the release gate; they do not
  inflate quality-regression counts. Cases with baseline errors are not compared.

The release gate passes only when the evaluation is complete and every case
passes with no regressions. There is no automated deployment or release action.
A run without a baseline can pass the case checks, but cannot establish the
absence of regressions relative to a prior prompt. Prompts that already failed
in the baseline remain failures even when they are not newly regressed.

Dataset hashes do not detect changes in a remote provider's model implementation.
Keep model revisions and endpoint configuration fixed when comparing versions.

## pytest

```sh
python -m pytest
# Only the 200 prompt cases:
python -m pytest tests/test_prompt_suite.py
```

`tests/test_evaluation.py` also specifies format drift, valid-but-wrong labels,
unique regression counting, provider-error classification, and provider inputs.
`tests/test_api.py` specifies immutable versioning, placeholder validation, run
snapshots, and baseline admission.
These tests specify the evaluator and API contracts.
API-triggered evaluations call only `test_prompt_suite.py`, using the exact
prompt and provider selected for the persisted run.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Dataset count and hash |
| GET | `/api/prompts` | Saved immutable prompt versions |
| POST | `/api/prompts` | Save `{name, template}` as the next version |
| GET | `/api/runs` | Latest 100 runs and summaries |
| POST | `/api/runs` | Start `{prompt_id, provider, model, baseline_id}` |
| GET | `/api/runs/{id}` | Case outputs, checks, and baseline differences |

Templates must contain the literal `{{input}}` placeholder, replaced by each
case's input without evaluating code or interpreting other template expressions.
Input labels are never included in provider calls. SQLite uses WAL, parameterized
queries, short transactions, and a ten-second busy timeout. The database stores
prompt and model outputs in plaintext; use reviewed fixtures and protect the
local database if replacing them with private data.

## Execution limits

Run **one Uvicorn worker** against a database. A process-local semaphore permits
two active evaluations; further requests return HTTP 429. Each evaluation runs its
200 cases sequentially in a separate pytest process with a one-hour process limit.
The API polls persisted results while those processes run. Avoid `--reload` during
an evaluation. Restarted runs are marked interrupted, and cannot be baselines.
Background work is local and not a durable distributed job queue; on abrupt
termination a child process may finish independently. Shut down evaluations before
restarting or upgrading the service. Use a durable worker service for multi-instance
operation. Don't edit dataset bytes while a run is active.

The service binds to loopback and has no user accounts or authentication. Add
authentication and TLS before exposing it beyond a trusted local environment.


## Layout

- `promptlab/api.py` — prompt and evaluation endpoints
- `promptlab/runner.py` — dedicated pytest execution
- `promptlab/evaluation.py` — output checks and baseline differences
- `promptlab/providers.py` — mock and HTTP adapters
- `promptlab/db.py` — SQLite schema and result persistence
- `datasets/tickets.json` — 200 synthetic cases
- `tests/` and `conftest.py` — pytest cases and provider setup
- `frontend/` — React dashboard and Vite proxy

Built on [FastAPI](https://fastapi.tiangolo.com/),
[pytest](https://docs.pytest.org/), and [React](https://react.dev/).
MIT licensed.
