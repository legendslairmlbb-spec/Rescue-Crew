"""Run the Lisbon tickets through the agent team, resumably, and build the results report.

The six tools come from the Rescue Crew FastMCP server, started once per run over stdio and
loaded with langchain-mcp-adapters. One session is kept open for the whole run.

Runs are resumable through the state file (reports/lisbon-run-state.jsonl):

- each finished ticket gets one row, written only after its last step finishes;
- a run skips every ticket_id already in the file;
- the server is started with the same file, so homes held in earlier runs are taken and
  earlier refunds and hand-offs are on record.

When all tickets have a row, the final report is built from the state file alone.
"""

from __future__ import annotations

import asyncio
import csv
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp.client.stdio import get_default_environment

from rescue_crew.agents import Team, TicketResult, make_model_factory
from rescue_crew.server import DEFAULT_TICKETS
from rescue_crew.state import DEFAULT_STATE, STATE_VAR, append_row, load_state

REPO = Path(__file__).resolve().parents[2]
STATE_FILE = REPO / DEFAULT_STATE
REPORT_FILE = REPO / "reports" / "lisbon-results.md"
EXPECTED = {"safety": "safety_handoff", "rebooking": "rebooked", "refund": "refunded"}
AGENT_FIELDS = ("ticket_id", "guest_requested", "guest_message", "total_paid")
STOP_AFTER_FAILURES = 3  # consecutive errored tickets, e.g. the daily model limit is used up


def load_tickets(path: Path) -> tuple[list[dict[str, str]], dict[str, str]]:
    """Return (ticket inputs for agents, expected outcomes kept apart for scoring only)."""
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    tickets = [{k: r[k] for k in AGENT_FIELDS} for r in rows]
    expected = {r["ticket_id"]: r.get("expected_outcome", "") for r in rows}
    return tickets, expected


def call_summary(call: dict[str, Any]) -> str:
    args, tool = call.get("args") or {}, call["tool"]
    detail = ""
    if tool == "hold_booking":
        detail = args.get("listing_id", "")
    elif tool == "issue_refund":
        detail = f"EUR {args.get('amount_eur', '')}"
    elif tool == "handoff_to_safety_agent":
        detail = ", ".join(args.get("conditions", []))
    text = f"{tool}({detail})" if detail else tool
    return text if call["status"] == "success" else f"{text} [{call['status']}]"


def to_row(result: TicketResult) -> dict[str, Any]:
    calls = [
        {"agent": c.agent, "tool": c.tool, "args": c.args, "status": c.status}
        for c in result.tool_calls
    ]
    return {
        "ticket_id": result.ticket_id,
        "outcome": result.outcome,
        "tool_calls": calls,
        "tool_call_order": [call_summary(c) for c in calls],
        "held_listing_id": result.held_listing_id,
        "refund_eur": result.refund_eur,
        "safety_conditions": result.safety_conditions,
        "host_messaged": result.host_messaged,
        "notes": result.notes,
        "model_calls": result.model_calls,
        "models_used": result.models_used,
    }


def build_report(
    rows: dict[str, dict[str, Any]],
    expected: dict[str, str],
    ticket_order: list[str],
    path: Path = REPORT_FILE,
) -> Path:
    """Write the results report from the state file's rows only."""
    done = [rows[t] for t in ticket_order if t in rows]
    missing = [t for t in ticket_order if t not in rows]
    counts: dict[str, int] = {}
    for r in done:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
    matched = sum(1 for r in done if EXPECTED.get(expected.get(r["ticket_id"], "")) == r["outcome"])
    safety_ids = {t for t, e in expected.items() if e == "safety"}
    safety_rows = [r for r in done if r["ticket_id"] in safety_ids]
    money_on_safety = [
        r["ticket_id"]
        for r in safety_rows
        if any(
            c["tool"] in {"hold_booking", "issue_refund"} and c["status"] == "success"
            for c in r["tool_calls"]
        )
    ]
    held = [r["held_listing_id"] for r in done if r.get("held_listing_id")]
    refunded = sum(float(r["refund_eur"]) for r in done if r.get("refund_eur"))
    not_messaged = [
        r["ticket_id"]
        for r in done
        if r["outcome"] in {"rebooked", "refunded"} and not r.get("host_messaged")
    ]
    models = sorted({m for r in done for m in r.get("models_used", [])})
    status = (
        "complete"
        if not missing
        else f"PARTIAL: {len(missing)} of {len(ticket_order)} tickets not finished yet"
    )

    lines = [
        "# Lisbon incident: Rescue Crew results",
        "",
        (
            f"Built from `{DEFAULT_STATE.as_posix()}` ({len(done)} finished tickets; {status}). "
            "Agents followed `specs/001-lisbon-rescue-crew`; tools came from the Rescue Crew MCP "
            "server via langchain-mcp-adapters."
        ),
        "",
        "## Summary",
        "",
        "| Outcome | Tickets |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in sorted(counts.items())],
        "",
        (
            f"- Matches `expected_outcome` (scoring only, never shown to agents): "
            f"**{matched}/{len(done)}**"
        ),
        (
            f"- Safety tickets handed off: "
            f"{sum(1 for r in safety_rows if r['outcome'] == 'safety_handoff')}/{len(safety_rows)}; "
            f"successful refund or hold on a safety ticket: {len(money_on_safety)}"
        ),
        (
            f"- Homes held: {len(held)} ({len(set(held))} distinct listings); "
            f"refunded in total: EUR {refunded:.2f}"
        ),
        f"- Resolved tickets whose host was not messaged: {', '.join(not_messaged) or 'none'}",
        f"- Model calls: {sum(r.get('model_calls', 0) for r in done)}; models that answered: "
        + (", ".join(f"`{m}`" for m in models) or "none"),
        "",
        "## Tickets",
        "",
        (
            "Tool calls are in the order they were called. A status in brackets means the call did "
            "not succeed (refused by the server, rejected by an allowlist, or blocked by the safety "
            "gate). ✗ marks an outcome that differs from `expected_outcome`."
        ),
        "",
        "| ticket_id | outcome | expected | tool calls (in order) | listing held | refund | notes |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in done:
        exp = expected.get(r["ticket_id"], "")
        mark = "" if EXPECTED.get(exp) == r["outcome"] else " ✗"
        calls = " → ".join(r["tool_call_order"]) or "(none)"
        refund = f"EUR {r['refund_eur']}" if r.get("refund_eur") else ""
        notes = "; ".join(r.get("notes", [])).replace("|", "/")
        lines.append(
            f"| {r['ticket_id']} | {r['outcome']}{mark} | {exp} | {calls} | "
            f"{r.get('held_listing_id') or ''} | {refund} | {notes} |"
        )
    if missing:
        lines += ["", "## Not finished yet", "", ", ".join(missing)]
    lines += [
        "",
        "## Totals",
        "",
        "| Rebooked | Refunded | Safety hand-offs |",
        "|---|---|---|",
        (
            f"| {counts.get('rebooked', 0)} | {counts.get('refunded', 0)} | "
            f"{counts.get('safety_handoff', 0)} |"
        ),
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


async def run(
    tickets_path: Path = DEFAULT_TICKETS,
    state_file: Path = STATE_FILE,
    limit: int | None = None,
) -> list[TicketResult]:
    tickets, expected = load_tickets(REPO / tickets_path)
    order = [t["ticket_id"] for t in tickets]
    finished = load_state(state_file)
    todo = [t for t in tickets if t["ticket_id"] not in finished]
    print(f"{len(finished)}/{len(tickets)} tickets already finished; {len(todo)} to run.")
    if limit:
        todo = todo[:limit]

    results: list[TicketResult] = []
    if todo:
        env = {**get_default_environment(), STATE_VAR: str(state_file)}
        client = MultiServerMCPClient(
            {
                "rescue-crew": {
                    "transport": "stdio",
                    "command": sys.executable,
                    "args": ["-c", "from rescue_crew.server import main; main()"],
                    "cwd": str(REPO),
                    "env": env,
                }
            }
        )
        failures = 0
        async with client.session("rescue-crew") as session:
            tools = await load_mcp_tools(session)
            team = Team(tools, make_model_factory(str(REPO / ".env")))
            for i, ticket in enumerate(todo, 1):
                r = await team.run_ticket(ticket)
                results.append(r)
                calls = " → ".join(call_summary(asdict(c)) for c in r.tool_calls)
                if r.finished:
                    append_row(state_file, to_row(r))  # only after the ticket's last step
                    failures = 0
                    print(f"[{i:>2}/{len(todo)}] {r.ticket_id} {r.outcome:<15} {calls}", flush=True)
                else:
                    failures += 1
                    print(
                        f"[{i:>2}/{len(todo)}] {r.ticket_id} NOT FINISHED ({r.error})", flush=True
                    )
                    if failures >= STOP_AFTER_FAILURES:
                        print(f"Stopping: {failures} tickets in a row failed. Run again later.")
                        break

    finished = load_state(state_file)
    remaining = [t for t in order if t not in finished]
    if remaining:
        print(f"\n{len(finished)}/{len(order)} finished. {len(remaining)} left for the next run.")
    else:
        path = build_report(finished, expected, order)
        print(f"\nAll {len(order)} tickets finished. Report: {path.relative_to(REPO)}")
    return results


def _utf8_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles: cp1252


def main() -> None:
    _utf8_stdout()
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    asyncio.run(run(limit=limit))


def report_main() -> None:
    """Build the report from the state file now (marked PARTIAL if tickets are missing)."""
    _utf8_stdout()
    tickets, expected = load_tickets(REPO / DEFAULT_TICKETS)
    path = build_report(load_state(STATE_FILE), expected, [t["ticket_id"] for t in tickets])
    print(f"Report: {path.relative_to(REPO)}")
