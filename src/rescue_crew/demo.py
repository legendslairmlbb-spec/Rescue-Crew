"""Support chat window for demos: watch the real Rescue Crew team work one ticket.

It runs the same Team, SafetyGate, allowlists and prompts as the 60-ticket run, against a
throwaway in-memory MCP server:

- tickets come from a demo file (default: the 7 December extract in data/demo/, git-ignored);
- no run-state file is read or written, and the window checks after every run that
  reports/lisbon-run-state.jsonl is byte-for-byte unchanged;
- guest names and expected_outcome are never loaded into the window or the agents.

Live runs are recorded to data/demo/replays/ so a run can be played back if the model
endpoint is rate-limited during a demo. Replays are labelled as replays in the window.

Start it with ``uv run rescue-crew-demo`` and open http://127.0.0.1:8765.
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import os
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastmcp import Client
from langchain_mcp_adapters.tools import load_mcp_tools
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, StreamingResponse
from starlette.routing import Route

from rescue_crew.agents import Team, TicketResult, make_model_factory
from rescue_crew.server import DEFAULT_LISTINGS, create_server
from rescue_crew.state import DEFAULT_STATE

REPO = Path(__file__).resolve().parents[2]
DEMO_TICKETS = Path("data/demo/stranded_guest_tickets_2026-12-07.csv")
REPLAY_DIR = Path("data/demo/replays")
PAGE = Path(__file__).with_name("demo_page.html")
SHOWN_FIELDS = ("ticket_id", "guest_language", "guest_requested", "guest_message", "total_paid")
AGENT_FIELDS = ("ticket_id", "guest_requested", "guest_message", "total_paid")
REPLAY_DELAY_S = 0.7

Emit = Callable[[dict[str, Any]], None]


def load_demo_tickets(path: Path) -> dict[str, dict[str, str]]:
    """Ticket fields the window may show. Guest names and expected_outcome are dropped."""
    with path.open(encoding="utf-8", newline="") as f:
        return {r["ticket_id"]: {k: r[k] for k in SHOWN_FIELDS} for r in csv.DictReader(f)}


def file_digest(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


class DemoSession:
    """One ticket at a time on a fresh throwaway server, kept open for a follow-up attempt."""

    def __init__(
        self,
        tickets_path: Path,
        listings_path: Path = DEFAULT_LISTINGS,
        model_factory: Callable[[list], Any] | None = None,
        state_file: Path = REPO / DEFAULT_STATE,
        replay_dir: Path | None = REPO / REPLAY_DIR,
        require_full_export: bool = True,
    ):
        self.tickets_path = Path(tickets_path)
        self.listings_path = Path(listings_path)
        self.tickets = load_demo_tickets(self.tickets_path)
        self._model_factory = model_factory
        self.state_file = state_file
        self.state_digest = file_digest(state_file)
        self.replay_dir = replay_dir
        self.require_full_export = require_full_export
        self.lock = asyncio.Lock()
        self._stack: AsyncExitStack | None = None
        self.team: Team | None = None
        self.result: TicketResult | None = None
        self._recording: dict[str, Any] | None = None

    # -- helpers ---------------------------------------------------------------------------

    def model_factory(self) -> Callable[[list], Any]:
        if self._model_factory is None:  # read .env only when a live run is asked for
            self._model_factory = make_model_factory(str(REPO / ".env"))
        return self._model_factory

    def state_untouched(self) -> bool:
        return file_digest(self.state_file) == self.state_digest

    def replays(self) -> dict[str, str]:
        if not self.replay_dir or not self.replay_dir.is_dir():
            return {}
        out = {}
        for p in sorted(self.replay_dir.glob("LIS-TKT-*.json")):
            out[p.stem] = json.loads(p.read_text(encoding="utf-8")).get("recorded_at", "")
        return out

    def _save_recording(self) -> None:
        if self.replay_dir is None or self._recording is None:
            return
        self.replay_dir.mkdir(parents=True, exist_ok=True)
        path = self.replay_dir / f"{self._recording['ticket_id']}.json"
        path.write_text(json.dumps(self._recording, indent=1), encoding="utf-8")

    async def close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack, self.team, self.result, self._recording = None, None, None, None

    def _outcome_event(self, r: TicketResult) -> dict[str, Any]:
        return {
            "type": "outcome",
            "ticket_id": r.ticket_id,
            "outcome": r.outcome,
            "safety_conditions": r.safety_conditions,
            "held_listing_id": r.held_listing_id,
            "refund_eur": r.refund_eur,
            "host_messaged": r.host_messaged,
            "notes": r.notes,
            "model_calls": r.model_calls,
            "models_used": r.models_used,
            "state_file_unchanged": self.state_untouched(),
        }

    # -- live ------------------------------------------------------------------------------

    async def run(self, ticket_id: str, emit: Emit, message: str | None = None) -> TicketResult:
        """Run one ticket through the real team on a fresh throwaway server."""
        if ticket_id not in self.tickets:
            raise KeyError(f"unknown ticket_id {ticket_id}")
        await self.close()
        ticket = {k: self.tickets[ticket_id][k] for k in AGENT_FIELDS}
        edited = message is not None and message.strip() != ticket["guest_message"].strip()
        if edited:
            ticket["guest_message"] = message.strip()

        events: list[dict[str, Any]] = []

        def record(event: dict[str, Any]) -> None:
            events.append(event)
            emit(event)

        server = create_server(
            self.listings_path,
            self.tickets_path,
            require_full_export=self.require_full_export,
            state_path=None,  # throwaway: no earlier run is restored, nothing is written
        )
        self._stack = AsyncExitStack()
        client = await self._stack.enter_async_context(Client(server))
        tools = await load_mcp_tools(client.session)
        self.team = Team(tools, self.model_factory())
        self.team.on_event = record
        self.result = await self.team.run_ticket(ticket)
        record(self._outcome_event(self.result))
        if not edited:  # only the ticket's own message is worth replaying
            self._recording = {
                "ticket_id": ticket_id,
                "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "events": events,
                "refund_attempt": [],
            }
            self._save_recording()
        return self.result

    async def try_refund(self, emit: Emit) -> str:
        """Send issue_refund for total_paid through the gate, after the run has finished."""
        if self.team is None or self.result is None:
            raise RuntimeError("run a ticket first")
        events: list[dict[str, Any]] = []

        def record(event: dict[str, Any]) -> None:
            events.append(event)
            emit(event)

        self.team.on_event = record
        tid = self.result.ticket_id
        record({"type": "manual", "text": "Someone tries the refund anyway"})
        args = {"ticket_id": tid, "amount_eur": self.tickets[tid]["total_paid"]}
        status = await self.team.attempt("refund", "issue_refund", args, self.result)
        record(
            {
                "type": "manual_done",
                "status": "success" if status == "success" else status,
                "state_file_unchanged": self.state_untouched(),
            }
        )
        if self._recording is not None:
            self._recording["refund_attempt"] = events
            self._save_recording()
        return status

    # -- replay ----------------------------------------------------------------------------

    def load_replay(self, ticket_id: str) -> dict[str, Any]:
        if self.replay_dir is None:
            raise KeyError("replays are off")
        path = self.replay_dir / f"{ticket_id}.json"
        if not path.is_file():
            raise KeyError(f"no recorded run for {ticket_id}")
        return json.loads(path.read_text(encoding="utf-8"))


# -- web app ---------------------------------------------------------------------------------


def _stream(work: Callable[[Emit], Any]) -> StreamingResponse:
    """Run ``work(emit)`` and stream every emitted event as one JSON line."""
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def body() -> AsyncIterator[bytes]:
        async def runner() -> None:
            try:
                await work(queue.put_nowait)
            except Exception as e:  # noqa: BLE001 - shown in the window, never crashes it
                queue.put_nowait({"type": "error", "message": f"{type(e).__name__}: {e}"[:300]})
            finally:
                queue.put_nowait(None)

        task = asyncio.create_task(runner())
        while (event := await queue.get()) is not None:
            yield (json.dumps(event) + "\n").encode()
        await task

    return StreamingResponse(body(), media_type="application/x-ndjson")


def _replay_delay(body: dict[str, Any]) -> float:
    """Pause between replayed events; ``fast`` plays instantly (for screenshots)."""
    return 0.0 if body.get("fast") else REPLAY_DELAY_S


def create_app(session: DemoSession) -> Starlette:
    async def page(_: Request) -> HTMLResponse:
        return HTMLResponse(PAGE.read_text(encoding="utf-8"))

    async def tickets(_: Request) -> JSONResponse:
        return JSONResponse(
            {
                "tickets": list(session.tickets.values()),
                "replays": session.replays(),
                "state_file_unchanged": session.state_untouched(),
            }
        )

    async def run(request: Request) -> StreamingResponse:
        body = await request.json()
        tid, mode = body.get("ticket_id", ""), body.get("mode", "live")

        async def work(emit: Emit) -> None:
            async with session.lock:
                if mode == "replay":
                    rec = session.load_replay(tid)
                    emit({"type": "replay", "recorded_at": rec["recorded_at"]})
                    for event in rec["events"]:
                        await asyncio.sleep(_replay_delay(body))
                        emit(event)
                    return
                emit({"type": "live"})
                await session.run(tid, emit, body.get("message"))

        return _stream(work)

    async def refund(request: Request) -> StreamingResponse:
        body = await request.json()

        async def work(emit: Emit) -> None:
            async with session.lock:
                if body.get("mode") == "replay":
                    rec = session.load_replay(body.get("ticket_id", ""))
                    if not rec.get("refund_attempt"):
                        raise RuntimeError("this recording has no refund attempt")
                    for event in rec["refund_attempt"]:
                        await asyncio.sleep(_replay_delay(body))
                        emit(event)
                    return
                await session.try_refund(emit)

        return _stream(work)

    return Starlette(
        routes=[
            Route("/", page),
            Route("/api/tickets", tickets),
            Route("/api/run", run, methods=["POST"]),
            Route("/api/refund", refund, methods=["POST"]),
        ]
    )


def main() -> None:
    import uvicorn

    tickets_path = Path(os.environ.get("RESCUE_CREW_DEMO_TICKETS", REPO / DEMO_TICKETS))
    listings_path = Path(os.environ.get("RESCUE_CREW_LISTINGS_CSV", REPO / DEFAULT_LISTINGS))
    port = int(os.environ.get("RESCUE_CREW_DEMO_PORT", "8765"))
    session = DemoSession(tickets_path, listings_path)
    print(f"Rescue Crew demo: http://127.0.0.1:{port}  ({len(session.tickets)} tickets)")
    uvicorn.run(create_app(session), host="127.0.0.1", port=port, log_level="warning")
