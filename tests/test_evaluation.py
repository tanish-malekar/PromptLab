import pytest
from promptlab.evaluation import check_output, compare, evaluate


@pytest.mark.parametrize("output", ["billing", "```json\n{}\n```", "[]", "null", '{"category":"billing"}',
                                    '{"category":"billing","priority":"high","extra":true}'])
def test_rejects_format_drift(output):
    assert check_output(output, {"category": "billing", "priority": "high"}) == (False, False)


def test_wrong_valid_label_is_accuracy_failure():
    assert check_output('{"category":"bug","priority":"high"}',
                        {"category": "billing", "priority": "high"}) == (True, False)


def test_regression_count_does_not_double_count_case():
    old = [{"case_id": "a", "format_ok": True, "accuracy_ok": True, "output": "old", "error": None}]
    new = [{"case_id": "a", "format_ok": False, "accuracy_ok": False, "output": "new", "error": None}]
    row, = compare(new, old)
    assert row["regression"] and row["format_regression"] and row["accuracy_regression"]
    assert sum(r["regression"] for r in compare(new, old)) == 1


def test_provider_failure_is_not_mislabeled_as_quality_regression():
    old = [{"case_id": "a", "format_ok": True, "accuracy_ok": True, "output": "old", "error": None}]
    new = [{"case_id": "a", "format_ok": False, "accuracy_ok": False, "output": "", "error": "TimeoutError"}]
    assert not compare(new, old)[0]["regression"]


def test_provider_never_receives_expected_labels():
    class CapturingProvider:
        def complete(self, prompt, ticket):
            assert prompt == "Classify: sample ticket"
            assert ticket == "sample ticket"
            return '{"category":"bug","priority":"normal"}'
    result = evaluate({"id": "x", "input": "sample ticket", "expected": {"category": "bug", "priority": "normal"}},
                      "Classify: {{input}}", CapturingProvider())
    assert result.format_ok and result.accuracy_ok
