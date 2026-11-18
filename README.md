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

## Run (stdio)

```bash
uv run rescue-crew
```

## Test & lint

```bash
uv run pytest
uv run ruff check .
```

Tests in `tests/test_incident_data.py` run only when the exports are in `data/`.
