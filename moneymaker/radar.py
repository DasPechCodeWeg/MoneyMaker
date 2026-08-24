"""Find open GitHub bounties without mistaking promises for payments.

Only the Python standard library is required. The runner accepts ``GITHUB_TOKEN``
or ``GH_TOKEN``; GitHub Actions supplies its short-lived repository token.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping

API_ROOT = "https://api.github.com"
MONEY_PATTERN = re.compile(r"(?<!\w)(?:US\s*)?\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", re.I)
BOUNTY_COMMAND = re.compile(
    r"/(?:bounty|reward)\s+(?:US\s*)?\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
    re.I,
)
UNACCEPTABLE_PATTERNS = (
    (re.compile(r"\bdo not (?:open|submit) (?:new )?(?:prs?|pull requests?)\b", re.I),
     "Maintainer asks contributors not to open new pull requests."),
    (re.compile(r"\b(?:no|do not use|must not use)\s+(?:generative\s+)?(?:ai|llms?)\b", re.I),
     "The issue appears to prohibit AI-assisted work."),
)


class GitHubError(RuntimeError):
    """GitHub rejected a request or returned an unusable response."""


@dataclasses.dataclass(frozen=True, slots=True)
class Opportunity:
    repository: str
    issue_number: int
    title: str
    url: str
    advertised_usd: float | None
    amount_source: str
    age_days: int
    comments: int
    competing_pull_requests: int
    score: int
    sponsor: str
    sponsor_evidence: str | None
    warnings: tuple[str, ...]
    updated_at: str
    payment_status: str = "advertised; not received or guaranteed"

    def as_dict(self) -> dict[str, Any]:
        result = dataclasses.asdict(self)
        result["warnings"] = list(self.warnings)
        return result


class GitHubClient:
    """Tiny GitHub REST client with bounded rate-limit handling."""

    def __init__(self, token: str | None = None) -> None:
        self.token = token
        self._repository_cache: dict[str, dict[str, Any]] = {}
        self._pull_request_cache: dict[str, list[dict[str, Any]]] = {}

    def get(self, route: str, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        query = "?" + urllib.parse.urlencode(params) if params else ""
        request = urllib.request.Request(
            API_ROOT + route + query,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "MoneyMaker-Bounty-Radar/0.1",
                **({"Authorization": f"Bearer {self.token}"} if self.token else {}),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            response_body = error.read(2048).decode("utf-8", errors="replace")
            raise GitHubError(f"GitHub returned HTTP {error.code}: {response_body}") from error
        except (OSError, ValueError) as error:
            raise GitHubError(f"Could not read GitHub response for {route}: {error}") from error
        if not isinstance(payload, dict):
            raise GitHubError(f"Expected a JSON object from {route}.")
        return payload

    def search(self, query: str, *, per_page: int = 20) -> list[dict[str, Any]]:
        payload = self.get(
            "/search/issues",
            {"q": query, "sort": "updated", "order": "desc", "per_page": per_page},
        )
        return [item for item in payload.get("items", []) if isinstance(item, dict)]

    def issue(self, repository: str, issue_number: int) -> dict[str, Any]:
        return self.get(f"/repos/{repository}/issues/{issue_number}")

    def repository(self, repository: str) -> dict[str, Any]:
        if repository not in self._repository_cache:
            self._repository_cache[repository] = self.get(f"/repos/{repository}")
        return self._repository_cache[repository]

    def open_pull_requests(self, repository: str) -> list[dict[str, Any]]:
        """Fetch up to 100 open PRs without consuming the search API quota."""
        if repository in self._pull_request_cache:
            return self._pull_request_cache[repository]
        route = f"/repos/{repository}/pulls?state=open&per_page=100"
        request = urllib.request.Request(
            API_ROOT + route,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "MoneyMaker-Bounty-Radar/0.1",
                **({"Authorization": f"Bearer {self.token}"} if self.token else {}),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            response_body = error.read(2048).decode("utf-8", errors="replace")
            raise GitHubError(f"GitHub returned HTTP {error.code}: {response_body}") from error
        except (OSError, ValueError) as error:
            raise GitHubError(f"Could not read open pull requests for {repository}: {error}") from error
        if not isinstance(payload, list):
            raise GitHubError(f"Expected a JSON list of pull requests for {repository}.")
        self._pull_request_cache[repository] = [item for item in payload if isinstance(item, dict)]
        return self._pull_request_cache[repository]


def count_referencing_pull_requests(
    issue: Mapping[str, Any], pull_requests: list[Mapping[str, Any]]
) -> int:
    """Count open PR bodies that directly mention the issue number or URL."""
    number = int(issue["number"])
    url = str(issue.get("html_url") or "")
    number_pattern = re.compile(rf"(?<!\d)#{number}(?!\d)")
    count = 0
    for pull_request in pull_requests:
        body = str(pull_request.get("body") or "")
        if (url and url in body) or number_pattern.search(body):
            count += 1
    return count


def parse_money(text: str) -> list[float]:
    """Return every syntactically valid dollar amount, in appearance order."""
    return [float(match.group(1).replace(",", "")) for match in MONEY_PATTERN.finditer(text)]


def label_names(issue: Mapping[str, Any]) -> list[str]:
    names: list[str] = []
    for label in issue.get("labels") or []:
        if isinstance(label, str):
            names.append(label)
        elif isinstance(label, Mapping) and isinstance(label.get("name"), str):
            names.append(label["name"])
    return names


def advertised_amount(issue: Mapping[str, Any]) -> tuple[float | None, str, list[str]]:
    """Prefer current amount labels over potentially stale issue-body promises."""
    label_amounts: list[float] = []
    for name in label_names(issue):
        stripped = name.strip()
        if re.fullmatch(r"(?:US\s*)?\$\s*[0-9][0-9,]*(?:\.[0-9]{1,2})?", stripped, re.I):
            label_amounts.extend(parse_money(stripped))

    body = str(issue.get("body") or "")
    command_amounts = [float(match.group(1).replace(",", "")) for match in BOUNTY_COMMAND.finditer(body)]
    warnings: list[str] = []
    if label_amounts:
        selected = min(label_amounts)
        if command_amounts and any(value != selected for value in command_amounts):
            warnings.append(
                f"Current label advertises ${selected:g}, but the issue body mentions "
                f"${max(command_amounts):g}; the current label wins."
            )
        return selected, "current GitHub label", warnings
    if command_amounts:
        return command_amounts[-1], "issue-body bounty command; verify platform amount", warnings
    money = parse_money(str(issue.get("title") or "") + "\n" + body)
    return (max(money), "unconfirmed text mention", warnings) if money else (None, "not stated", warnings)


def parse_timestamp(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def assess(
    issue: Mapping[str, Any],
    repository: Mapping[str, Any],
    config: Mapping[str, Any],
    *,
    competing_pull_requests: int = 0,
    now: dt.datetime | None = None,
) -> Opportunity | None:
    """Reject closed, already-paid and prohibited work; score everything else."""
    now = now or dt.datetime.now(dt.timezone.utc)
    if str(issue.get("state", "")).lower() != "open" or issue.get("pull_request"):
        return None
    if repository.get("archived") or repository.get("disabled"):
        return None

    full_name = str(repository.get("full_name") or "")
    if "/" not in full_name:
        return None
    owner = full_name.split("/", 1)[0].lower()
    blocked = {str(item).lower() for item in config.get("blocked_owners", [])}
    if owner in blocked:
        return None

    lowered_labels = [name.lower() for name in label_names(issue)]
    if any("rewarded" in name or "already paid" in name or "wontfix" in name for name in lowered_labels):
        return None

    body = str(issue.get("body") or "")
    if any(pattern.search(body) for pattern, _ in UNACCEPTABLE_PATTERNS):
        return None

    created_at = issue.get("created_at")
    if not isinstance(created_at, str):
        return None
    try:
        age_days = max(0, int((now - parse_timestamp(created_at)).total_seconds() // 86400))
    except ValueError:
        return None
    if age_days > int(config.get("max_issue_age_days", 730)):
        return None

    amount, amount_source, warnings = advertised_amount(issue)
    sponsors = config.get("trusted_sponsors", {})
    sponsor_info = sponsors.get(owner, {}) if isinstance(sponsors, Mapping) else {}
    trusted = isinstance(sponsor_info, Mapping) and bool(sponsor_info)
    comments = int(issue.get("comments") or 0)
    stars = int(repository.get("stargazers_count") or 0)
    forks = int(repository.get("forks_count") or 0)

    score = 40
    if trusted:
        score += 30
    else:
        warnings.append("Sponsor payout history has not been independently verified.")
        score -= 15
    if amount is not None:
        score += min(15, int(amount // 10))
        if amount < 10:
            warnings.append("The advertised amount is below $10.")
            score -= 10
        if amount > 5000 and not trusted:
            warnings.append("An unusually large amount lacks a verified sponsor.")
            score -= 25
    else:
        warnings.append("No explicit dollar amount was found.")
        score -= 20
    if age_days > 365:
        warnings.append("Issue is older than one year; confirm sponsor interest.")
        score -= 20
    elif age_days > 120:
        warnings.append("Issue is older than four months.")
        score -= 10
    if comments >= 20:
        warnings.append(f"Issue already has {comments} comments; check competing claims.")
        score -= min(25, comments // 2)
    if stars < 25 and forks > max(50, stars * 5):
        warnings.append("Repository has an unusually high fork-to-star ratio.")
        score -= 30
    if issue.get("assignees"):
        warnings.append("The issue already has at least one assignee.")
        score -= 15
    if competing_pull_requests:
        warnings.append(
            f"At least {competing_pull_requests} open pull request(s) directly reference this issue."
        )
        score -= min(35, competing_pull_requests * 5)

    evidence = sponsor_info.get("evidence") if trusted else None
    return Opportunity(
        repository=full_name,
        issue_number=int(issue["number"]),
        title=str(issue.get("title") or "Untitled issue"),
        url=str(issue.get("html_url") or f"https://github.com/{full_name}/issues/{issue['number']}"),
        advertised_usd=amount,
        amount_source=amount_source,
        age_days=age_days,
        comments=comments,
        competing_pull_requests=competing_pull_requests,
        score=max(0, min(100, score)),
        sponsor=owner,
        sponsor_evidence=str(evidence) if isinstance(evidence, str) else None,
        warnings=tuple(warnings),
        updated_at=str(issue.get("updated_at") or created_at),
    )


def scan(
    client: GitHubClient,
    config: Mapping[str, Any],
    *,
    now: dt.datetime | None = None,
    pause: Callable[[float], None] = time.sleep,
) -> tuple[list[Opportunity], list[str]]:
    """Search and independently re-fetch issues before treating them as open."""
    candidates: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    queries = config.get("queries", [])
    for index, query in enumerate(queries):
        if index:
            pause(2.1)
        try:
            results = client.search(str(query), per_page=int(config.get("results_per_query", 20)))
        except GitHubError as error:
            errors.append(f"Search failed for {query!r}: {error}")
            continue
        for candidate in results:
            key = str(candidate.get("html_url") or "")
            if key:
                candidates.setdefault(key, candidate)

    opportunities: list[Opportunity] = []
    max_candidates = int(config.get("max_candidates", 30))
    for candidate in list(candidates.values())[:max_candidates]:
        repository_url = str(candidate.get("repository_url") or "")
        if "/repos/" not in repository_url or not isinstance(candidate.get("number"), int):
            continue
        repository_name = repository_url.split("/repos/", 1)[1].strip("/")
        try:
            fresh_issue = client.issue(repository_name, candidate["number"])
            repository = client.repository(repository_name)
            if repository.get("archived") or repository.get("disabled"):
                continue
            pull_requests = client.open_pull_requests(repository_name)
            competition = count_referencing_pull_requests(fresh_issue, pull_requests)
            opportunity = assess(
                fresh_issue,
                repository,
                config,
                competing_pull_requests=competition,
                now=now,
            )
        except (GitHubError, ValueError, TypeError, KeyError) as error:
            errors.append(f"Skipped {repository_name}#{candidate['number']}: {error}")
            continue
        if opportunity:
            minimum_score = int(config.get("minimum_score", 25))
            if opportunity.score >= minimum_score:
                opportunities.append(opportunity)
    opportunities.sort(key=lambda item: (item.score, item.advertised_usd or 0), reverse=True)
    return opportunities, errors


def render_markdown(opportunities: list[Opportunity], errors: list[str], *, generated: str) -> str:
    lines = [
        "# Verified-open bounty radar",
        "",
        f"Generated: {generated}",
        "",
        "> Every amount below is an advertisement, not a payment guarantee. "
        "Each issue was fetched directly from GitHub and confirmed open at scan time.",
        "",
        "| Score | Advertised | Issue | Age | Comments | Open PRs |",
        "| ---: | ---: | --- | ---: | ---: | ---: |",
    ]
    for opportunity in opportunities:
        amount = f"${opportunity.advertised_usd:g}" if opportunity.advertised_usd is not None else "unknown"
        title = opportunity.title.replace("|", r"\|").replace("\n", " ")
        lines.append(
            f"| {opportunity.score}/100 | {amount} | "
            f"[{opportunity.repository}#{opportunity.issue_number}: {title}]({opportunity.url}) | "
            f"{opportunity.age_days}d | {opportunity.comments} | "
            f"{opportunity.competing_pull_requests} |"
        )
    if not opportunities:
        lines.append("| — | — | No qualifying open bounties found. | — | — | — |")

    for opportunity in opportunities:
        if opportunity.warnings:
            lines.extend(["", f"### {opportunity.repository}#{opportunity.issue_number}", ""])
            lines.extend(f"- {warning}" for warning in opportunity.warnings)

    if errors:
        lines.extend(["", "## Scan warnings", ""])
        lines.extend(f"- {error}" for error in errors)

    lines.extend([
        "",
        "## Before starting work",
        "",
        "1. Read the sponsor's current payout and contribution rules.",
        "2. Check open pull requests and recent maintainer comments.",
        "3. Verify the active bounty amount on its official board.",
        "4. Never report a hypothetical vulnerability as a confirmed finding.",
        "",
    ])
    return "\n".join(lines)


def load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("queries"), list):
        raise ValueError("Source configuration must be an object with a queries list.")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discover and sanity-check paid GitHub issues.")
    parser.add_argument("--config", type=Path, default=Path("config/sources.json"))
    parser.add_argument("--output", type=Path, default=Path("reports/bounties.json"))
    parser.add_argument("--markdown", type=Path, default=Path("reports/BOUNTIES.md"))
    parser.add_argument("--fail-on-errors", action="store_true", help="Exit non-zero when any query failed.")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        opportunities, errors = scan(GitHubClient(os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")), config)
    except (OSError, ValueError, GitHubError) as error:
        print(f"Bounty radar failed: {error}", file=sys.stderr)
        return 2

    generated = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    payload = {
        "generated_at": generated,
        "payment_disclaimer": "Advertised rewards are neither guaranteed nor received.",
        "opportunity_count": len(opportunities),
        "errors": errors,
        "opportunities": [opportunity.as_dict() for opportunity in opportunities],
    }
    for output_path, content in (
        (args.output, json.dumps(payload, ensure_ascii=False, indent=2) + "\n"),
        (args.markdown, render_markdown(opportunities, errors, generated=generated)),
    ):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")

    print(f"Confirmed {len(opportunities)} open opportunities; encountered {len(errors)} warnings.")
    return 1 if errors and args.fail_on_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
