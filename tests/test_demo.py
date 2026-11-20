"""Demo chat window: same team and gate, throwaway server, nothing written to the real run."""

import asyncio
import json

import pytest
from starlette.testclient import TestClient
from test_agents import FIXTURES, ScriptedModel

from rescue_crew import demo
from rescue_crew.demo import DemoSession, create_app, load_demo_tickets


@pytest.fixture
def session(tmp_path):
    state = tmp_path / "lisbon-run-state.jsonl"
    state.write_text('{"ticket_id": "LIS-TKT-0099", "outcome": "rebooked"}\n', encoding="utf-8")
    return DemoSession(
        FIXTURES / "tickets.csv",
        FIXTURES / "listings.csv",
        model_factory=lambda _tools: ScriptedModel(),
        state_file=state,
        replay_dir=tmp_path / "replays",
        require_full_export=False,
    )


def test_window_never_loads_guest_names_or_expected_outcome():
    tickets = load_demo_tickets(FIXTURES / "tickets.csv")
    for t in tickets.values():
        assert "guest_name" not in t and "expected_outcome" not in t
    assert "Test Guest" not in json.dumps(tickets)


def test_refund_request_with_emergency_is_handed_off_and_refund_is_blocked(session):
    events = []

    async def go():
        r = await session.run("LIS-TKT-0003", events.append)
        status = await session.try_refund(events.append)
        await session.close()
        return r, status

    r, status = asyncio.run(go())
    assert r.outcome == "safety_handoff"
    assert [(c.tool, c.status) for c in r.tool_calls] == [
        ("handoff_to_safety_agent", "success"),
        ("issue_refund", "blocked_by_safety_gate"),
    ]
    assert status == "blocked_by_safety_gate"
    tools = [e for e in events if e["type"] == "tool"]
    assert [e["status"] for e in tools] == ["success", "blocked_by_safety_gate"]
    outcome = next(e for e in events if e["type"] == "outcome")
    assert outcome["state_file_unchanged"] is True
    assert events[-1] == {
        "type": "manual_done",
        "status": "blocked_by_safety_gate",
        "state_file_unchanged": True,
    }
    assert session.state_untouched()


def test_each_run_gets_a_fresh_server_and_gate(session):
    async def go():
        first = await session.run("LIS-TKT-0003", lambda e: None)
        second = await session.run("LIS-TKT-0003", lambda e: None)
        await session.close()
        return first, second

    first, second = asyncio.run(go())
    assert first.outcome == second.outcome == "safety_handoff"
    assert [c.status for c in second.tool_calls] == ["success"]


def test_live_run_is_recorded_for_replay_but_edited_messages_are_not(session):
    async def go():
        await session.run("LIS-TKT-0003", lambda e: None)
        await session.try_refund(lambda e: None)
        await session.run("LIS-TKT-0002", lambda e: None, message="Edited text, refund please.")
        await session.close()

    asyncio.run(go())
    assert set(session.replays()) == {"LIS-TKT-0003"}
    rec = session.load_replay("LIS-TKT-0003")
    assert [e["type"] for e in rec["events"]][-1] == "outcome"
    assert any(e.get("status") == "blocked_by_safety_gate" for e in rec["refund_attempt"])


def test_rebooking_ticket_runs_the_normal_path(session):
    async def go():
        r = await session.run("LIS-TKT-0001", lambda e: None)
        await session.close()
        return r

    r = asyncio.run(go())
    assert r.outcome == "rebooked"
    assert [c.tool for c in r.tool_calls] == [
        "search_open_listings",
        "hold_booking",
        "message_host",
    ]


def lines(response):
    return [json.loads(x) for x in response.text.splitlines() if x]


def test_web_app_live_refund_and_replay(session, monkeypatch):
    monkeypatch.setattr(demo, "REPLAY_DELAY_S", 0)
    with TestClient(create_app(session)) as client:
        assert "Rescue Crew Support" in client.get("/").text
        data = client.get("/api/tickets").json()
        assert "Test Guest" not in json.dumps(data)
        assert data["replays"] == {}

        live = lines(client.post("/api/run", json={"ticket_id": "LIS-TKT-0003", "mode": "live"}))
        assert live[0] == {"type": "live"}
        assert live[-1]["outcome"] == "safety_handoff"

        refund = lines(client.post("/api/refund", json={"mode": "live"}))
        assert any(e.get("status") == "blocked_by_safety_gate" for e in refund)

        replay = lines(
            client.post("/api/run", json={"ticket_id": "LIS-TKT-0003", "mode": "replay"})
        )
        assert replay[0]["type"] == "replay"
        assert replay[1:] == live[1:]
        replay_refund = lines(
            client.post("/api/refund", json={"ticket_id": "LIS-TKT-0003", "mode": "replay"})
        )
        assert replay_refund == refund

        missing = lines(
            client.post("/api/run", json={"ticket_id": "LIS-TKT-0001", "mode": "replay"})
        )
        assert missing[-1]["type"] == "error"
    assert session.state_untouched()
