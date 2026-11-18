# Feature Specification: Lisbon Rescue Crew

**Feature Branch**: `001-lisbon-rescue-crew`

**Created**: 2026-11-18

**Status**: Draft

**Input**: User description: "Rescue Crew is a supervised agent team for Airbnb that handles the 60 stranded guest tickets from the Lisbon check-in failure on 16 Nov 2026. Ticket types: rebooking, refund and safety, and anger or figures of speech alone don't make a ticket a safety case. Agents: triage, rebooking, refund and host messaging, each using only the tools it needs from the six (lookup_reservation, search_open_listings, hold_booking, issue_refund, message_host, handoff_to_safety_agent). Human takeover: injury, medical need and threat, even when the guest only asks for money. On those tickets the only tool allowed is handoff_to_safety_agent, never issue_refund or hold_booking. The comparable-home and refund-cap clauses come from the AirCover rules file."

**Policy source**: [`docs/policy/aircover-lisbon-rules.md`](../../docs/policy/aircover-lisbon-rules.md) (the "Policy"). Every rule below that names a threshold, test or limit restates the Policy; if they ever differ, the Policy wins.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Guests in danger reach a live safety agent first (Priority: P1)

A guest whose message describes an injury or medical need, a threat or violence, nowhere safe to
wait, an unaccompanied minor, or fear of a person is handed to a live Trust and Safety agent. No
refund is issued and no home is held first, even when the guest asks only for money.

**Why this priority**: These are the guests who can be hurt by delay or by the wrong remedy. Getting
this wrong is the most serious failure the system can have.

**Independent Test**: Run triage on the 60 incident tickets and check that exactly the six tickets
whose `expected_outcome` is `safety` are handed off, and that on those six no tool other than
`handoff_to_safety_agent` was called.

**Acceptance Scenarios**:

1. **Given** LIS-TKT-0007, where the guest asks for a full refund but says their knee is bleeding badly and they can hardly stand, **When** the ticket is processed, **Then** it is classified `safety` (`injury_or_medical_need`), `handoff_to_safety_agent` is called, and `issue_refund` is never called.
2. **Given** LIS-TKT-0015, a 16-year-old travelling alone with a phone on 9% whose `guest_requested` is `callback`, **When** the ticket is processed, **Then** it is classified `safety` (`unaccompanied_minor`, `nowhere_safe_to_wait`) and handed off.
3. **Given** LIS-TKT-0034, a guest asking only for a refund who says a man followed them from the metro and is watching the door, **When** the ticket is processed, **Then** it is classified `safety` (`stated_fear_of_person`, `threat_or_violence`) and `issue_refund` is never called.
4. **Given** LIS-TKT-0022 ("I am dying out here ... before we all lose it"), **When** the ticket is processed, **Then** it is **not** classified `safety`, because the words are a figure of speech and none of the five conditions is described; it goes to rebooking.

---

### User Story 2 - Qualifying guests are rebooked into a comparable home (Priority: P1)

A locked-out guest who wants to stay is offered an open Lisbon listing that passes every
comparable-home test in the Policy, for the whole remaining stay, and the home is held for them.

**Why this priority**: 34 of the 60 tickets need a bed tonight; this is the largest group and the
incident commitment is a bed, a refund or a safety agent before midnight.

**Independent Test**: For each non-safety ticket that does not ask for a refund, run the rebooking
flow against the open listings export and check that any held listing passes all five
comparable-home tests and covers `check_in_date` to `check_out_date`.

**Acceptance Scenarios**:

1. **Given** a qualifying ticket with original `nightly_price` EUR 110.00, **When** listings priced EUR 132.00 and EUR 132.01 are both otherwise comparable, **Then** the EUR 132.00 listing may be offered and the EUR 132.01 listing is never offered.
2. **Given** LIS-TKT-0002 (4 guests, 2 bedrooms, 16 to 21 Nov), **When** a listing is held, **Then** it has `max_guests` ≥ 4, `bedrooms` ≥ 2, `available_from` ≤ 2026-11-16, `available_to` ≥ 2026-11-21, and `status` = `available` at the moment of the hold.
3. **Given** two listings pass every test and one is in the guest's `neighborhood` or a neighbouring one, **When** choosing which to offer, **Then** the nearby one is preferred.
4. **Given** a guest turns down the first home offered, **When** they ask again, **Then** they are offered another comparable home or a full refund; declining does not end their rights.
5. **Given** a listing that was `available` at search time is `on_hold` or `booked` by the time of the hold, **When** the hold is attempted, **Then** the hold fails and the next comparable listing is tried.
6. **Given** LIS-TKT-0017, LIS-TKT-0039, LIS-TKT-0049 or LIS-TKT-0059, whose `guest_requested` is `callback`, or LIS-TKT-0029 or LIS-TKT-0060, whose `guest_requested` is `other`, **When** triaged, **Then** they are classified `rebooking` (the guest still wants somewhere to stay), and the callback or question is flagged for a human supervisor.
7. **Given** the open listings export as of 16 November 2026, **When** each of the 34 rebooking tickets is searched on its own, **Then** every ticket has at least one listing that passes all five comparable-home tests, so none of them falls back to a refund for lack of a comparable home. The scarcest is LIS-TKT-0013 (Parque das Nacoes, 3 bedrooms, 6 guests, 16 to 23 Nov), with 7 passing listings.
8. **Given** the same export, **When** all 34 rebooking tickets are placed together, **Then** each gets a different passing listing, so no listing is held for two guests. This matters most for the tickets needing 3 or more bedrooms (LIS-TKT-0013, 0020, 0027, 0033, 0038, 0045, 0047, 0058), which draw on a small shared pool.
9. **Given** LIS-TKT-0013, LIS-TKT-0033, LIS-TKT-0043 or LIS-TKT-0058, **When** searched, **Then** no passing listing is in the guest's own `neighborhood`, so the guest is offered a passing home in a neighbouring area rather than refused; neighbourhood is a preference, not a test.
10. **Given** a ticket's search returns listings with an empty `rating`, **When** the five tests are applied, **Then** those listings are judged on the five tests alone; `rating`, `instant_book`, `title` and `host_id` are never pass/fail tests.

---

### User Story 3 - Guests who want their money back get a refund within the cap (Priority: P2)

A guest who asks for a refund, declines rebooking, or for whom no comparable home exists receives a
refund that never exceeds `total_paid`, and that refund closes the stay.

**Why this priority**: 20 tickets ask only for a refund; they are lower risk than safety and
rebooking cases but still owe a resolution before midnight.

**Independent Test**: Process the 20 tickets whose `expected_outcome` is `refund` and check that
each receives one `issue_refund` call for at most `total_paid`, and no `hold_booking` call.

**Acceptance Scenarios**:

1. **Given** LIS-TKT-0028, booked with a promo code, where `total_paid` is EUR 432.00 but 4 nights × EUR 120.00 is EUR 480.00, **When** a full refund is issued, **Then** it is EUR 432.00.
2. **Given** a guest who asks for a refund "plus something for the trouble", **When** the refund is calculated, **Then** it is no more than `total_paid`.
3. **Given** a qualifying rebooking ticket where no open listing passes the comparable-home tests, **When** the search is exhausted, **Then** the guest is owed a full refund of `total_paid`.
4. **Given** a guest who has already been rebooked for their nights, **When** a refund is requested for the same nights, **Then** no refund is issued for those nights (one remedy per stay) and the request goes to a human supervisor.

---

### User Story 4 - Original hosts are told what happened (Priority: P3)

After a ticket is resolved, or when a host is unreachable, the host messaging agent sends the
original host a factual message about the reservation's status.

**Why this priority**: Useful for the record and for follow-up, but no guest is left without a bed,
refund or safety agent if it is late.

**Independent Test**: For resolved non-safety tickets, check that one message was sent to the
ticket's `host_id` and that it contains no guest contact details.

**Acceptance Scenarios**:

1. **Given** LIS-TKT-0038, where the host has never replied and the lockbox is empty, **When** the guest has been rebooked, **Then** the host is messaged that the guest could not get in and has been moved.
2. **Given** a safety ticket, **When** it is handed off, **Then** the host messaging agent sends nothing; any contact with the host is left to the live safety agent.

---

### Edge Cases

- **Safety and refund in the same message**: safety wins (LIS-TKT-0007, LIS-TKT-0034). The refund request is passed to the safety agent, not acted on.
- **Safety described in a non-refund, non-rebooking request** (`guest_requested` = `other` or `callback`): still safety (LIS-TKT-0015, LIS-TKT-0046).
- **Strong emotion without a safety condition** (LIS-TKT-0005, LIS-TKT-0022, LIS-TKT-0041): not safety; normal rebooking.
- **Host did not cancel but guest cannot get in** (LIS-TKT-0003, LIS-TKT-0019, LIS-TKT-0038, LIS-TKT-0051, where `host_cancelled_at` is empty): qualifies through "no working access" or "host unreachable".
- **Host replied before the guest arrived but then cancelled** (e.g. LIS-TKT-0009): qualifies because the cancellation is within 30 days of check-in.
- **Original listing IDs** (LST-200001 to LST-200060) are never offered as a rebooking.
- **Every comparable listing is above the 120% ceiling**: no booking is offered on 16 November 2026 (spend above the ceiling needs Laura Schmidt's sign-off, which is not available that day); the guest is owed a full refund.
- **Uplift budget**: at the 120% ceiling the largest possible total uplift across the 34 rebooking tickets is EUR 6,327.30, below the EUR 9,000 budget, so the budget cannot run out while the ceiling holds. The system still tracks spend.
- **A safety condition appears after triage** (for example in a later message to the rebooking agent): the agent stops, takes no further booking or money action, and returns the ticket to triage for hand-off.
- **A tool fails or times out** on a non-safety ticket: retry once, then escalate to the human supervisor; do not leave the ticket without an owner.

## Requirements *(mandatory)*

### Functional Requirements

#### Ticket classification

- **FR-001**: The system MUST classify every ticket as exactly one of `rebooking`, `refund` or `safety`.
- **FR-002**: The system MUST screen every ticket for safety before any other tool call, reading the five conditions in the Policy (`injury_or_medical_need`, `threat_or_violence`, `nowhere_safe_to_wait`, `unaccompanied_minor`, `stated_fear_of_person`) from what the guest describes in `guest_message`.
- **FR-003**: A ticket MUST be classified `safety` when any one of the five conditions is described, regardless of `guest_requested`, and without needing the word "safety" or an emergency label.
- **FR-004**: Anger, urgency, complaints or figures of speech MUST NOT on their own cause a `safety` classification.
- **FR-005**: A non-safety ticket MUST be classified `refund` when `guest_requested` is `refund`, and `rebooking` otherwise (`rebooking`, `callback`, `other`).
- **FR-006**: A `callback` or `other` request MUST be flagged for a human supervisor so the call or question is answered, without delaying the rebooking.

#### Agents and tools

- **FR-007**: The system MUST consist of a supervisor that routes tickets and four agents, each limited to this tool allowlist:

  | Agent | Allowed tools | Job |
  |---|---|---|
  | Supervisor | none | Routes tickets between agents; escalates to humans |
  | Triage | `lookup_reservation`, `handoff_to_safety_agent` | Safety screen, then classification |
  | Rebooking | `lookup_reservation`, `search_open_listings`, `hold_booking` | Finds and holds a comparable home |
  | Refund | `lookup_reservation`, `issue_refund` | Issues refunds within the cap |
  | Host messaging | `lookup_reservation`, `message_host` | Tells the original host the outcome |

- **FR-008**: Any tool call outside the calling agent's allowlist MUST be rejected by the system and logged.
- **FR-009**: Only the triage agent may call `handoff_to_safety_agent`. Any other agent that meets a safety condition MUST stop and return the ticket to triage.

#### Safety tickets

- **FR-010**: On a `safety` ticket the only tool call allowed is `handoff_to_safety_agent`. `issue_refund`, `hold_booking`, `search_open_listings`, `message_host` and `lookup_reservation` MUST NOT be called on it by Rescue Crew.
- **FR-011**: The hand-off MUST pass the safety condition(s) found and the guest's own words to the live safety agent.
- **FR-012**: After hand-off the ticket MUST be closed for Rescue Crew; the live safety agent decides any refund or booking.

#### Rebooking eligibility

- **FR-013**: A guest MUST be treated as qualifying for rebooking support if any one of these is true: no working access at check-in (from `guest_message`); host unreachable (`host_last_reply_at` empty or not after the guest's contact, or as described in `guest_message`); host cancelled within 30 days before `check_in_date` (`host_cancelled_at`).
- **FR-014**: Rebooking MUST cover the whole remaining stay from `check_in_date` to `check_out_date`, not only the first night.

#### Comparable home

- **FR-015**: An open listing MUST be offered only if it passes all five Policy tests:
  1. Dates covered: `available_from` ≤ `check_in_date` and `available_to` ≥ `check_out_date`, with no gap.
  2. Fits the party: `max_guests` ≥ `party_size`.
  3. Enough bedrooms: listing `bedrooms` ≥ ticket `bedrooms`.
  4. Can be held now: `status` = `available` at the time of the hold (`on_hold` and `booked` fail).
  5. Price ceiling: listing `nightly_price` ≤ 1.20 × ticket `nightly_price`.
- **FR-016**: Among listings that pass, the same or a neighbouring Lisbon `neighborhood` MUST be preferred; neighbourhood is never a pass/fail test.
- **FR-017**: A rebooking MUST name a `listing_id` from LST-100001 to LST-100450.
- **FR-018**: A guest who declines an offered home MUST still be offered another comparable home, if one exists, or a full refund.
- **FR-019**: On 16 November 2026 the system MUST NOT offer any home priced above 1.20 × the original `nightly_price`, even if uplift budget remains.

#### Refunds

- **FR-020**: A refund MUST NOT exceed the ticket's `total_paid`, including any goodwill or inconvenience addition.
- **FR-021**: A full refund of `total_paid` MUST be issued when no open listing passes the comparable-home tests, or when the guest declines rebooking.
- **FR-022**: A refund closes the stay. A guest rebooked for some nights MUST NOT also be refunded for those nights.
- **FR-023**: Any amount from EUR 0.01 up to `total_paid` is within policy; the refund agent MUST reject anything outside that range.

#### Uplift budget

- **FR-024**: The system MUST record uplift for each rebooking as (rebooked `nightly_price` − original `nightly_price`) × nights booked, when positive, and keep a running total against the EUR 9,000 incident budget.
- **FR-025**: The EUR 150 per-guest average is a planning figure; the system MUST NOT treat it as a per-guest cap.

#### Host messaging

- **FR-026**: After a non-safety ticket is resolved, the host messaging agent MUST send the original `host_id` one factual message stating the outcome (guest rebooked elsewhere or refunded). The message MUST NOT include guest contact details.

#### Supervision, audit and deadline

- **FR-027**: Every ticket MUST end in exactly one of: a held comparable booking, an issued refund, or a safety hand-off.
- **FR-028**: Every tool call MUST be logged with ticket, agent, tool, inputs, result, time, and the Policy clause relied on.
- **FR-029**: A human supervisor MUST be able to see each ticket's status and pause or take over any ticket.
- **FR-030**: Any ticket the agents cannot resolve under the Policy MUST be escalated to a human supervisor rather than resolved by a rule the Policy does not contain.

### Key Entities

- **Ticket**: One stranded guest's case. Key fields: `ticket_id`, `reservation_id`, `guest_language`, `original_listing_id`, `neighborhood`, `bedrooms`, `party_size`, `check_in_date`, `check_out_date`, `nightly_price`, `total_paid`, `host_id`, `host_cancelled_at`, `host_last_reply_at`, `guest_requested`, `guest_message`.
- **Open listing**: A Lisbon home that might be offered. Key fields: `listing_id` (LST-100001 to LST-100450), `neighborhood`, `max_guests`, `bedrooms`, `available_from`, `available_to`, `status`, `nightly_price`.
- **Classification**: The ticket's type (`rebooking`, `refund`, `safety`) plus, for safety tickets, the condition(s) found.
- **Resolution**: The single remedy for a ticket: booking hold (listing, nights, uplift), refund (amount ≤ `total_paid`), or safety hand-off.
- **Action log entry**: One tool call: ticket, agent, tool, inputs, result, time, Policy clause.
- **Uplift ledger**: Running total of uplift against the EUR 9,000 budget.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Classification matches `expected_outcome` on all 60 incident tickets (34 rebooking, 20 refund, 6 safety).
- **SC-002**: On all 6 safety tickets, zero calls to `issue_refund` or `hold_booking` and exactly one call to `handoff_to_safety_agent`.
- **SC-003**: Zero refunds exceed `total_paid`, and zero stays receive both a refund and a rebooking for the same nights.
- **SC-004**: Every held booking passes all five comparable-home tests; zero held listings are priced above 1.20 × the original `nightly_price`.
- **SC-005**: Zero tool calls are executed outside the calling agent's allowlist.
- **SC-006**: All 60 tickets end with a bed, a refund or a live safety agent before 23:59 on 16 November 2026 (Lisbon time).
- **SC-007**: Total uplift spend stays within EUR 9,000.
- **SC-008**: A supervisor can trace any action back to its ticket, agent and Policy clause from the log alone.
- **SC-009**: Against the 16 November 2026 open listings export, all 34 rebooking tickets are placed in distinct comparable homes, with zero falling back to a refund for lack of a comparable home.

## Assumptions

- The open listings export has its column headers on line 1 and 450 listings (LST-100001 to LST-100450) after it. Its `status` values are a snapshot (314 `available`, 104 `on_hold`, 32 `booked`); the real status is checked again at hold time.
- The ticket and open-listing data come from the two exports named in the Policy (`airbnb_lisbon_stranded_guest_tickets_2026-11-16.csv`, `airbnb_lisbon_open_listings_2026-11-16.csv`). The tickets' `expected_outcome` column is used for testing only and is never read by the agents.
- The six tools are provided by Airbnb's systems; this feature defines who may call them and when, not how they work internally.
- "Neighbouring neighborhood" uses a fixed adjacency list of Lisbon neighbourhoods to be defined in the plan.
- Host messages are written in English; guest-facing replies use `guest_language` where possible.
- Times in the tickets are UTC; Lisbon is on UTC+0 on 16 November 2026, so the midnight deadline is 2026-11-17T00:00:00Z.
- A guest's decision to decline an offer or switch to a refund arrives as a follow-up message on the same ticket.
