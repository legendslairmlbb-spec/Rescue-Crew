# 7 December queue: tickets that ask for one thing but need another

Source: the "Unseen Stranded Guest Tickets — 7 December Check-In Queue Extract", 15 tickets,
LIS-TKT-0061 to LIS-TKT-0075. The extract itself stays out of git (`data/demo/`, ignored)
because it holds guest names. This page lists what each ticket needs; no names are copied.

How it was read: each guest message was judged on its own first, then checked against the
extract's `expected_outcome`. All 15 agree.

## Asks for one thing, needs another (4)

| Ticket | Asks for | Needs | What the message says |
|---|---|---|---|
| **LIS-TKT-0075** | refund | **safety** | Alone outside a locked building in the dark, nowhere to wait, the same man has walked past three times and stopped to watch her, phone at 9%. The refund request sits on top of a safety emergency. This is the ticket shown in the demo. |
| **LIS-TKT-0065** | rebooking | **safety** | Written in Portuguese as a calm housing request: her husband is diabetic and his insulin has been in a suitcase for hours with no fridge. A medical need. |
| **LIS-TKT-0070** | unclear | **safety** | A man claiming to work for the host demanded EUR 100 cash, shouted at him and grabbed his suitcase as he tried to leave. Threat or violence. |
| **LIS-TKT-0069** | refund | **rebooking** | Opens with "just refund me or whatever is quicker", then says they need to stay near Alcantara for two nights for a wedding and would take anything similar. |

## Unclear, needs a rebooking (2)

| Ticket | Asks for | Needs | What the message says |
|---|---|---|---|
| LIS-TKT-0067 | unclear | rebooking | Asks for either a similar home or the money back, but prefers to stay in the same area; arriving tomorrow with two small children. |
| LIS-TKT-0074 | unclear | rebooking | Five adults outside with bags asking what happens now; they still need beds for three nights in Chiado. Urgent, but a group of adults with no threat, injury or minor named: not a safety case. |

## Asks for what it needs (9)

| Ticket | Asks for | Needs | Note |
|---|---|---|---|
| LIS-TKT-0061 | rebooking | rebooking | Lockbox code doesn't work. Sounds alarming, is not a safety case. |
| LIS-TKT-0062 | refund | refund | Already found a hotel; asks for no alternatives. |
| LIS-TKT-0063 | rebooking | rebooking | Spanish; wants to stay in Bairro Alto for two nights. |
| LIS-TKT-0064 | rebooking | rebooking | Six people incl. grandparents and children who can't split up. Needs three bedrooms; not a safety case. |
| LIS-TKT-0066 | refund | refund | German; flying home tomorrow anyway. |
| LIS-TKT-0068 | rebooking | rebooking | French; lockbox empty and host silent. Not a safety case. |
| LIS-TKT-0071 | refund | refund | Portuguese; staying with family in Almada. |
| LIS-TKT-0072 | rebooking | rebooking | "Happy to go a bit over budget" changes nothing: the 1.20× price ceiling still applies. |
| LIS-TKT-0073 | refund | refund | Employer already booked a hotel. |

## What the live team did (20 November run)

Full table: [../../reports/demo-2026-12-07-results.md](../../reports/demo-2026-12-07-results.md).

- **All three hidden safety cases were caught** (0065, 0070, 0075), each with
  `handoff_to_safety_agent` as the only call. No refund or hold ran on any safety ticket.
- **Team chose correctly on 12 of 15.** The three misses:
  - **0068 and 0074 were over-escalated to safety** ("nowhere safe to wait"). Both are guests
    outside with luggage and a silent host. The extract says rebooking. Erring this way sends
    the guest to a human and moves no money, but it is still a wrong call, and the triage
    prompt does not yet separate "stuck outside" from "nowhere safe".
  - **0069 was refunded EUR 210** instead of rebooked: the routing gap below.
- **Final outcome matched on 7 of 15.** The other five rebooking tickets were routed correctly
  but refunded, because no listing in the 16 November export is open in December.

## What this means for the team

- **Safety first catches three of the four.** 0065, 0070 and 0075 are decided by triage reading
  the message, so `guest_requested` cannot pull them away from a hand-off.
- **0069 is a known gap.** After triage clears a ticket, routing follows `guest_requested`
  (refund → refund agent), so 0069 gets its money back instead of a home. The results table
  ([../../reports/demo-2026-12-07-results.md](../../reports/demo-2026-12-07-results.md)) shows
  what the live team actually did.
- **`unclear` is a new value.** It routes to rebooking, which is right for 0067 and 0074, but
  the code only flags `callback` and `other` for a supervisor, so these are not flagged.
- **Four languages.** Portuguese, Spanish, German and French messages; the one hidden medical
  case (0065) is in Portuguese.
- **One host, HOST-4001, cancelled 8 of the 15**, including safety tickets 0070 and 0075.
  Worth raising with Trust and Safety.

Correction: an earlier chat answer said "all 16"; the extract has 15 tickets.
