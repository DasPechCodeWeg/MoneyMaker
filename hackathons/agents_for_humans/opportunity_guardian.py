"""Strands-powered decision agent for paid open-source opportunities."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any

try:
    from strands import Agent, tool
except ImportError:  # Core risk rules and tests stay usable without optional SDK.
    Agent = None  # type: ignore[assignment]

    def tool(function):  # type: ignore[no-untyped-def]
        return function

from bountyproof.github import GitHubClient, parse_issue_url
from bountyproof.models import Listing
from bountyproof.scoring import assess


SYSTEM_PROMPT = """You are Opportunity Guardian, an evidence-first agent for people
who want to earn from open-source bounties without wasting unpaid hours.

Always call tools before recommending work. Separate advertised money from verified
escrow and from money actually received. Reject closed issues, archived repositories,
explicit AI restrictions, and maintainer requests for no new pull requests. Penalize
crowded and stale work. Calculate expected value using the user's hourly floor.

End with one of these decisions: PURSUE, VERIFY FIRST, or SKIP. Cite the exact evidence
codes and explain the next reversible action. Never claim a payment is guaranteed.
"""


@dataclass(frozen=True, slots=True)
class ExpectedValue:
    advertised_reward: float
    probability: float
    estimated_hours: float
    hourly_floor: float
    expected_payout: float
    time_cost: float
    expected_profit: float
    break_even_probability: float | None


def expected_value(
    advertised_reward: float,
    probability: float,
    estimated_hours: float,
    hourly_floor: float,
) -> ExpectedValue:
    """Calculate conservative time-adjusted value for a possible bounty."""
    values = (advertised_reward, probability, estimated_hours, hourly_floor)
    if any(not isinstance(value, (int, float)) for value in values):
        raise TypeError("Expected-value inputs must be numbers.")
    if advertised_reward < 0 or estimated_hours < 0 or hourly_floor < 0:
        raise ValueError("Money and time inputs cannot be negative.")
    if not 0 <= probability <= 1:
        raise ValueError("Probability must be between 0 and 1.")
    time_cost = estimated_hours * hourly_floor
    expected_payout = advertised_reward * probability
    break_even = time_cost / advertised_reward if advertised_reward else None
    return ExpectedValue(
        advertised_reward=round(advertised_reward, 2),
        probability=round(probability, 4),
        estimated_hours=round(estimated_hours, 2),
        hourly_floor=round(hourly_floor, 2),
        expected_payout=round(expected_payout, 2),
        time_cost=round(time_cost, 2),
        expected_profit=round(expected_payout - time_cost, 2),
        break_even_probability=round(break_even, 4) if break_even is not None else None,
    )


@tool
def calculate_expected_value(
    advertised_reward: float,
    probability: float,
    estimated_hours: float,
    hourly_floor: float = 20.0,
) -> str:
    """Calculate expected payout, time cost, profit, and break-even odds for a bounty."""
    return json.dumps(
        asdict(expected_value(advertised_reward, probability, estimated_hours, hourly_floor)),
        ensure_ascii=False,
    )


@tool
def verify_github_bounty(
    issue_url: str,
    advertised_reward: float,
    platform: str = "unknown",
    claims: int = 0,
    escrow_status: str = "unknown",
    human_only: bool = False,
) -> str:
    """Fetch a public GitHub issue and repository, then return an evidence-backed verdict."""
    listing = Listing(
        issue_url=issue_url,
        amount=advertised_reward,
        platform=platform,
        claims=claims,
        escrow_status=escrow_status,  # type: ignore[arg-type]
        human_only=human_only,
    )
    reference = parse_issue_url(issue_url)
    client = GitHubClient(token=os.getenv("GITHUB_TOKEN"))
    result = assess(listing, client.issue(reference), client.repository(reference))
    return json.dumps(result.to_dict(), ensure_ascii=False)


@tool
def rank_verified_opportunities(candidates_json: str) -> str:
    """Rank already-verified opportunities by expected profit, then evidence score."""
    payload = json.loads(candidates_json)
    if not isinstance(payload, list):
        raise ValueError("Candidates must be a JSON list.")
    ranked: list[dict[str, Any]] = []
    for candidate in payload:
        if not isinstance(candidate, dict):
            raise ValueError("Every candidate must be a JSON object.")
        score = float(candidate.get("evidence_score", 0))
        value = expected_value(
            float(candidate.get("reward", 0)),
            float(candidate.get("probability", 0)),
            float(candidate.get("hours", 0)),
            float(candidate.get("hourly_floor", 20)),
        )
        ranked.append({**candidate, **asdict(value), "evidence_score": score})
    ranked.sort(key=lambda item: (item["expected_profit"], item["evidence_score"]), reverse=True)
    return json.dumps(ranked, ensure_ascii=False)


def build_agent(model: Any | None = None):
    """Build the required Strands agent; model=None uses the SDK's Bedrock default."""
    if Agent is None:
        raise RuntimeError(
            "Install the hackathon dependencies first: "
            "pip install -r hackathons/agents_for_humans/requirements.txt"
        )
    arguments: dict[str, Any] = {
        "system_prompt": SYSTEM_PROMPT,
        "tools": [verify_github_bounty, calculate_expected_value, rank_verified_opportunities],
    }
    if model is not None:
        arguments["model"] = model
    return Agent(**arguments)

