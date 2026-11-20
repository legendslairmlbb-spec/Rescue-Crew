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

## LLM endpoint, key and model

Copy `.env.example` to `.env` (ignored by git) and set:

- `LLM_BASE_URL`: any OpenAI-compatible endpoint (default `https://openrouter.ai/api/v1`)
- `LLM_API_KEY`: the key for that endpoint
- `LLM_MODEL`: the model to call first
- `LLM_FALLBACK_MODELS`: optional, comma-separated, tried in order when the previous model
  is rate-limited, unavailable or times out

The older `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` / `OPENROUTER_FALLBACK_MODELS` names still
work. No endpoint, key or model name is written in the code. Check they work:

```bash
uv run rescue-crew-check-llm
```

It prints the model that answered followed by `OK`. Tests never call a model unless
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

## Running the 60 tickets

```bash
uv run rescue-crew-run
```

Runs are resumable. Each finished ticket gets one row in `reports/lisbon-run-state.jsonl`
(ticket_id, outcome, tool calls in order, listing held, refund), written only after its last
step. The next run skips those tickets and treats their homes as taken. A run stops after 3
tickets in a row fail (for example when the free daily model limit is used up), so just run it
again later. When all 60 rows exist it writes `reports/lisbon-results.md`;
`uv run rescue-crew-report` builds that report from the state file at any time.

## Demo support chat window

```bash
uv run rescue-crew-demo
```

Opens on http://127.0.0.1:8765 (local only). It runs one ticket at a time through the same
team, safety gate, allowlists and prompts as the 60-ticket run, on a throwaway in-memory server:
no run-state file is read or written, and every run checks that
`reports/lisbon-run-state.jsonl` is unchanged. Tickets come from
`data/demo/stranded_guest_tickets_2026-12-07.csv` (or `RESCUE_CREW_DEMO_TICKETS`); guest names
and `expected_outcome` are never loaded.

- **Run live** calls the model from `.env` and shows every tool call in order, including
  blocked ones.
- **Try the refund anyway** sends `issue_refund` through the same gate after the run.
- **Play recorded run** replays the last live run of that ticket (saved in
  `data/demo/replays/`, git-ignored), labelled as a replay, for when the endpoint is
  rate-limited.

Demo tickets are dated 7 December while the listings export is from 16 November, so
rebooking tickets may find no comparable home and fall back to a refund.
