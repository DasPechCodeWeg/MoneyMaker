"""Small, serializable representations of bounty evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

EscrowStatus = Literal["unknown", "not_escrowed", "verified_escrow"]
Severity = Literal["blocker", "warning", "info"]
Verdict = Literal["PASS", "CAUTION", "REJECT"]


@dataclass(frozen=True)
class Listing:
    issue_url: str
    amount: float = 0.0
    currency: str = "USD"
    platform: str = "unknown"
    listed_status: str = "open"
    claims: int = 0
    escrow_status: EscrowStatus = "unknown"
    human_only: bool = False

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError("Reward amount cannot be negative")
        if self.claims < 0:
            raise ValueError("Claim count cannot be negative")
        if self.escrow_status not in {
            "unknown",
            "not_escrowed",
            "verified_escrow",
        }:
            raise ValueError(f"Unsupported escrow status: {self.escrow_status}")


@dataclass(frozen=True)
class IssueSnapshot:
    url: str
    state: str
    title: str = ""
    body: str = ""
    comments: int = 0
    updated_at: str | None = None
    author_association: str = "NONE"
    locked: bool = False


@dataclass(frozen=True)
class RepositorySnapshot:
    full_name: str
    archived: bool = False
    disabled: bool = False
    pushed_at: str | None = None
    stargazers_count: int = 0


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    message: str
    evidence: str


@dataclass
class Assessment:
    listing: Listing
    issue: IssueSnapshot
    repository: RepositorySnapshot
    score: int
    verdict: Verdict
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
