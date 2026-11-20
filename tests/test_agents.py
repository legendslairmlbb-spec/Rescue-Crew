"""Agent team tests: scripted fake models, real MCP tools via langchain-mcp-adapters."""

import asyncio
import json
import re
from pathlib import Path

import pytest
from fastmcp import Client
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_mcp_adapters.tools import load_mcp_tools

from rescue_crew import agents
from rescue_crew.agents import SafetyGate, Team
from rescue_crew.run import build_report, to_row
from rescue_crew.server import create_server
from rescue_crew.state import append_row, load_state

FIXTURES = Path(__file__).parent / "fixtures"


def ticket(tid, requested, message, total_paid="330.00"):
    return {
        "ticket_id": tid,
        "guest_requested": requested,
        "guest_message": message,
        "total_paid": total_paid,
    }


TICKETS = [
    ticket("LIS-TKT-0001", "rebooking", "Cancelled at the door, find us another flat."),
    ticket("LIS-TKT-0002", "refund", "Just refund what we paid.", "432.00"),
    ticket("LIS-TKT-0003", "refund", "Refund me. My knee is bleeding badly."),
    ticket("LIS-TKT-0004", "callback", "Call me, we still need a one-bed tonight."),
]


class ScriptedModel:
    """Stands in for an LLM: decides from the system prompt which agent it is playing."""

    def __init__(self, overrides=None):
        self.overrides = overrides or {}
        self.calls = 0

    async def ainvoke(self, messages):
        self.calls += 1
        system = next(m.content for m in messages if isinstance(m, SystemMessage))
        human = next(m.content for m in messages if isinstance(m, HumanMessage))
        tid = re.search(r"LIS-TKT-\d{4}", human).group(0)
        tool_results = [m for m in messages if isinstance(m, ToolMessage)]
        role = next(r for r in ("triage", "rebooking", "refund", "host messaging") if r in system)
        if role in self.overrides:
            return self.overrides[role](tid, human, tool_results)

        def call(name, **args):
            return AIMessage("", tool_calls=[{"name": name, "args": args, "id": f"c{self.calls}"}])

        if role == "triage":
            if "bleeding" in human:
                return call(
                    "handoff_to_safety_agent",
                    ticket_id=tid,
                    conditions=["injury_or_medical_need"],
                    guest_words=human,
                )
            return AIMessage("CLEAR")
        if role == "rebooking":
            if not tool_results:
                return call("search_open_listings", ticket_id=tid)
            listings = json.loads(tool_results[0].content)["listings"]
            if not listings:
                return AIMessage("NO_COMPARABLE")
            return call("hold_booking", ticket_id=tid, listing_id=listings[0]["listing_id"])
        if role == "refund":
            amount = re.search(r"total_paid_eur: (\S+)", human).group(1)
            return call("issue_refund", ticket_id=tid, amount_eur=amount)
        return call("message_host", ticket_id=tid, message="The guest was moved or refunded.")


def run_team(tickets, overrides=None):
    server = create_server(
        FIXTURES / "listings.csv", FIXTURES / "tickets.csv", require_full_export=False
    )

    async def go():
        async with Client(server) as c:
            tools = await load_mcp_tools(c.session)
            team = Team(tools, lambda _tools: ScriptedModel(overrides))
            return [await team.run_ticket(t) for t in tickets]

    return asyncio.run(go()), server.state


def tools_called(result):
    return [(c.tool, c.status) for c in result.tool_calls]


def test_full_team_flow_on_fixture_tickets():
    results, state = run_team(TICKETS)
    by_id = {r.ticket_id: r for r in results}

    r1 = by_id["LIS-TKT-0001"]
    assert r1.outcome == "rebooked"
    assert tools_called(r1) == [
        ("search_open_listings", "success"),
        ("hold_booking", "success"),
        ("message_host", "success"),
    ]

    r2 = by_id["LIS-TKT-0002"]
    assert r2.outcome == "refunded"
    assert tools_called(r2) == [("issue_refund", "success"), ("message_host", "success")]
    assert str(state.refunds["LIS-TKT-0002"]) == "432.00"

    r3 = by_id["LIS-TKT-0003"]
    assert r3.outcome == "safety_handoff"
    assert tools_called(r3) == [("handoff_to_safety_agent", "success")]
    assert r3.safety_conditions == ["injury_or_medical_need"]
    assert "LIS-TKT-0003" not in state.refunds

    r4 = by_id["LIS-TKT-0004"]
    assert r4.outcome == "rebooked" and r4.route == "rebooking"
    assert any("flagged for a human supervisor" in n for n in r4.notes)
    # Shared server session: the second guest cannot get the first guest's home.
    assert state.holds["LIS-TKT-0001"] != state.holds["LIS-TKT-0004"]


def test_triage_cannot_call_money_tools():
    def sneaky_triage(tid, human, tool_results):
        return AIMessage(
            "",
            tool_calls=[
                {"name": "issue_refund", "args": {"ticket_id": tid, "amount_eur": "1"}, "id": "x"}
            ],
        )

    results, state = run_team([TICKETS[1]], overrides={"triage": sneaky_triage})
    r = results[0]
    assert ("issue_refund", "rejected_not_allowed") in tools_called(r)
    assert r.outcome == "needs_human" and not state.refunds


def test_unclear_triage_blocks_every_money_and_booking_tool():
    results, state = run_team(
        [TICKETS[0]], overrides={"triage": lambda *a: AIMessage("Not sure, maybe.")}
    )
    r = results[0]
    assert r.outcome == "needs_human" and r.tool_calls == []
    assert not state.holds and not state.refunds


def test_agent_using_another_ticket_id_is_rejected():
    def wrong_ticket(tid, human, tool_results):
        if tool_results:
            return AIMessage("done")
        return AIMessage(
            "",
            tool_calls=[
                {
                    "name": "issue_refund",
                    "args": {"ticket_id": "LIS-TKT-0001", "amount_eur": "330.00"},
                    "id": "y",
                }
            ],
        )

    results, state = run_team([TICKETS[1]], overrides={"refund": wrong_ticket})
    assert ("issue_refund", "rejected_wrong_ticket") in tools_called(results[0])
    assert not state.refunds


def test_no_comparable_home_falls_back_to_full_refund():
    results, state = run_team(
        [TICKETS[0]], overrides={"rebooking": lambda *a: AIMessage("NO_COMPARABLE")}
    )
    r = results[0]
    assert r.outcome == "refunded" and str(state.refunds["LIS-TKT-0001"]) == "330.00"


def test_safety_gate_rules():
    gate = SafetyGate()
    assert gate.check("T1", "issue_refund") and gate.check("T1", "hold_booking")
    assert gate.check("T1", "lookup_reservation")
    assert gate.check("T1", "handoff_to_safety_agent") is None
    gate.clear("T1")
    assert gate.check("T1", "issue_refund") is None
    gate.mark_safety("T2")
    for tool in ("issue_refund", "hold_booking", "message_host", "handoff_to_safety_agent"):
        assert gate.check("T2", tool)


def test_allowlists_match_spec():
    assert agents.ALLOWLIST["triage"] == {"handoff_to_safety_agent"}
    assert "issue_refund" not in agents.ALLOWLIST["rebooking"]
    assert "hold_booking" not in agents.ALLOWLIST["refund"]
    for agent in ("rebooking", "refund", "host_messaging"):
        assert "handoff_to_safety_agent" not in agents.ALLOWLIST[agent]


def test_no_model_name_or_key_in_agent_code():
    source = Path(agents.__file__).read_text(encoding="utf-8")
    assert ":free" not in source and "sk-or-" not in source


EXPECTED = {
    "LIS-TKT-0001": "rebooking",
    "LIS-TKT-0002": "refund",
    "LIS-TKT-0003": "safety",
    "LIS-TKT-0004": "rebooking",
}
ORDER = list(EXPECTED)


def failing_host(tid, human, tool_results):
    raise RuntimeError("Rate limit exceeded: free-models-per-day")


# --- resumable runs ----------------------------------------------------------------------


def test_failed_host_message_keeps_the_hold_and_finishes_the_ticket():
    results, state = run_team([TICKETS[0]], overrides={"host messaging": failing_host})
    r = results[0]
    assert r.outcome == "rebooked" and r.finished and not r.host_messaged
    assert r.held_listing_id == state.holds["LIS-TKT-0001"]
    assert any("after rebooked" in n for n in r.notes)


def test_error_before_any_remedy_leaves_ticket_unfinished():
    def failing_triage(*a):
        raise RuntimeError("Rate limit exceeded: free-models-per-day")

    results, state = run_team([TICKETS[0]], overrides={"triage": failing_triage})
    r = results[0]
    assert r.outcome == "needs_human" and r.error and not r.finished
    assert not state.holds


def test_unclear_triage_is_a_finished_escalation():
    results, _ = run_team([TICKETS[0]], overrides={"triage": lambda *a: AIMessage("unsure")})
    assert results[0].finished and results[0].error is None


def test_state_rows_round_trip_and_reject_duplicates(tmp_path):
    results, _ = run_team(TICKETS)
    path = tmp_path / "state.jsonl"
    for r in results:
        append_row(path, to_row(r))
    rows = load_state(path)
    assert list(rows) == ORDER
    assert rows["LIS-TKT-0002"]["refund_eur"] == "432.00"
    assert rows["LIS-TKT-0001"]["tool_call_order"] == [
        "search_open_listings",
        "hold_booking(LST-100001)",
        "message_host",
    ]
    append_row(path, to_row(results[0]))
    with pytest.raises(ValueError, match="appears twice"):
        load_state(path)


def test_restarted_server_treats_earlier_holds_as_taken(tmp_path):
    first, _ = run_team(TICKETS[:1])  # LIS-TKT-0001 holds LST-100001
    path = tmp_path / "state.jsonl"
    append_row(path, to_row(first[0]))

    server = create_server(
        FIXTURES / "listings.csv",
        FIXTURES / "tickets.csv",
        require_full_export=False,
        state_path=path,
    )
    st = server.state
    assert st.holds == {"LIS-TKT-0001": "LST-100001"}
    assert st.live_status["LST-100001"] == "on_hold"

    async def go():
        async with Client(server) as c:
            found = (await c.call_tool("search_open_listings", {"ticket_id": "LIS-TKT-0004"})).data
            ids = [x["listing_id"] for x in found["listings"]]
            refused = await c.call_tool(
                "hold_booking",
                {"ticket_id": "LIS-TKT-0004", "listing_id": "LST-100001"},
                raise_on_error=False,
            )
            again = await c.call_tool(
                "hold_booking",
                {"ticket_id": "LIS-TKT-0001", "listing_id": "LST-100003"},
                raise_on_error=False,
            )
            return ids, refused.is_error, again.is_error

    ids, refused, again = asyncio.run(go())
    assert "LST-100001" not in ids and refused and again


def test_state_naming_one_listing_twice_is_refused(tmp_path):
    path = tmp_path / "state.jsonl"
    for tid in ("LIS-TKT-0001", "LIS-TKT-0004"):
        append_row(path, {"ticket_id": tid, "outcome": "rebooked", "held_listing_id": "LST-100001"})
    with pytest.raises(ValueError, match="held by two tickets"):
        create_server(
            FIXTURES / "listings.csv",
            FIXTURES / "tickets.csv",
            require_full_export=False,
            state_path=path,
        )


def test_report_is_built_from_state_rows_only(tmp_path):
    results, _ = run_team(TICKETS)
    rows = {r.ticket_id: to_row(r) for r in results}

    partial = build_report(
        {k: rows[k] for k in ORDER[:2]}, EXPECTED, ORDER, tmp_path / "partial.md"
    )
    assert "PARTIAL: 2 of 4" in partial.read_text(encoding="utf-8")

    text = build_report(rows, EXPECTED, ORDER, tmp_path / "final.md").read_text(encoding="utf-8")
    assert "complete" in text and "**4/4**" in text
    line = next(x for x in text.splitlines() if x.startswith("| LIS-TKT-0001"))
    assert (
        line.index("search_open_listings") < line.index("hold_booking") < line.index("message_host")
    )
    assert "handoff_to_safety_agent(injury_or_medical_need)" in text
    assert "EUR 432.00" in text
    # The three totals are the last thing in the report: 2 rebooked, 1 refunded, 1 safety.
    assert text.rstrip().splitlines()[-3:] == [
        "| Rebooked | Refunded | Safety hand-offs |",
        "|---|---|---|",
        "| 2 | 1 | 1 |",
    ]
