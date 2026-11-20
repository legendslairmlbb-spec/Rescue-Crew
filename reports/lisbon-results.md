# Lisbon incident: Rescue Crew results

Built from `reports/lisbon-run-state.jsonl` (60 finished tickets; complete). Agents followed `specs/001-lisbon-rescue-crew`; tools came from the Rescue Crew MCP server via langchain-mcp-adapters.

## Summary

| Outcome | Tickets |
|---|---|
| rebooked | 34 |
| refunded | 20 |
| safety_handoff | 6 |

- Matches `expected_outcome` (scoring only, never shown to agents): **60/60**
- Safety tickets handed off: 6/6; successful refund or hold on a safety ticket: 0
- Homes held: 34 (34 distinct listings); refunded in total: EUR 12020.00
- Resolved tickets whose host was not messaged: LIS-TKT-0006
- Model calls: 203; models that answered: `gemini-3-flash-preview`, `gemini-3.5-flash-lite`, `nvidia/nemotron-3-ultra-550b-a55b:free`

## Tickets

Tool calls are in the order they were called. A status in brackets means the call did not succeed (refused by the server, rejected by an allowlist, or blocked by the safety gate). ✗ marks an outcome that differs from `expected_outcome`.

| ticket_id | outcome | expected | tool calls (in order) | listing held | refund | notes |
|---|---|---|---|---|---|---|
| LIS-TKT-0001 | rebooked | rebooking | search_open_listings → hold_booking(LST-100017) → message_host | LST-100017 |  | imported from the 2026-11-19 run |
| LIS-TKT-0002 | rebooked | rebooking | search_open_listings → hold_booking(LST-100447) → message_host | LST-100447 |  | imported from the 2026-11-19 run |
| LIS-TKT-0003 | rebooked | rebooking | search_open_listings → hold_booking(LST-100243) → message_host | LST-100243 |  | imported from the 2026-11-19 run |
| LIS-TKT-0004 | refunded | refund | issue_refund(EUR 168.0) → message_host |  | EUR 168.0 | imported from the 2026-11-19 run |
| LIS-TKT-0005 | rebooked | rebooking | search_open_listings → hold_booking(LST-100342) → message_host | LST-100342 |  | imported from the 2026-11-19 run |
| LIS-TKT-0006 | rebooked | rebooking | search_open_listings → hold_booking(LST-100348) | LST-100348 |  | imported from the 2026-11-19 run, which recorded needs_human: the hold succeeded, then the host message failed on the daily model limit |
| LIS-TKT-0007 | safety_handoff | safety | handoff_to_safety_agent(injury_or_medical_need) |  |  |  |
| LIS-TKT-0008 | refunded | refund | issue_refund(EUR 237) → message_host |  | EUR 237 |  |
| LIS-TKT-0009 | rebooked | rebooking | search_open_listings → hold_booking(LST-100265) → message_host | LST-100265 |  |  |
| LIS-TKT-0010 | rebooked | rebooking | search_open_listings → hold_booking(LST-100382) → message_host | LST-100382 |  |  |
| LIS-TKT-0011 | refunded | refund | issue_refund(EUR 297) → message_host |  | EUR 297 |  |
| LIS-TKT-0012 | rebooked | rebooking | search_open_listings → hold_booking(LST-100340) → message_host | LST-100340 |  |  |
| LIS-TKT-0013 | rebooked | rebooking | search_open_listings → hold_booking(LST-100088) → message_host | LST-100088 |  |  |
| LIS-TKT-0014 | refunded | refund | issue_refund(EUR 140) → message_host |  | EUR 140 |  |
| LIS-TKT-0015 | safety_handoff | safety | handoff_to_safety_agent(nowhere_safe_to_wait, unaccompanied_minor) |  |  |  |
| LIS-TKT-0016 | rebooked | rebooking | search_open_listings → hold_booking(LST-100239) → message_host | LST-100239 |  |  |
| LIS-TKT-0017 | rebooked | rebooking | search_open_listings → hold_booking(LST-100177) → message_host | LST-100177 |  | guest_requested=callback: flagged for a human supervisor |
| LIS-TKT-0018 | refunded | refund | issue_refund(EUR 1278) → message_host |  | EUR 1278 |  |
| LIS-TKT-0019 | rebooked | rebooking | search_open_listings → hold_booking(LST-100411) → message_host | LST-100411 |  |  |
| LIS-TKT-0020 | rebooked | rebooking | search_open_listings → hold_booking(LST-100198) → message_host | LST-100198 |  |  |
| LIS-TKT-0021 | refunded | refund | issue_refund(EUR 192) → message_host |  | EUR 192 |  |
| LIS-TKT-0022 | rebooked | rebooking | search_open_listings → hold_booking(LST-100063) → message_host | LST-100063 |  |  |
| LIS-TKT-0023 | safety_handoff | safety | handoff_to_safety_agent(injury_or_medical_need, nowhere_safe_to_wait) |  |  |  |
| LIS-TKT-0024 | rebooked | rebooking | search_open_listings → hold_booking(LST-100138) → message_host | LST-100138 |  |  |
| LIS-TKT-0025 | refunded | refund | issue_refund(EUR 246) → message_host |  | EUR 246 |  |
| LIS-TKT-0026 | refunded | refund | issue_refund(EUR 832) → message_host |  | EUR 832 |  |
| LIS-TKT-0027 | rebooked | rebooking | search_open_listings → hold_booking(LST-100432) → message_host | LST-100432 |  |  |
| LIS-TKT-0028 | refunded | refund | issue_refund(EUR 432) → message_host |  | EUR 432 |  |
| LIS-TKT-0029 | rebooked | rebooking | search_open_listings → hold_booking(LST-100123) → message_host | LST-100123 |  | guest_requested=other: flagged for a human supervisor |
| LIS-TKT-0030 | refunded | refund | issue_refund(EUR 294) → message_host |  | EUR 294 |  |
| LIS-TKT-0031 | rebooked | rebooking | search_open_listings → hold_booking(LST-100287) → message_host | LST-100287 |  |  |
| LIS-TKT-0032 | rebooked | rebooking | search_open_listings → hold_booking(LST-100283) → message_host | LST-100283 |  |  |
| LIS-TKT-0033 | rebooked | rebooking | search_open_listings → hold_booking(LST-100333) → message_host | LST-100333 |  |  |
| LIS-TKT-0034 | safety_handoff | safety | handoff_to_safety_agent(threat_or_violence, nowhere_safe_to_wait, stated_fear_of_person) |  |  |  |
| LIS-TKT-0035 | rebooked | rebooking | search_open_listings → hold_booking(LST-100212) → message_host | LST-100212 |  |  |
| LIS-TKT-0036 | refunded | refund | issue_refund(EUR 144) → message_host |  | EUR 144 |  |
| LIS-TKT-0037 | refunded | refund | issue_refund(EUR 1332) → message_host |  | EUR 1332 |  |
| LIS-TKT-0038 | rebooked | rebooking | search_open_listings → hold_booking(LST-100406) → message_host | LST-100406 |  |  |
| LIS-TKT-0039 | rebooked | rebooking | search_open_listings → hold_booking(LST-100253) → message_host | LST-100253 |  | guest_requested=callback: flagged for a human supervisor |
| LIS-TKT-0040 | refunded | refund | issue_refund(EUR 306) → message_host |  | EUR 306 |  |
| LIS-TKT-0041 | rebooked | rebooking | search_open_listings → hold_booking(LST-100446) → message_host | LST-100446 |  |  |
| LIS-TKT-0042 | refunded | refund | issue_refund(EUR 948) → message_host |  | EUR 948 |  |
| LIS-TKT-0043 | rebooked | rebooking | search_open_listings → hold_booking(LST-100032) → message_host | LST-100032 |  |  |
| LIS-TKT-0044 | refunded | refund | issue_refund(EUR 324) → message_host |  | EUR 324 |  |
| LIS-TKT-0045 | rebooked | rebooking | search_open_listings → hold_booking(LST-100079) → message_host | LST-100079 |  |  |
| LIS-TKT-0046 | safety_handoff | safety | handoff_to_safety_agent(threat_or_violence, stated_fear_of_person) |  |  |  |
| LIS-TKT-0047 | rebooked | rebooking | search_open_listings → hold_booking(LST-100148) → message_host | LST-100148 |  |  |
| LIS-TKT-0048 | refunded | refund | issue_refund(EUR 580) → message_host |  | EUR 580 |  |
| LIS-TKT-0049 | rebooked | rebooking | search_open_listings → hold_booking(LST-100266) → message_host | LST-100266 |  | guest_requested=callback: flagged for a human supervisor |
| LIS-TKT-0050 | rebooked | rebooking | search_open_listings → hold_booking(LST-100393) → message_host | LST-100393 |  |  |
| LIS-TKT-0051 | rebooked | rebooking | search_open_listings → hold_booking(LST-100358) → message_host | LST-100358 |  |  |
| LIS-TKT-0052 | refunded | refund | issue_refund(EUR 1710) → message_host |  | EUR 1710 |  |
| LIS-TKT-0053 | refunded | refund | issue_refund(EUR 552) → message_host |  | EUR 552 |  |
| LIS-TKT-0054 | rebooked | rebooking | search_open_listings → hold_booking(LST-100201) → message_host | LST-100201 |  |  |
| LIS-TKT-0055 | safety_handoff | safety | handoff_to_safety_agent(injury_or_medical_need) |  |  |  |
| LIS-TKT-0056 | refunded | refund | lookup_reservation → issue_refund(EUR 840) → message_host |  | EUR 840 |  |
| LIS-TKT-0057 | refunded | refund | issue_refund(EUR 1168) → message_host |  | EUR 1168 |  |
| LIS-TKT-0058 | rebooked | rebooking | search_open_listings → hold_booking(LST-100115) → message_host | LST-100115 |  |  |
| LIS-TKT-0059 | rebooked | rebooking | search_open_listings → hold_booking(LST-100139) → message_host | LST-100139 |  | guest_requested=callback: flagged for a human supervisor |
| LIS-TKT-0060 | rebooked | rebooking | search_open_listings → hold_booking(LST-100209) → message_host | LST-100209 |  | guest_requested=other: flagged for a human supervisor |
