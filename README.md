# MoneyMaker

MoneyMaker is an evidence-first bounty radar and an open lab for building products that can earn money.

The first lesson was expensive in a useful way: a green bounty badge does not mean that an issue is open, unclaimed, payable, or even possible to change. The radar therefore re-fetches every candidate from GitHub and rejects archived repositories, closed issues, already rewarded work, prohibited AI use, suspicious repositories, and stale amount labels.

## What it does

- Searches selected GitHub bounty programs twice a day.
- Confirms the original issue is still open.
- Prefers current dollar labels over stale amounts in issue text.
- Scores sponsor evidence, issue age, competition, assignment, and repository health.
- Publishes machine-readable JSON and a human-readable report.
- Runs without third-party Python packages.
- Tests every risk rule before each scheduled scan.

No advertised reward is represented as earned or guaranteed. Payment still depends on the sponsor, acceptance, platform rules, and payout setup.

## Run locally

```bash
python -m unittest discover -s tests -v
GITHUB_TOKEN=github_token_here python -m moneymaker.radar
```

Outputs are written to `reports/bounties.json` and `reports/BOUNTIES.md`.

Check one advertised issue before spending time on it:

```bash
python -m bountyproof check https://github.com/OWNER/REPO/issues/NUMBER \
  --amount 100 --platform algora --claims 3 --escrow-status unknown
```

This returns `PASS`, `CAUTION`, or `REJECT` with the evidence behind every rule.

## Current strategy

The repository supports three routes:

1. Find a low-competition, still-open paid issue and prepare a tested contribution.
2. Turn the due-diligence engine into a useful hosted product for other bounty hunters.
3. Reuse the product in legitimate hackathons that explicitly allow AI-assisted development.

The research log records rejected opportunities as carefully as accepted ones. Avoiding a fake $100 task can be worth more than completing it.

## Ethical boundary

MoneyMaker does not mass-submit generated pull requests, make speculative vulnerability claims, bypass platform controls, or ignore a maintainer's contribution policy. Security work is limited to programs that explicitly authorize it and must follow their scope and disclosure process.

## License

MIT
