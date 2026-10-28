import hashlib
from dataclasses import dataclass

from .contracts import Finding, Verification, validate_locations


@dataclass(frozen=True)
class ReducedFinding:
    finding: Finding
    fingerprint: str


def _fingerprint(finding: Finding) -> str:
    value = "\0".join((finding.rule_id, finding.path, str(finding.line), finding.root_cause_key))
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def reduce_findings(findings: list[Finding], verdicts: list[Verification],
                    patch_lines: dict[str, set[int]] | None = None) -> list[ReducedFinding]:
    candidate_ids = [finding.candidate_id for finding in findings]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ValueError("duplicate candidate id")
    known = set(candidate_ids)
    decisions: dict[str, Verification] = {}
    for verdict in verdicts:
        if verdict.candidate_id not in known:
            raise ValueError("verdict references unknown candidate")
        previous = decisions.get(verdict.candidate_id)
        if previous is not None:
            if previous != verdict:
                raise ValueError("contradictory verdicts")
            raise ValueError("duplicate verdict")
        decisions[verdict.candidate_id] = verdict
    accepted: list[Finding] = []
    roots: set[str] = set()
    for finding in findings:
        verdict = decisions.get(finding.candidate_id)
        if verdict is None or verdict.decision == "reject":
            continue
        if verdict and verdict.decision == "amend" and verdict.amendment:
            finding = verdict.amendment
        if finding.root_cause_key in roots:
            continue
        roots.add(finding.root_cause_key)
        accepted.append(finding)
    if patch_lines is not None:
        validate_locations(accepted, patch_lines)
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    accepted.sort(key=lambda f: (rank[f.severity], -f.confidence, f.path, f.line, f.candidate_id))
    return [ReducedFinding(f, _fingerprint(f)) for f in accepted[:8]]
