from __future__ import annotations

import json
import unittest

from hackathons.agents_for_humans.opportunity_guardian import (
    calculate_expected_value,
    expected_value,
    rank_verified_opportunities,
)


class ExpectedValueTests(unittest.TestCase):
    def test_profitable_opportunity(self) -> None:
        result = expected_value(200, 0.5, 2, 20)
        self.assertEqual(result.expected_payout, 100)
        self.assertEqual(result.time_cost, 40)
        self.assertEqual(result.expected_profit, 60)
        self.assertEqual(result.break_even_probability, 0.2)

    def test_unprofitable_opportunity(self) -> None:
        result = expected_value(50, 0.1, 5, 20)
        self.assertEqual(result.expected_profit, -95)

    def test_zero_reward_has_no_break_even_probability(self) -> None:
        self.assertIsNone(expected_value(0, 0, 1, 20).break_even_probability)

    def test_probability_out_of_range_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            expected_value(100, 1.1, 1, 20)

    def test_negative_time_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            expected_value(100, 0.5, -1, 20)

    def test_strands_tool_returns_json(self) -> None:
        result = json.loads(calculate_expected_value(100, 0.25, 1, 20))
        self.assertEqual(result["expected_profit"], 5)

    def test_ranker_prefers_expected_profit_then_evidence(self) -> None:
        candidates = [
            {"name": "crowded", "reward": 100, "probability": 0.1, "hours": 1, "evidence_score": 90},
            {"name": "clear", "reward": 100, "probability": 0.8, "hours": 1, "evidence_score": 70},
        ]
        ranked = json.loads(rank_verified_opportunities(json.dumps(candidates)))
        self.assertEqual(ranked[0]["name"], "clear")

    def test_ranker_rejects_non_list_input(self) -> None:
        with self.assertRaises(ValueError):
            rank_verified_opportunities("{}")


if __name__ == "__main__":
    unittest.main()

