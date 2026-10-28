from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Finding(StrictModel):
    candidate_id: str = Field(min_length=1, max_length=128)
    rule_id: str = Field(min_length=1, max_length=128)
    severity: Literal["critical", "high", "medium", "low"]
    confidence: float = Field(ge=0, le=1)
    path: str = Field(min_length=1, max_length=512)
    line: int = Field(gt=0)
    side: Literal["RIGHT"]
    end_line: int | None = Field(default=None, gt=0)
    title: str = Field(min_length=1, max_length=200)
    evidence: str = Field(min_length=1, max_length=4000)
    impact: str = Field(min_length=1, max_length=2000)
    recommendation: str = Field(min_length=1, max_length=2000)
    root_cause_key: str = Field(min_length=1, max_length=256)

    @field_validator("candidate_id", "rule_id", "path", "title", "evidence", "impact",
                     "recommendation", "root_cause_key")
    @classmethod
    def no_outer_whitespace(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("strings must not have outer whitespace")
        return value

    @field_validator("path")
    @classmethod
    def relative_safe_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or value.startswith("./"):
            raise ValueError("path must be repository-relative")
        return value

    @model_validator(mode="after")
    def ordered_range(self):
        if self.end_line is not None and self.end_line < self.line:
            raise ValueError("end_line must be greater than or equal to line")
        return self


class Verification(StrictModel):
    candidate_id: str = Field(min_length=1, max_length=128)
    decision: Literal["confirm", "reject", "amend"]
    amendment: Finding | None = None

    @model_validator(mode="after")
    def valid_amendment(self):
        if self.decision == "amend":
            if self.amendment is None or self.amendment.candidate_id != self.candidate_id:
                raise ValueError("amendment must match candidate_id")
        elif self.amendment is not None:
            raise ValueError("amendment is only valid with amend decision")
        return self


class FindingBatch(StrictModel):
    findings: list[Finding] = Field(max_length=64)


class VerificationBatch(StrictModel):
    verifications: list[Verification] = Field(max_length=64)


class SuggestionBatch(StrictModel):
    suggestions: list[Annotated[str, Field(min_length=1, max_length=2000)]] = Field(max_length=64)


def validate_locations(findings: list[Finding], patch_lines: dict[str, set[int]]) -> None:
    for finding in findings:
        lines = patch_lines.get(finding.path, set())
        end = finding.end_line or finding.line
        if any(line not in lines for line in range(finding.line, end + 1)):
            raise ValueError(f"finding {finding.candidate_id} is outside patch")
