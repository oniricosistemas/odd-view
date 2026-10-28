from ai_reviewer.contracts import Finding, Verification
import pytest

from ai_reviewer.reducer import reduce_findings


def make(i, severity="medium", root=None):
    return Finding(candidate_id=f"c{i}", rule_id="r", severity=severity, confidence=0.8,
        path=f"src/{i}.py", line=1, side="RIGHT", title=f"t{i}", evidence="e",
        impact="i", recommendation="r", root_cause_key=root or f"root-{i}")


def test_reducer_applies_verdicts_deduplicates_and_caps_at_eight():
    findings = [make(i, "high" if i == 9 else "medium", "same" if i in (0, 1) else None)
                for i in range(10)]
    verdicts = [Verification(candidate_id=f"c{i}", decision="reject" if i == 2 else "confirm")
                for i in range(10)]
    reduced = reduce_findings(findings, verdicts)
    assert len(reduced) == 8
    assert reduced[0].finding.candidate_id == "c9"
    assert len({item.fingerprint for item in reduced}) == 8
    assert "c2" not in {item.finding.candidate_id for item in reduced}


def test_reducer_fails_closed_and_revalidates_amendment_location():
    original = make(1)
    assert reduce_findings([original], []) == []
    amended = make(1).model_copy(update={"line": 9})
    verdict = Verification(candidate_id="c1", decision="amend", amendment=amended)
    try:
        reduce_findings([original], [verdict], {"src/1.py": {1}})
    except ValueError as exc:
        assert "outside patch" in str(exc)
    else:
        raise AssertionError("amendment outside patch was accepted")


def test_duplicate_candidate_ids_and_contradictory_verdicts_fail_closed():
    finding = make(1)
    duplicate = make(2).model_copy(update={"candidate_id": finding.candidate_id})
    with pytest.raises(ValueError, match="duplicate candidate"):
        reduce_findings([finding, duplicate], [Verification(candidate_id="c1", decision="confirm")])
    with pytest.raises(ValueError, match="contradictory"):
        reduce_findings([finding], [Verification(candidate_id="c1", decision="reject"),
                                    Verification(candidate_id="c1", decision="confirm")])


def test_verdict_for_unknown_candidate_fails_closed():
    with pytest.raises(ValueError, match="unknown candidate"):
        reduce_findings([make(1)], [Verification(candidate_id="other", decision="confirm")])
