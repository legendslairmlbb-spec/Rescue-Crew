"""Policy behaviour of the six tools, on small synthetic fixtures."""

import asyncio
from pathlib import Path

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from rescue_crew.data import DataError, check_full_export, load_listings
from rescue_crew.server import create_server

FIXTURES = Path(__file__).parent / "fixtures"
LISTINGS = FIXTURES / "listings.csv"
TICKETS = FIXTURES / "tickets.csv"

SAFETY_RULE = "Never use this on a safety ticket before handoff_to_safety_agent"


@pytest.fixture
def server():
    return create_server(LISTINGS, TICKETS, require_full_export=False)


def call(server, tool, **args):
    async def go():
        async with Client(server) as c:
            return (await c.call_tool(tool, args)).data

    return asyncio.run(go())


def tool_descriptions(server):
    async def go():
        async with Client(server) as c:
            return {t.name: t.description for t in await c.list_tools()}

    return asyncio.run(go())


# --- loading -----------------------------------------------------------------------------


def test_six_tools_registered(server):
    assert set(tool_descriptions(server)) == {
        "lookup_reservation",
        "search_open_listings",
        "hold_booking",
        "issue_refund",
        "message_host",
        "handoff_to_safety_agent",
    }


def test_load_rejects_note_on_line_1(tmp_path):
    bad = tmp_path / "listings.csv"
    bad.write_text("Export note: generated 16 Nov\n" + LISTINGS.read_text(), encoding="utf-8")
    with pytest.raises(DataError, match="line 1 must be the column headers"):
        load_listings(bad)


@pytest.mark.parametrize("bad_id", ["LST-200001", "LST-100451", "LST-100000"])
def test_load_rejects_ids_outside_export_range(tmp_path, bad_id):
    bad = tmp_path / "listings.csv"
    bad.write_text(LISTINGS.read_text().replace("LST-100001", bad_id), encoding="utf-8")
    with pytest.raises(DataError, match="outside LST-100001..LST-100450"):
        load_listings(bad)


def test_full_export_requires_450_listings():
    with pytest.raises(DataError, match="expected 450"):
        check_full_export(load_listings(LISTINGS))


# --- search_open_listings ----------------------------------------------------------------


def test_search_returns_only_comparable_listings_ranked(server):
    r = call(server, "search_open_listings", ticket_id="LIS-TKT-0001", limit=20)
    ids = [x["listing_id"] for x in r["listings"]]
    # 132.00 is exactly 1.20 x 110.00 and passes; 132.01 fails. Same area, then neighbour,
    # then elsewhere. On-hold, booked, date-gap, too-small listings are excluded.
    assert ids == ["LST-100001", "LST-100003", "LST-100006"]
    assert r["price_ceiling_eur"] == "132.00"


def test_search_ids_all_come_from_the_export(server):
    export_ids = set(load_listings(LISTINGS))
    for tid in ["LIS-TKT-0001", "LIS-TKT-0002", "LIS-TKT-0004"]:
        r = call(server, "search_open_listings", ticket_id=tid, limit=20)
        assert {x["listing_id"] for x in r["listings"]} <= export_ids


def test_search_skips_listings_this_server_already_held(server):
    call(server, "hold_booking", ticket_id="LIS-TKT-0001", listing_id="LST-100001")
    r = call(server, "search_open_listings", ticket_id="LIS-TKT-0004", limit=20)
    assert "LST-100001" not in [x["listing_id"] for x in r["listings"]]


# --- hold_booking ------------------------------------------------------------------------


@pytest.mark.parametrize("listing_id", ["LST-200001", "LST-100999", "LST-100002", "LST-100004"])
def test_hold_rejects_invented_original_or_non_comparable_ids(server, listing_id):
    with pytest.raises(ToolError):
        call(server, "hold_booking", ticket_id="LIS-TKT-0001", listing_id=listing_id)


def test_hold_records_uplift_and_blocks_double_hold(server):
    r = call(server, "hold_booking", ticket_id="LIS-TKT-0001", listing_id="LST-100001")
    assert r["held"] and r["nights"] == 3 and r["uplift_eur"] == "66.00"
    with pytest.raises(ToolError, match="not comparable"):
        call(server, "hold_booking", ticket_id="LIS-TKT-0004", listing_id="LST-100001")
    with pytest.raises(ToolError, match="already holds"):
        call(server, "hold_booking", ticket_id="LIS-TKT-0001", listing_id="LST-100003")


# --- issue_refund ------------------------------------------------------------------------


def test_refund_capped_at_total_paid_not_nights_times_price(server):
    with pytest.raises(ToolError, match="exceeds total_paid"):
        call(server, "issue_refund", ticket_id="LIS-TKT-0002", amount_eur="480.00")
    with pytest.raises(ToolError, match="exceeds total_paid"):
        call(server, "issue_refund", ticket_id="LIS-TKT-0002", amount_eur="432.01")
    r = call(server, "issue_refund", ticket_id="LIS-TKT-0002", amount_eur="432.00")
    assert r == {
        "refunded": True,
        "ticket_id": "LIS-TKT-0002",
        "amount_eur": "432.00",
        "total_paid_eur": "432.00",
    }


@pytest.mark.parametrize("amount", ["0", "0.001", "-5"])
def test_refund_rejects_amounts_below_one_cent(server, amount):
    with pytest.raises(ToolError):
        call(server, "issue_refund", ticket_id="LIS-TKT-0002", amount_eur=amount)


def test_one_remedy_per_stay(server):
    call(server, "hold_booking", ticket_id="LIS-TKT-0001", listing_id="LST-100001")
    with pytest.raises(ToolError, match="one remedy per stay"):
        call(server, "issue_refund", ticket_id="LIS-TKT-0001", amount_eur="330.00")
    call(server, "issue_refund", ticket_id="LIS-TKT-0004", amount_eur="330.00")
    with pytest.raises(ToolError, match="refund closes the stay"):
        call(server, "hold_booking", ticket_id="LIS-TKT-0004", listing_id="LST-100003")
    with pytest.raises(ToolError, match="already refunded"):
        call(server, "issue_refund", ticket_id="LIS-TKT-0004", amount_eur="1.00")


# --- safety ------------------------------------------------------------------------------


def test_after_handoff_no_refund_hold_search_or_host_message(server):
    r = call(
        server,
        "handoff_to_safety_agent",
        ticket_id="LIS-TKT-0003",
        conditions=["injury_or_medical_need"],
        guest_words="I fell on the steps and my knee is bleeding badly.",
    )
    assert r["handed_off"] and r["conditions"] == ["injury_or_medical_need"]
    for tool, args in [
        ("issue_refund", {"amount_eur": "330.00"}),
        ("hold_booking", {"listing_id": "LST-100001"}),
        ("search_open_listings", {}),
        ("message_host", {"message": "Update on your reservation."}),
    ]:
        with pytest.raises(ToolError, match="live safety agent"):
            call(server, tool, ticket_id="LIS-TKT-0003", **args)


def test_handoff_rejects_unknown_conditions(server):
    with pytest.raises(ToolError):
        call(
            server,
            "handoff_to_safety_agent",
            ticket_id="LIS-TKT-0001",
            conditions=["angry"],
            guest_words="This is a nightmare.",
        )


def test_descriptions_carry_the_policy_rules(server):
    d = tool_descriptions(server)
    assert SAFETY_RULE in d["hold_booking"]
    assert SAFETY_RULE in d["issue_refund"]
    assert "total_paid" in d["issue_refund"] and "goodwill" in d["issue_refund"]
    assert "1.20" in d["search_open_listings"]
    assert "never an ID you composed" in d["search_open_listings"]
    for word in ["injury_or_medical_need", "unaccompanied_minor", "figures of speech"]:
        assert word in d["handoff_to_safety_agent"]


def test_readme_tool_list_matches_server(server):
    readme = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
    for name, description in tool_descriptions(server).items():
        assert name in readme
        assert description.strip().splitlines()[0] in readme


# --- lookup_reservation ------------------------------------------------------------------


def test_lookup_hides_test_answers_and_guest_name(server):
    r = call(server, "lookup_reservation", ticket_id="LIS-TKT-0002")
    assert "expected_outcome" not in r and "guest_name" not in r
    assert r["total_paid_eur"] == "432.00" and r["case_status"] == "open"
