import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("PROMPTLAB_DB", ROOT / "data" / "promptlab.sqlite3")).resolve()
DATASET_PATH = ROOT / "datasets" / "tickets.json"
DEFAULT_PROMPT = """Classify the support ticket below.
Return only a JSON object with exactly two string keys: category and priority.
Category must be bug, billing, feature, or account.
Use high priority when the ticket says urgent, otherwise normal.
Ticket: {{input}}"""
