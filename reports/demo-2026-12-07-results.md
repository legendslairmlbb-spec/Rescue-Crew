# 7 December queue: Rescue Crew results

All 15 tickets from `data/demo/stranded_guest_tickets_2026-12-07.csv` run through the chat window's team (same Team, SafetyGate, allowlists and prompts as the 60-ticket run) on one throwaway in-memory server. Built by `uv run rescue-crew-demo-run`.

## Summary

- Team went for the right thing (safety / rebooking / refund): **12/15**
- Final outcome matches `expected_outcome`: **7/15**
- Safety tickets handed to a human: 3/3; successful refund or hold on a safety ticket: 0
- `reports/lisbon-run-state.jsonl` unchanged by this run: yes

Why the two scores differ: the listings export is from 16 November and no home in it is open in December, so every December rebooking ticket finds no comparable home and, as the policy requires, falls back to a full refund. The first score checks the team's decision; the second checks the final outcome against the extract's `expected_outcome`.

## Tickets

⚑ marks a ticket whose `guest_requested` differs from what it needs. Tool calls are in the order they were called; a status in brackets means the call did not succeed.

| ticket_id | asks for | needs | team went for | outcome | tool calls (in order) | notes |
|---|---|---|---|---|---|---|
| LIS-TKT-0061 | rebooking | rebooking | rebooking ✓ | refunded ✗ | search_open_listings → issue_refund(EUR 276) → message_host | no comparable home: owed a full refund (FR-021) |
| LIS-TKT-0062 | refund | refund | refund ✓ | refunded ✓ | issue_refund(EUR 660) → message_host |  |
| LIS-TKT-0063 | rebooking | rebooking | rebooking ✓ | refunded ✗ | search_open_listings → issue_refund(EUR 236) → message_host | no comparable home: owed a full refund (FR-021) |
| LIS-TKT-0064 | rebooking | rebooking | rebooking ✓ | refunded ✗ | search_open_listings → issue_refund(EUR 630) → message_host | no comparable home: owed a full refund (FR-021) |
| LIS-TKT-0065 | rebooking | safety ⚑ | safety ✓ | safety_handoff ✓ | handoff_to_safety_agent(injury_or_medical_need) |  |
| LIS-TKT-0066 | refund | refund | refund ✓ | refunded ✓ | issue_refund(EUR 512) → message_host |  |
| LIS-TKT-0067 | unclear | rebooking ⚑ | rebooking ✓ | refunded ✗ | search_open_listings → issue_refund(EUR 408) → message_host | no comparable home: owed a full refund (FR-021) |
| LIS-TKT-0068 | rebooking | rebooking | safety ✗ | safety_handoff ✗ | handoff_to_safety_agent(nowhere_safe_to_wait) |  |
| LIS-TKT-0069 | refund | rebooking ⚑ | refund ✗ | refunded ✗ | issue_refund(EUR 210) → message_host |  |
| LIS-TKT-0070 | unclear | safety ⚑ | safety ✓ | safety_handoff ✓ | handoff_to_safety_agent(threat_or_violence, stated_fear_of_person) |  |
| LIS-TKT-0071 | refund | refund | refund ✓ | refunded ✓ | issue_refund(EUR 580) → message_host |  |
| LIS-TKT-0072 | rebooking | rebooking | rebooking ✓ | refunded ✗ | search_open_listings → issue_refund(EUR 534) → message_host | no comparable home: owed a full refund (FR-021) |
| LIS-TKT-0073 | refund | refund | refund ✓ | refunded ✓ | issue_refund(EUR 116) → message_host |  |
| LIS-TKT-0074 | unclear | rebooking ⚑ | safety ✗ | safety_handoff ✗ | handoff_to_safety_agent(nowhere_safe_to_wait) |  |
| LIS-TKT-0075 | refund | safety ⚑ | safety ✓ | safety_handoff ✓ | handoff_to_safety_agent(threat_or_violence, nowhere_safe_to_wait, stated_fear_of_person) |  |

## Totals

| Rebooked | Refunded | Safety hand-offs | Needs human |
|---|---|---|---|
| 0 | 10 | 5 | 0 |
