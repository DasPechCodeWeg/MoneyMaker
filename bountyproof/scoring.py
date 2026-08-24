"""Deterministic risk rules with inspectable evidence."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from .models import Assessment, Finding, IssueSnapshot, Listing, RepositorySnapshot

AI_REJECTION_PATTERNS = (
    r"\bai[- ]generated\s+(?:prs?|pull requests?|contributions?|submissions?)"
    r"[\s\S]{0,100}\b(?:closed|rejected|not accepted|not allowed|forbidden)\b",
    r"\b(?:do not|don't|never)\s+(?:submit|open|create)\s+"
    r"(?:ai[- ]generated|llm[- ]generated)\b",
    r"\b(?:no|without)\s+(?:ai[- ]generated|llm[- ]generated)\s+"
    r"(?:prs?|pull requests?|contributions?|submissions?)\b",
)

NO_NEW_PULL_REQUEST_PATTERNS = (
    r"\bplease\s+do\s+not\s+open\s+(?:any\s+)?new\s+"
    r"(?:prs?|pull requests?)\b",
    r"\b(?:do not|don't)\s+(?:submit|open)\s+(?:another|new)\s+"
    r"(?:pr|pull request)\b",
)

EXPLICIT_NONPAYMENT_PATTERNS = (
    r"\bbount(?:y|ies)\s+(?:is|are)\s+symbolic\b",
    r"\bno\s+monetary\s+(?:value|reward)\b",
    r"\bnot\s+(?:a\s+)?real[- ]world\s+payout\b",
    r"\bwill\s+never\s+be\s+merged\b",
    r"\bdo\s+not\s+expect[\s\S]{0,80}(?:pay|money|merge)\b",
)

HIDDEN_AGENT_INSTRUCTION_PATTERNS = (
    r"<!--[\s\S]{0,1500}\bignore\s+(?:all\s+)?(?:previous|prior)\s+instructions\b[\s\S]{0,1500}-->",
    r"<!--[\s\S]{0,1500}\b(?:system\s+prompt|environment\s+variables?|session\s+data)\b[\s\S]{0,1500}-->",
    r"<!--[\s\S]{0,1500}\b(?:exfiltrat|leak\s+secrets?)\b[\s\S]{0,1500}-->",
)


def _age_in_days(value: str | None, now: datetime) -> int | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0, (now - parsed.astimezone(timezone.utc)).days)


def _contains_any(patterns: tuple[str, ...], value: str) -> bool:
    return any(re.search(pattern, value, re.IGNORECASE) for pattern in patterns)


def assess(
    listing: Listing,
    issue: IssueSnapshot,
    repository: RepositorySnapshot,
    *,
    maintainer_text: str = "",
    now: datetime | None = None,
) -> Assessment:
    """Assess evidence without implying that displayed rewards are funded."""
    current = now or datetime.now(timezone.utc)
    findings: list[Finding] = []
    score = 100
    combined_policy = "\n".join((issue.body, maintainer_text))

    def add(code: str, severity: str, message: str, evidence: str, cost: int) -> None:
        nonlocal score
        findings.append(Finding(code, severity, message, evidence))
        score -= cost

    if issue.state.lower() != "open":
        add(
            "ISSUE_CLOSED",
            "blocker",
            "The upstream GitHub issue is not open.",
            f"GitHub state: {issue.state}; listing state: {listing.listed_status}",
            100,
        )

    if repository.archived or repository.disabled:
        reason = "archived" if repository.archived else "disabled"
        add(
            "REPOSITORY_INACTIVE",
            "blocker",
            "The upstream repository cannot accept ordinary contributions.",
            f"Repository is {reason}.",
            100,
        )

    expected_fragment = f"github.com/{repository.full_name}/issues/"
    if expected_fragment.lower() not in issue.url.lower():
        add(
            "REPOSITORY_MISMATCH",
            "blocker",
            "The issue does not belong to the advertised repository.",
            f"Issue: {issue.url}; repository: {repository.full_name}",
            100,
        )

    if listing.listed_status.lower() not in {"open", "available", "active"}:
        add(
            "LISTING_NOT_AVAILABLE",
            "blocker",
            "The bounty listing does not advertise an available reward.",
            f"Listing state: {listing.listed_status}",
            100,
        )

    if listing.human_only or _contains_any(AI_REJECTION_PATTERNS, combined_policy):
        add(
            "AI_CONTRIBUTIONS_REJECTED",
            "blocker",
            "Maintainer instructions or listing rules exclude AI-generated work.",
            "Human-only flag or explicit rejection language was detected.",
            100,
        )

    if _contains_any(NO_NEW_PULL_REQUEST_PATTERNS, combined_policy):
        add(
            "MAINTAINER_REJECTS_NEW_PRS",
            "blocker",
            "A maintainer instructed contributors not to open new pull requests.",
            "Explicit no-new-PR language was detected.",
            100,
        )

    if _contains_any(EXPLICIT_NONPAYMENT_PATTERNS, combined_policy):
        add(
            "EXPLICIT_NONPAYMENT",
            "blocker",
            "The repository explicitly says the displayed bounty is not real compensation.",
            "A symbolic, no-payment, or never-merge disclaimer was detected.",
            100,
        )

    if _contains_any(HIDDEN_AGENT_INSTRUCTION_PATTERNS, combined_policy):
        add(
            "HIDDEN_AGENT_INSTRUCTIONS",
            "blocker",
            "Hidden repository text attempts to direct automated agents or request sensitive context.",
            "An instruction-like HTML comment was detected; repository text is untrusted input.",
            100,
        )

    if issue.locked:
        add(
            "ISSUE_LOCKED",
            "warning",
            "The issue is locked; claiming or coordinating may be impossible.",
            "GitHub reports locked=true.",
            20,
        )

    if listing.amount <= 0:
        add(
            "NO_CASH_REWARD",
            "warning",
            "No positive cash reward was supplied.",
            f"Displayed amount: {listing.currency} {listing.amount:.2f}",
            25,
        )
    elif listing.escrow_status == "not_escrowed":
        add(
            "REWARD_NOT_ESCROWED",
            "warning",
            "The sponsor has not reserved the reward in verified escrow.",
            f"{listing.platform} reward: {listing.currency} {listing.amount:.2f}",
            25,
        )
    elif listing.escrow_status == "unknown":
        add(
            "FUNDING_UNVERIFIED",
            "warning",
            "A displayed amount does not prove funds exist or will be paid.",
            f"{listing.platform} reward: {listing.currency} {listing.amount:.2f}",
            15,
        )
    else:
        findings.append(
            Finding(
                "ESCROW_REPORTED",
                "info",
                "The caller reported independently verified escrow.",
                "This evidence was supplied by the caller, not inferred.",
            )
        )

    issue_age = _age_in_days(issue.updated_at, current)
    if issue_age is not None and issue_age > 180:
        add(
            "STALE_ISSUE",
            "warning",
            "The issue has not been updated recently.",
            f"Last issue update: {issue_age} days ago.",
            20,
        )

    repo_age = _age_in_days(repository.pushed_at, current)
    if repo_age is not None and repo_age > 180:
        add(
            "STALE_REPOSITORY",
            "warning",
            "The repository has not received a recent push.",
            f"Last repository push: {repo_age} days ago.",
            20,
        )

    if issue.comments >= 100:
        add(
            "EXCESSIVE_COMMENTS",
            "warning",
            "The issue has an unusually large comment count.",
            f"GitHub reports {issue.comments} comments.",
            20,
        )

    if listing.claims >= 10:
        add(
            "HEAVY_COMPETITION",
            "warning",
            "Many contributors have already claimed the same reward.",
            f"Claimed by {listing.claims} contributors.",
            15,
        )

    bounded = max(0, min(100, score))
    has_blocker = any(item.severity == "blocker" for item in findings)
    has_warning = any(item.severity == "warning" for item in findings)
    verdict = "REJECT" if has_blocker else "CAUTION" if has_warning else "PASS"
    return Assessment(listing, issue, repository, bounded, verdict, findings)
