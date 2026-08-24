from __future__ import annotations

import datetime as dt
import unittest

from moneymaker.radar import (
    GitHubError,
    advertised_amount,
    assess,
    count_referencing_pull_requests,
    parse_money,
    render_markdown,
    scan,
)


NOW = dt.datetime(2026, 8, 24, 12, 0, tzinfo=dt.timezone.utc)
CONFIG = {
    "queries": ["one", "two"],
    "trusted_sponsors": {"tscircuit": {"evidence": "https://algora.io/tscircuit/bounties"}},
    "blocked_owners": ["claude-builders-bounty"],
    "max_issue_age_days": 730,
    "results_per_query": 10,
    "max_candidates": 10,
}


def make_issue(**overrides: object) -> dict[str, object]:
    issue: dict[str, object] = {
        "number": 42,
        "title": "Fix documented behavior",
        "body": "/bounty $75",
        "state": "open",
        "html_url": "https://github.com/tscircuit/example/issues/42",
        "repository_url": "https://api.github.com/repos/tscircuit/example",
        "created_at": "2026-08-01T12:00:00Z",
        "updated_at": "2026-08-22T12:00:00Z",
        "comments": 0,
        "labels": [{"name": "$75"}, {"name": "💎 Bounty"}],
        "assignees": [],
    }
    issue.update(overrides)
    return issue


def make_repository(**overrides: object) -> dict[str, object]:
    repository: dict[str, object] = {
        "full_name": "tscircuit/example",
        "stargazers_count": 140,
        "forks_count": 35,
        "archived": False,
    }
    repository.update(overrides)
    return repository


class FakeClient:
    def __init__(self, issue: dict[str, object], *, fresh_state: str = "open", fail: bool = False) -> None:
        self.result = issue
        self.fresh_state = fresh_state
        self.fail = fail
        self.issue_requests = 0

    def search(self, query: str, *, per_page: int) -> list[dict[str, object]]:
        if self.fail and query == "two":
            raise GitHubError("simulated rate limit")
        return [self.result]

    def issue(self, repository: str, issue_number: int) -> dict[str, object]:
        self.issue_requests += 1
        return {**self.result, "state": self.fresh_state}

    def repository(self, repository: str) -> dict[str, object]:
        return make_repository()

    def open_pull_requests(self, repository: str) -> list[dict[str, object]]:
        return []


class RadarTests(unittest.TestCase):
    def test_parse_multiple_money_formats(self) -> None:
        self.assertEqual(parse_money("$30, US $1,250.50 and $3"), [30, 1250.50, 3])

    def test_current_label_beats_stale_bounty_command(self) -> None:
        amount, source, warnings = advertised_amount(make_issue(labels=[{"name": "$1"}]))
        self.assertEqual(amount, 1)
        self.assertEqual(source, "current GitHub label")
        self.assertIn("$75", warnings[0])

    def test_bounty_command_is_explicitly_unconfirmed(self) -> None:
        amount, source, warnings = advertised_amount(make_issue(labels=[]))
        self.assertEqual(amount, 75)
        self.assertIn("verify", source)
        self.assertFalse(warnings)

    def test_closed_issue_is_rejected(self) -> None:
        self.assertIsNone(assess(make_issue(state="closed"), make_repository(), CONFIG, now=NOW))

    def test_rewarded_issue_is_rejected(self) -> None:
        self.assertIsNone(assess(make_issue(labels=[{"name": "💰 Rewarded"}]), make_repository(), CONFIG, now=NOW))

    def test_blocked_owner_is_rejected(self) -> None:
        repository = make_repository(full_name="claude-builders-bounty/trap")
        self.assertIsNone(assess(make_issue(), repository, CONFIG, now=NOW))

    def test_no_new_pull_requests_is_rejected(self) -> None:
        issue = make_issue(body="Please do not open new PRs; the fix is already under review.")
        self.assertIsNone(assess(issue, make_repository(), CONFIG, now=NOW))

    def test_ai_prohibition_is_respected(self) -> None:
        issue = make_issue(body="There is a $50 bounty. Do not use AI for this task.")
        self.assertIsNone(assess(issue, make_repository(), CONFIG, now=NOW))

    def test_stale_issue_is_rejected(self) -> None:
        issue = make_issue(created_at="2023-01-01T00:00:00Z")
        self.assertIsNone(assess(issue, make_repository(), CONFIG, now=NOW))

    def test_suspicious_fork_ratio_is_flagged(self) -> None:
        opportunity = assess(make_issue(), make_repository(stargazers_count=10, forks_count=1000), CONFIG, now=NOW)
        self.assertIsNotNone(opportunity)
        self.assertTrue(any("fork-to-star" in warning for warning in opportunity.warnings))

    def test_trusted_sponsor_scores_above_unknown_sponsor(self) -> None:
        trusted = assess(make_issue(), make_repository(), CONFIG, now=NOW)
        unknown = assess(make_issue(), make_repository(full_name="unknown/example"), CONFIG, now=NOW)
        self.assertGreater(trusted.score, unknown.score)

    def test_directly_referencing_pull_requests_are_counted(self) -> None:
        issue = make_issue()
        pull_requests = [
            {"body": "Fixes #42"},
            {"body": "Alternative for https://github.com/tscircuit/example/issues/42"},
            {"body": "Mentions #420, which is unrelated"},
        ]
        self.assertEqual(count_referencing_pull_requests(issue, pull_requests), 2)

    def test_competing_pull_requests_reduce_score(self) -> None:
        clear = assess(make_issue(), make_repository(), CONFIG, now=NOW)
        crowded = assess(
            make_issue(), make_repository(), CONFIG, competing_pull_requests=6, now=NOW
        )
        self.assertLess(crowded.score, clear.score)
        self.assertEqual(crowded.competing_pull_requests, 6)

    def test_scan_deduplicates_and_refetches_original_issue(self) -> None:
        client = FakeClient(make_issue())
        opportunities, errors = scan(client, CONFIG, now=NOW, pause=lambda _: None)
        self.assertEqual(len(opportunities), 1)
        self.assertEqual(client.issue_requests, 1)
        self.assertFalse(errors)

    def test_scan_rejects_issue_closed_after_search(self) -> None:
        opportunities, _ = scan(FakeClient(make_issue(), fresh_state="closed"), CONFIG, now=NOW, pause=lambda _: None)
        self.assertFalse(opportunities)

    def test_scan_keeps_partial_results_after_search_error(self) -> None:
        opportunities, errors = scan(FakeClient(make_issue(), fail=True), CONFIG, now=NOW, pause=lambda _: None)
        self.assertEqual(len(opportunities), 1)
        self.assertEqual(len(errors), 1)

    def test_markdown_never_represents_advertisement_as_guarantee(self) -> None:
        opportunity = assess(make_issue(), make_repository(), CONFIG, now=NOW)
        markdown = render_markdown([opportunity], [], generated="2026-08-24")
        self.assertIn("not a payment guarantee", markdown)
        self.assertIn("$75", markdown)


if __name__ == "__main__":
    unittest.main()
