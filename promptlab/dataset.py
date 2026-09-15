import hashlib
import json
from .config import DATASET_PATH


def load_cases():
    cases = json.loads(DATASET_PATH.read_text())
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Dataset case IDs must be unique")
    for case in cases:
        if not isinstance(case["input"], str) or not case["input"].strip():
            raise ValueError("Dataset inputs must be nonempty strings")
        expected = case["expected"]
        if set(expected) != {"category", "priority"}:
            raise ValueError("Invalid expected output")
        if expected["category"] not in {"bug", "billing", "feature", "account"}:
            raise ValueError("Invalid expected category")
        if expected["priority"] not in {"normal", "high"}:
            raise ValueError("Invalid expected priority")
    return cases


def dataset_hash():
    # Exact bytes identify the checked-in dataset, including expected labels.
    return hashlib.sha256(DATASET_PATH.read_bytes()).hexdigest()
