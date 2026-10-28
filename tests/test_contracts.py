import pytest
from pydantic import ValidationError

from ai_reviewer.contracts import Finding, Verification, validate_locations


VALID = dict(candidate_id="c1", rule_id="logic", severity="high", confidence=0.9,
             path="src/a.py", line=4, side="RIGHT", end_line=5, title="Bug",
             evidence="x can be null", impact="crash", recommendation="guard x",
             root_cause_key="null-x")


def test_finding_and_verification_are_strict():
    finding = Finding.model_validate(VALID)
    assert finding.path == "src/a.py"
    with pytest.raises(ValidationError):
        Finding.model_validate({**VALID, "surprise": True})
    with pytest.raises(ValidationError):
        Verification.model_validate({"candidate_id": "c1", "decision": "maybe"})


def test_paths_are_relative_and_lines_must_exist_in_patch():
    with pytest.raises(ValidationError):
        Finding.model_validate({**VALID, "path": "../secret"})
    finding = Finding.model_validate(VALID)
    validate_locations([finding], {"src/a.py": {3, 4, 5}})
    with pytest.raises(ValueError, match="patch"):
        validate_locations([finding], {"src/a.py": {3}})


def test_ranges_and_model_output_are_bounded():
    with pytest.raises(ValidationError, match="end_line"):
        Finding.model_validate({**VALID, "line": 5, "end_line": 4})
    with pytest.raises(ValidationError):
        Finding.model_validate({**VALID, "title": "x" * 201})
    with pytest.raises(ValidationError):
        Verification.model_validate({"candidate_id": "c1", "decision": "amend"})
    with pytest.raises(ValidationError):
        Verification.model_validate({"candidate_id": "c1", "decision": "amend",
                                     "amendment": {**VALID, "candidate_id": "other"}})


def test_contracts_reject_coercion_whitespace_and_unbounded_suggestions():
    with pytest.raises(ValidationError):
        Finding.model_validate({**VALID, "line": "4"})
    with pytest.raises(ValidationError):
        Finding.model_validate({**VALID, "candidate_id": " c1"})
    from ai_reviewer.contracts import SuggestionBatch
    with pytest.raises(ValidationError):
        SuggestionBatch.model_validate({"suggestions": ["x" * 2001]})
