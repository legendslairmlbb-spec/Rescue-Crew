"""Checks against the real 16 Nov 2026 exports in data/ (skipped when they are absent)."""

import asyncio
import csv

import pytest
from fastmcp import Client

from rescue_crew.server import DEFAULT_LISTINGS, DEFAULT_TICKETS, create_server

pytestmark = pytest.mark.skipif(
    not (DEFAULT_LISTINGS.is_file() and DEFAULT_TICKETS.is_file()),
    reason="incident exports not present in data/",
)


def rebooking_ticket_ids():
    with DEFAULT_TICKETS.open(encoding="utf-8") as f:
        return [r["ticket_id"] for r in csv.DictReader(f) if r["expected_outcome"] == "rebooking"]


def test_full_export_loads_with_450_listings():
    server = create_server()
    assert len(server.state.listings) == 450


def test_every_search_result_is_an_export_id_and_all_34_can_be_held():
    server = create_server()
    export_ids = set(server.state.listings)
    ticket_ids = rebooking_ticket_ids()
    assert len(ticket_ids) == 34

    async def go():
        async with Client(server) as c:
            counts = {}
            for tid in ticket_ids:
                r = (await c.call_tool("search_open_listings", {"ticket_id": tid})).data
                assert r["listings"], f"{tid} has no comparable home"
                assert {x["listing_id"] for x in r["listings"]} <= export_ids
                counts[tid] = r["comparable_count"]
            # Hold the scarcest tickets first, each into its top-ranked result.
            held = {}
            for tid in sorted(ticket_ids, key=counts.get):
                r = (await c.call_tool("search_open_listings", {"ticket_id": tid})).data
                lid = r["listings"][0]["listing_id"]
                h = (await c.call_tool("hold_booking", {"ticket_id": tid, "listing_id": lid})).data
                held[tid] = h["listing_id"]
            return held

    held = asyncio.run(go())
    assert len(held) == 34 and len(set(held.values())) == 34
    assert server.state.uplift_spent <= 9000
