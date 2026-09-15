import pytest
from promptlab.dataset import load_cases
from promptlab.db import save_result
from promptlab.evaluation import evaluate

CASES = load_cases()


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_prompt_case(case, evaluation_context):
    run, provider = evaluation_context
    result = evaluate(case, run["template"], provider)
    if run["id"] is not None:
        save_result(run["id"], result)
    assert result.error is None, f"Execution failed: {result.error}"
    assert result.format_ok, "Output must match the JSON classification schema"
    assert result.accuracy_ok, f"Classification differs from {case['expected']}"
