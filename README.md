# Rescue Crew

MCP server with the six tools the Rescue Crew agents use for the Lisbon check-in incident of
16 November 2026. The rules come from [the AirCover policy](docs/policy/aircover-lisbon-rules.md)
and [the spec](specs/001-lisbon-rescue-crew/spec.md).

## Setup

```bash
uv sync
```

Put the two incident exports in `data/` (ignored by git):

- `data/airbnb_lisbon_open_listings_2026-11-16.csv`
- `data/airbnb_lisbon_stranded_guest_tickets_2026-11-16.csv`

Other paths can be set with `RESCUE_CREW_LISTINGS_CSV` and `RESCUE_CREW_TICKETS_CSV`. The server
loads both files once at start and refuses to start if the listings file does not have its
headers on line 1 and exactly 450 listings, LST-100001 to LST-100450.

## Gemini key

Copy `.env.example` to `.env` (ignored by git) and set `GOOGLE_AI_API_KEY` to a Google AI key.
The default model is `gemini-3.5-flash-lite`; change it with `GEMINI_MODEL`. Check the key works:

```bash
uv run rescue-crew-check-llm
```

It prints `gemini-3.5-flash-lite: OK` on success. Tests never call Gemini unless
`RESCUE_CREW_LIVE_LLM=1` is set.

## Run (stdio)

```bash
uv run rescue-crew
```

## Use with Claude Code

Register the server once, giving the full path to this repo (`--directory` also makes `data/`
resolve correctly):

```bash
claude mcp add rescue-crew -- uv run --directory "/path/to/Rescue-Crew" rescue-crew
```

Then run `claude mcp list` to check it is connected, and `/mcp` inside Claude Code to see the tools.

## Tools

Printed from the running server (`fastmcp.Client(...).list_tools()`); `?` marks an optional input.

```text
lookup_reservation(ticket_id)
    Return a stranded guest's reservation and the current state of their case.
search_open_listings(ticket_id, limit?)
    Find open Lisbon homes comparable to the guest's cancelled booking.
hold_booking(ticket_id, listing_id)
    Hold a comparable home for the guest's whole remaining stay.
issue_refund(ticket_id, amount_eur)
    Refund a stranded guest, capped at the ticket's total_paid.
message_host(ticket_id, message)
    Send the original host one factual message about the reservation's outcome.
handoff_to_safety_agent(ticket_id, conditions, guest_words)
    Hand a safety ticket to a live Trust and Safety agent. Call this first.
```

## Rules in practice

- Price ceiling: on an original EUR 110.00 per night, a home at EUR 132.00 (exactly 1.20×) is offered and one at EUR 132.01 is not.
- Refund cap: LIS-TKT-0028 paid EUR 432.00 with a promo, not 4 × EUR 120.00 = EUR 480.00, so `issue_refund` allows up to EUR 432.00 and rejects EUR 432.01.

## Test & lint

```bash
uv run pytest
uv run ruff check .
```

Tests in `tests/test_incident_data.py` run only when the exports are in `data/`.
