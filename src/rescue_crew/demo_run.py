"""Run every ticket in the demo queue through the chat window's team and write a results table.

Same Team, SafetyGate, allowlists and prompts as the window and the 60-ticket run. One
throwaway in-memory server is shared by the whole queue, so a home held for one ticket is
taken for the next. No run-state file is read or written. ``expected_outcome`` is read
separately and used only to score the table; the agents never see it, and guest names are
never loaded.

The team's choice is scored on its own ("what the team went for"), apart from the final
outcome, because the 16 November listings export has no home open in December: a December
rebooking ticket that is routed correctly can still end as a refund when no comparable home
exists, as the policy requires.
"""

from __future__ import annotations

import asyncio
import csv
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastmcp import Client
from langchain_mcp_adapters.tools import load_mcp_tools

from rescue_crew.agents import Team, TicketResult, make_model_factory
from rescue_crew.demo import AGENT_FIELDS, DEMO_TICKETS, REPO, file_digest
from rescue_crew.run import EXPECTED, _utf8_stdout, call_summary
from rescue_crew.server import DEFAULT_LISTINGS, create_server
from rescue_crew.state import DEFAULT_STATE

REPORT = Path("reports/demo-2026-12-07-results.md")


def load_queue(path: Path) -> tuple[list[dict[str, str]], dict[str, str]]:
    """(agent inputs, expected outcomes for scoring only). Guest names are not read."""
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return (
        [{k: r[k] for k in AGENT_FIELDS} for r in rows],
        {r["ticket_id"]: r.get("expected_outcome", "") for r in rows},
    )


def went_for(r: TicketResult) -> str:
    """What the team went for: safety, rebooking, refund, or none."""
    if r.outcome == "safety_handoff":
        return "safety"
    agents = [c.agent for c in r.tool_calls]
    if "rebooking" in agents:
        return "rebooking"
    if "refund" in agents:
        return "refund"
    return "none"


def build_table(
    results: list[TicketResult],
    tickets: list[dict[str, str]],
    expected: dict[str, str],
    state_unchanged: bool,
    source: str,
) -> str:
    asked = {t["ticket_id"]: t["guest_requested"] for t in tickets}
    rows: list[str] = []
    right_choice = right_outcome = safety_ok = 0
    safety_ids = {t for t, e in expected.items() if e == "safety"}
    money_on_safety = []
    for r in results:
        exp = expected.get(r.ticket_id, "")
        choice = went_for(r)
        ok_choice = choice == exp
        ok_outcome = EXPECTED.get(exp) == r.outcome
        right_choice += ok_choice
        right_outcome += ok_outcome
        if r.ticket_id in safety_ids:
            safety_ok += r.outcome == "safety_handoff"
            if any(
                c.tool in {"hold_booking", "issue_refund"} and c.status == "success"
                for c in r.tool_calls
            ):
                money_on_safety.append(r.ticket_id)
        calls = " → ".join(call_summary(asdict(c)) for c in r.tool_calls) or "(none)"
        hidden = " ⚑" if asked[r.ticket_id] != exp else ""
        notes = "; ".join(r.notes).replace("|", "/")
        rows.append(
            f"| {r.ticket_id} | {asked[r.ticket_id]} | {exp}{hidden} | "
            f"{choice} {'✓' if ok_choice else '✗'} | {r.outcome} {'✓' if ok_outcome else '✗'} | "
            f"{calls} | {notes} |"
        )
    n = len(results)
    counts: dict[str, int] = {}
    for r in results:
        counts[r.outcome] = counts.get(r.outcome, 0) + 1
    lines = [
        "# 7 December queue: Rescue Crew results",
        "",
        (
            f"All {n} tickets from `{source}` run through the chat window's team (same Team, "
            "SafetyGate, allowlists and prompts as the 60-ticket run) on one throwaway "
            "in-memory server. Built by `uv run rescue-crew-demo-run`."
        ),
        "",
        "## Summary",
        "",
        f"- Team went for the right thing (safety / rebooking / refund): **{right_choice}/{n}**",
        f"- Final outcome matches `expected_outcome`: **{right_outcome}/{n}**",
        (
            f"- Safety tickets handed to a human: {safety_ok}/{len(safety_ids)}; successful "
            f"refund or hold on a safety ticket: {len(money_on_safety)}"
        ),
        (
            "- `reports/lisbon-run-state.jsonl` unchanged by this run: "
            + ("yes" if state_unchanged else "**NO**")
        ),
        "",
        (
            "Why the two scores differ: the listings export is from 16 November and no home in "
            "it is open in December, so every December rebooking ticket finds no comparable home "
            "and, as the policy requires, falls back to a full refund. The first score checks "
            "the team's decision; the second checks the final outcome against the extract's "
            "`expected_outcome`."
        ),
        "",
        "## Tickets",
        "",
        (
            "⚑ marks a ticket whose `guest_requested` differs from what it needs. Tool calls are "
            "in the order they were called; a status in brackets means the call did not succeed."
        ),
        "",
        "| ticket_id | asks for | needs | team went for | outcome | tool calls (in order) | notes |",
        "|---|---|---|---|---|---|---|",
        *rows,
        "",
        "## Totals",
        "",
        "| Rebooked | Refunded | Safety hand-offs | Needs human |",
        "|---|---|---|---|",
        (
            f"| {counts.get('rebooked', 0)} | {counts.get('refunded', 0)} | "
            f"{counts.get('safety_handoff', 0)} | {counts.get('needs_human', 0)} |"
        ),
    ]
    return "\n".join(lines) + "\n"


async def run_queue(
    tickets_path: Path,
    listings_path: Path = DEFAULT_LISTINGS,
    model_factory: Any = None,
    require_full_export: bool = True,
) -> list[TicketResult]:
    tickets, _ = load_queue(tickets_path)
    server = create_server(
        listings_path, tickets_path, require_full_export=require_full_export, state_path=None
    )
    factory = model_factory or make_model_factory(str(REPO / ".env"))
    results = []
    async with Client(server) as client:
        team = Team(await load_mcp_tools(client.session), factory)
        for i, t in enumerate(tickets, 1):
            r = await team.run_ticket(t)
            results.append(r)
            calls = " → ".join(call_summary(asdict(c)) for c in r.tool_calls)
            print(f"[{i:>2}/{len(tickets)}] {r.ticket_id} {r.outcome:<15} {calls}", flush=True)
    return results


def main() -> None:
    _utf8_stdout()
    tickets_path = REPO / DEMO_TICKETS
    if len(sys.argv) > 1:
        tickets_path = Path(sys.argv[1])
    state_file = REPO / DEFAULT_STATE
    before = file_digest(state_file)
    results = asyncio.run(run_queue(tickets_path, REPO / DEFAULT_LISTINGS))
    tickets, expected = load_queue(tickets_path)
    text = build_table(
        results,
        tickets,
        expected,
        file_digest(state_file) == before,
        "data/demo/stranded_guest_tickets_2026-12-07.csv",
    )
    out = REPO / REPORT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"\nReport: {REPORT.as_posix()}")
