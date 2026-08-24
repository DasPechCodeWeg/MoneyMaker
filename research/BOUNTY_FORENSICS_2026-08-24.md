# Bounty forensics — 24 August 2026

No amount in this document has been earned or guaranteed. The purpose is to prevent wasted work and preserve primary evidence.

## Result

The visible GitHub issue-bounty market contained no healthy, low-competition target in this scan. Every initially promising issue failed at least one primary check.

| Candidate | Advertised | Primary finding | Decision |
| --- | ---: | --- | --- |
| `seveibar/pgstrap#2` | $30 | At least 15 competing pull requests; PGlite already exists on `main` | Reject |
| `tscircuit/pcb-viewer#163` | $3 | 39 claims; requested behavior already implemented | Reject |
| `tscircuit/autorouting#92` | $50 | Repository archived and read-only since 15 August 2025 | Reject |
| `tscircuit/jlcsearch#92` | $1 current | Body still says $75; 100+ claims | Reject |
| `typeorm/typeorm#3357` | $590 | Maintainer explicitly asks for no new PRs | Reject |
| ProjectDiscovery open board | $100 each | Listed issues are closed on GitHub | Reject until a fresh labeled issue appears |

## Platform evidence

### Algora

The tscircuit board shows 707 completed bounties and named earners, so the sponsor has a real payment history. Its remaining open board is nevertheless heavily stale and crowded. The issue and repository on GitHub must be treated as authoritative.

- Completed board: https://algora.io/tscircuit/bounties?status=completed
- Open board: https://algora.io/tscircuit/bounties?status=open

### Opire

Opire's own FAQ says rewards are not escrowed. A creator can post a bounty without entering a payment method and chooses later whether to initiate payment. Several listings marked open point to closed GitHub issues. A listing is a promise, not proof of funds.

- Official FAQ: https://opire.dev/home

### ProjectDiscovery

ProjectDiscovery has a credible official program: only explicitly labeled work qualifies, one active claim is allowed, contributors get two weeks, and the first complete high-quality merge wins. At scan time, direct GitHub search found no qualifying open issue. Security findings must be disclosed privately.

- Rules: https://github.com/projectdiscovery/oss-bounty-program
- Announcement: https://projectdiscovery.io/blog/announcing-the-projectdiscovery-oss-bounty-program

### Known trap

`claude-builders-bounty/claude-builders-bounty` had roughly 2,800 pull requests but only 21 issues, two repository commits, and no independently verified funding evidence. It is excluded from the scanner.

## Better funded routes found

- Firelight Immunefi audit competition: $20,000 USDC in a public vault, about 3,044 lines in scope, public test repository, deadline 25 August 2026 at 10:00 UTC. A runnable proof of concept is mandatory. https://immunefi.com/audit-competition/audit-comp-firelight-1/information/
- ENS Immunefi audit competition: $70,000 vault, much larger scope, deadline 14 September 2026. KYC applies. https://immunefi.com/audit-competition/audit-competition-ens/information/
- RevenueCat Shipaton 2026: $740,000 cash in the binding rules; AI-assisted development is allowed. The student track accepts an open-source repository and short video without an app-store release, subject to academic-email eligibility. https://revenuecat-shipaton-2026.devpost.com/rules
- AssemblyAI Voice Agent Hackathon: $10,000 listed prize pool, deadline 30 September 2026. https://lablab.ai/ai-hackathons/assemblyai-voice-agent-hackathon/live

These alternatives still require their own eligibility, account, submission, and acceptance steps. They are not income until awarded and paid.

