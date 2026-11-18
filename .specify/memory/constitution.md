# Rescue Crew Constitution

Rescue Crew is a supervised agent team for Airbnb that resolves the 60 stranded-guest tickets from the
Lisbon check-in failure of 16 November 2026. Every guest ends with a bed, a refund or a live safety
agent before midnight on 16 November 2026.

## Core Principles

### I. The AirCover Policy Is the Only Source of Rules

- All eligibility, comparable-home, refund and uplift rules MUST come from
  [`docs/policy/aircover-lisbon-rules.md`](../../docs/policy/aircover-lisbon-rules.md) (the "Policy").
- Agents and code MUST NOT invent thresholds, exceptions, goodwill payments or new remedies. When the
  Policy is silent, the case goes to a human supervisor rather than being decided by guesswork.
- Every money or booking action MUST record the Policy clause it relies on.

Rationale: AirCover money and guest placement are binding commitments. Rules that are not in the
Policy have no authority.

### II. Safety First: Human Takeover (NON-NEGOTIABLE)

- A ticket is a **safety** ticket when `guest_message` describes any one of the Policy's five
  conditions: `injury_or_medical_need`, `threat_or_violence`, `nowhere_safe_to_wait`,
  `unaccompanied_minor`, `stated_fear_of_person`.
- This applies whatever `guest_requested` says, including a guest who asks only for money. The guest
  does not need to say "safety" and the ticket does not need an emergency label.
- On a safety ticket the only tool call allowed is `handoff_to_safety_agent`. `issue_refund` and
  `hold_booking` MUST NOT be called before the hand-off. After the hand-off, the live safety agent
  decides any refund or booking.
- Safety screening MUST run first on every ticket, before any other tool call.
- Anger, frustration, urgency or figures of speech ("I am dying out here", "worst day of our lives",
  "before we all lose it") do not, on their own, make a ticket a safety case. The test is whether one
  of the five conditions is actually described.

Rationale: a refund or a booking does not help a guest who is hurt, threatened, alone as a minor, or
with nowhere safe to wait. Treating every angry ticket as a safety case would overload the safety
team and delay everyone else.

### III. Least-Privilege Agents

- Each agent MUST be able to call only the tools its role needs, from the six available tools:
  `lookup_reservation`, `search_open_listings`, `hold_booking`, `issue_refund`, `message_host`,
  `handoff_to_safety_agent`.
- The tool allowlist MUST be enforced by the system that executes tool calls, not only by
  instructions given to the agent. A call outside an agent's allowlist MUST be rejected and logged.
- Adding a tool to an agent's allowlist is a constitution-level change (see Governance).

Rationale: a mistaken or manipulated agent cannot move money or hold homes if it was never given
the tool to do so.

### IV. Money and Booking Guardrails

- A refund MUST NOT exceed the ticket's `total_paid`, including goodwill or "inconvenience"
  additions. `total_paid` is used as-is, never recalculated from nights × `nightly_price`.
- One remedy per stay: a guest is either rebooked or refunded for the same nights, never both.
- A rebooked home MUST pass every comparable-home test in the Policy, including the price ceiling of
  1.20 × the original `nightly_price`. On 16 November 2026 no home above that ceiling is offered,
  even if uplift budget remains.
- Uplift spend MUST be tracked against the EUR 9,000 incident budget.

Rationale: these are the Policy's hard limits on AirCover money.

### V. Supervised, Auditable and Test-First

- A human supervisor MUST be able to see, for every ticket, its classification, each tool call with
  its inputs and result, the agent that made it, and the Policy clause applied.
- Behaviour MUST be covered by automated tests before it is relied on. The 60 incident tickets and
  their `expected_outcome` values are the acceptance suite: classification MUST match on all 60.
- Tests run with `uv run pytest`; code passes `uv run ruff check .` before it is merged.

Rationale: an incident response that cannot be audited cannot be trusted, and the tickets give a
fixed, known answer to test against.

## Additional Constraints

- Language and tooling: Python 3.12 or later, managed with uv; tests with pytest; linting with ruff.
- Tool calls against reservations, listings, refunds, host messages and safety hand-off go through
  the six named tools only; agents do not reach those systems any other way.
- Guest personal data (names, messages) is used only to resolve the ticket. It is not copied into
  logs, prompts or files beyond what resolving and auditing the ticket needs.
- Rebookings name a `listing_id` from the open listings export (LST-100001 to LST-100450). Original
  listings (LST-200001 to LST-200060) are never offered.

## Development Workflow

- Work follows the Spec Kit flow: `/speckit-specify` → `/speckit-clarify` (optional) →
  `/speckit-plan` → `/speckit-tasks` → `/speckit-implement`.
- Every plan MUST include a Constitution Check confirming Principles I–V, with any exception
  written down and justified.
- Changes that touch safety screening, tool allowlists or money rules need a reviewer other than the
  author.

## Governance

- This constitution overrides other project practices. Where the constitution and the Policy
  disagree, the Policy wins and the constitution is amended to match.
- Amendments are made by pull request that states the change, the reason and the version bump.
  Versioning follows semantic versioning: MAJOR for removing or redefining a principle, MINOR for a new
  principle or section or materially expanded guidance, PATCH for wording fixes.
- Every spec, plan and code review checks compliance with this constitution.

**Version**: 1.0.0 | **Ratified**: 2026-11-18 | **Last Amended**: 2026-11-18
