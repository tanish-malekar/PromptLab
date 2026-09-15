"""The same evaluator is used by pytest and persisted API evaluations."""
import json
import time
from dataclasses import asdict, dataclass


@dataclass
class Evaluation:
    case_id: str
    input: str
    expected: dict
    output: str
    format_ok: bool
    accuracy_ok: bool
    error: str | None
    latency_ms: float

    def as_dict(self):
        return asdict(self)


def check_output(output, expected):
    try:
        parsed = json.loads(output)
    except (ValueError, TypeError):
        return False, False
    format_ok = (
        isinstance(parsed, dict)
        and set(parsed) == {"category", "priority"}
        and isinstance(parsed.get("category"), str)
        and isinstance(parsed.get("priority"), str)
        and parsed["category"] in {"bug", "billing", "feature", "account"}
        and parsed["priority"] in {"normal", "high"}
    )
    return format_ok, bool(format_ok and parsed == expected)


def evaluate(case, template, provider):
    started = time.perf_counter()
    output, error = "", None
    try:
        if "{{input}}" not in template:
            raise ValueError("Prompt must contain {{input}}")
        rendered = template.replace("{{input}}", case["input"])
        output = provider.complete(rendered, case["input"])
        format_ok, accuracy_ok = check_output(output, case["expected"])
    except Exception as exc:
        # Do not persist credentials, full HTTP exceptions, or provider bodies.
        error = type(exc).__name__
        format_ok, accuracy_ok = False, False
    return Evaluation(
        case["id"], case["input"], case["expected"], output,
        format_ok, accuracy_ok, error,
        round((time.perf_counter() - started) * 1000, 3),
    )


def compare(candidate, baseline):
    """Count unique regressed cases, with independent format and accuracy flags.

    Provider errors are reported as execution failures rather than quality
    regressions. An output-format failure may cause both format and accuracy
    flags; the unique regression count never double-counts that case.
    """
    prior = {row["case_id"]: row for row in baseline}
    rows = []
    for row in candidate:
        old = prior.get(row["case_id"])
        comparable = old is not None and not row["error"] and not old["error"]
        format_regression = bool(comparable and old["format_ok"] and not row["format_ok"])
        accuracy_regression = bool(comparable and old["accuracy_ok"] and not row["accuracy_ok"])
        rows.append({**row, "format_regression": format_regression,
                     "accuracy_regression": accuracy_regression,
                     "regression": format_regression or accuracy_regression,
                     "baseline_output": old["output"] if old else None})
    return rows
