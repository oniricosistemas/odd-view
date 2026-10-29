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
    from ai_reviewer.contracts import SuggestionBatch
    with pytest.raises(ValidationError):
        SuggestionBatch.model_validate({"suggestions": ["x" * 2001]})


def test_finding_strips_whitespace_instead_of_rejecting():
    """Whitespace-padded strings are stripped (fix for ValidationError on LLM output)."""
    result = Finding.model_validate({**VALID, "candidate_id": "  c1  ",
                                     "rule_id": "  logic  "})
    assert result.candidate_id == "c1"
    assert result.rule_id == "logic"


def test_finding_strips_evidence_whitespace():
    """When the LLM returns evidence with leading/trailing whitespace, it should be stripped."""
    result = Finding.model_validate({**VALID, "evidence": "  x can be null  ",
                                     "impact": "  crash  ", "recommendation": "  guard x  "})
    assert result.evidence == "x can be null"
    assert result.impact == "crash"
    assert result.recommendation == "guard x"


def test_finding_strips_all_string_fields():
    """All string fields should have outer whitespace stripped."""
    result = Finding.model_validate({
        **VALID,
        "candidate_id": "  c1  ",
        "rule_id": "  logic  ",
        "path": "  src/a.py  ",
        "title": "  Bug  ",
        "evidence": "  x can be null  ",
        "impact": "  crash  ",
        "recommendation": "  guard x  ",
        "root_cause_key": "  null-x  ",
    })
    assert result.candidate_id == "c1"
    assert result.rule_id == "logic"
    assert result.path == "src/a.py"
    assert result.title == "Bug"
    assert result.evidence == "x can be null"
    assert result.impact == "crash"
    assert result.recommendation == "guard x"
    assert result.root_cause_key == "null-x"
