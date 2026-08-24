"""Command-line entry point for live and fixture-based bounty checks."""

from __future__ import annotations

import argparse
import json
import sys

from .github import GitHubClient, GitHubError, parse_issue_url
from .models import IssueSnapshot, Listing, RepositorySnapshot
from .scoring import assess


def _print_assessment(value, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value.to_dict(), indent=2, ensure_ascii=False))
        return
    print(f"{value.verdict}  {value.score}/100  {value.issue.title}")
    print(f"{value.listing.currency} {value.listing.amount:.2f} · {value.listing.platform}")
    print(value.issue.url)
    for item in value.findings:
        print(f"  [{item.severity.upper()}] {item.code}: {item.message}")
        print(f"    Evidence: {item.evidence}")


def _check(args: argparse.Namespace) -> int:
    listing = Listing(
        issue_url=args.url,
        amount=args.amount,
        currency=args.currency,
        platform=args.platform,
        listed_status=args.listed_status,
        claims=args.claims,
        escrow_status=args.escrow_status,
        human_only=args.human_only,
    )
    ref = parse_issue_url(args.url)
    client = GitHubClient()
    result = assess(listing, client.issue(ref), client.repository(ref))
    _print_assessment(result, args.json)
    return 2 if result.verdict == "REJECT" else 0


def _batch(args: argparse.Namespace) -> int:
    with open(args.path, encoding="utf-8") as handle:
        fixtures = json.load(handle)
    results = []
    for fixture in fixtures:
        results.append(
            assess(
                Listing(**fixture["listing"]),
                IssueSnapshot(**fixture["issue"]),
                RepositorySnapshot(**fixture["repository"]),
                maintainer_text=fixture.get("maintainer_text", ""),
            )
        )
    if args.json:
        print(json.dumps([item.to_dict() for item in results], indent=2))
    else:
        for item in results:
            _print_assessment(item, False)
            print()
    return 2 if any(item.verdict == "REJECT" for item in results) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bountyproof",
        description="Verify a GitHub bounty against upstream evidence.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="Check one public GitHub issue.")
    check.add_argument("url", help="Public GitHub issue URL.")
    check.add_argument("--amount", type=float, default=0.0)
    check.add_argument("--currency", default="USD")
    check.add_argument("--platform", default="unknown")
    check.add_argument("--listed-status", default="open")
    check.add_argument("--claims", type=int, default=0)
    check.add_argument(
        "--escrow-status",
        choices=("unknown", "not_escrowed", "verified_escrow"),
        default="unknown",
    )
    check.add_argument("--human-only", action="store_true")
    check.add_argument("--json", action="store_true")
    batch = commands.add_parser("batch", help="Assess an offline fixture manifest.")
    batch.add_argument("path")
    batch.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _check(args) if args.command == "check" else _batch(args)
    except (GitHubError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
