"""The Rescue Crew agent team (spec 001-lisbon-rescue-crew).

A supervisor (plain code, no tools) runs each ticket through LLM agents that use the six MCP
tools loaded with langchain-mcp-adapters:

    triage ──safety──▶ handoff_to_safety_agent (ticket closed)
       │
       └─clear──▶ rebooking (or refund) ──▶ host messaging

Two rules are enforced here in code, not only in prompts:

- Tool allowlists (FR-007/FR-008): each agent may call only its own tools; any other call is
  rejected and recorded.
- Safety gate (FR-002/FR-010): no tool except handoff_to_safety_agent runs on a ticket until
  triage has cleared it, and nothing at all runs after a hand-off. Every tool call must also
  name the ticket being worked on.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool

from rescue_crew.llm import settings

ALLOWLIST: dict[str, set[str]] = {
    # Spec FR-007 lets triage use lookup_reservation too; triage reads the ticket it is given
    # and never needs it, so it gets only the hand-off (fewer tools, nothing to misuse).
    "triage": {"handoff_to_safety_agent"},
    "rebooking": {"lookup_reservation", "search_open_listings", "hold_booking"},
    "refund": {"lookup_reservation", "issue_refund"},
    "host_messaging": {"lookup_reservation", "message_host"},
}
MONEY_AND_BOOKING_TOOLS = {"hold_booking", "issue_refund"}

TRIAGE_PROMPT = """\
You are the triage agent for stranded Airbnb guests in Lisbon on 16 November 2026.
Read the guest's message and decide ONLY whether it describes a safety condition:
- injury_or_medical_need: someone is hurt, unwell, pregnant, needs medication or a doctor
- threat_or_violence: someone has threatened, followed, shouted at or harmed them
- nowhere_safe_to_wait: out on the street at night, phone dying, alone with luggage, nowhere to go
- unaccompanied_minor: a guest under 18 travelling or waiting without an adult
- stated_fear_of_person: afraid of the host, a neighbour, a stranger or someone in the party
A safety condition wins over whatever the guest asked for, including a refund. The guest does
not need to say "safety". Anger, frustration, urgency or figures of speech alone ("I am dying out
here", "worst day of our lives", "before we all lose it") are NOT safety conditions.

If any condition is described: call handoff_to_safety_agent with the ticket_id, every
condition that applies, and the guest's own words. Call no other tool.
If none is described: do not call any tool; reply with exactly the word CLEAR."""

REBOOKING_PROMPT = """\
You are the rebooking agent. Find and hold a comparable home for the guest's whole stay.
1. Call search_open_listings with the ticket_id.
2. Call hold_booking with the ticket_id and the FIRST listing_id from the results.
   If that hold is refused, try the next listing_id from the same results.
Only use listing_id values returned by search_open_listings. Never invent one, and never use the
guest's original listing (LST-200xxx). If the search returns no listings, call no further tool
and reply with exactly NO_COMPARABLE."""

REFUND_PROMPT = """\
You are the refund agent. Call issue_refund once with the ticket_id and amount_eur equal to the
ticket's total_paid exactly as given. Never add goodwill or extra amounts."""

HOST_PROMPT = """\
You are the host messaging agent. Call message_host once with the ticket_id and one short,
factual message telling the original host what happened to this reservation. Do not include the
guest's name or contact details."""


@dataclass
class ToolCallRecord:
    agent: str
    tool: str
    args: dict[str, Any]
    status: str  # success | error | rejected_not_allowed | blocked_by_safety_gate | ...
    result: str


@dataclass
class TicketResult:
    ticket_id: str
    outcome: str = "needs_human"  # safety_handoff | rebooked | refunded | needs_human
    route: str | None = None  # rebooking | refund (after triage clears the ticket)
    safety_conditions: list[str] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    model_calls: int = 0
    models_used: list[str] = field(default_factory=list)
    host_messaged: bool = False
    error: str | None = None  # set when a model or tool call raised before the ticket resolved

    @property
    def finished(self) -> bool:
        """True when the ticket reached a final outcome and should not be run again.

        A remedy that went through (hand-off, hold or refund) is final even if the host message
        afterwards failed. A ticket that stopped on an error before resolving is not: the next
        run redoes it from the start.
        """
        if self.outcome in {"safety_handoff", "rebooked", "refunded"}:
            return True
        return self.outcome == "needs_human" and self.error is None

    @property
    def held_listing_id(self) -> str | None:
        return next(
            (
                c.args.get("listing_id")
                for c in self.tool_calls
                if c.tool == "hold_booking" and c.status == "success"
            ),
            None,
        )

    @property
    def refund_eur(self) -> str | None:
        return next(
            (
                str(c.args.get("amount_eur"))
                for c in self.tool_calls
                if c.tool == "issue_refund" and c.status == "success"
            ),
            None,
        )


class SafetyGate:
    """Per-ticket state that decides which tools may run (spec FR-002, FR-010, FR-012)."""

    def __init__(self) -> None:
        self._verdict: dict[str, str] = {}  # ticket_id -> "clear" | "safety"

    def clear(self, ticket_id: str) -> None:
        self._verdict[ticket_id] = "clear"

    def mark_safety(self, ticket_id: str) -> None:
        self._verdict[ticket_id] = "safety"

    def check(self, ticket_id: str, tool: str) -> str | None:
        """Return a refusal reason, or None when the tool may run on this ticket."""
        verdict = self._verdict.get(ticket_id)
        if verdict == "safety":
            return "ticket was handed to a live safety agent; Rescue Crew takes no further action"
        if tool == "handoff_to_safety_agent":
            return None
        if verdict != "clear":
            what = "money or booking" if tool in MONEY_AND_BOOKING_TOOLS else "other"
            return f"safety screening has not cleared this ticket; no {what} tool may run yet"
        return None


def make_model_factory(env_file: str = ".env") -> Callable[[list[BaseTool]], Any]:
    """Build chat models from .env: endpoint, key and model names never live in code."""
    from langchain_openai import ChatOpenAI

    cfg = settings(env_file)
    primary, fallbacks = cfg.models[0], cfg.models[1:]

    def chat(model: str) -> ChatOpenAI:
        return ChatOpenAI(
            model=model,
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            temperature=0,
            timeout=120,
            max_retries=4,  # backs off on 429s, honouring Retry-After
            default_headers={"X-Title": "Rescue Crew"},
            # Some OpenAI-compatible routers stream unless told not to.
            extra_body={"stream": False},
        )

    def factory(tools: list[BaseTool]) -> Any:
        bound = chat(primary).bind_tools(tools)
        backups = [chat(m).bind_tools(tools) for m in fallbacks if m != primary]
        return bound.with_fallbacks(backups) if backups else bound

    return factory


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
    return str(content)


class Team:
    def __init__(self, tools: list[BaseTool], model_factory: Callable[[list[BaseTool]], Any]):
        self.tools = {t.name: t for t in tools}
        missing = set().union(*ALLOWLIST.values()) - set(self.tools)
        if missing:
            raise RuntimeError(f"MCP server is missing tools: {sorted(missing)}")
        self.model_factory = model_factory
        self.gate = SafetyGate()
        self._models = {
            agent: model_factory([self.tools[n] for n in sorted(names)])
            for agent, names in ALLOWLIST.items()
        }

    async def _run_agent(
        self,
        agent: str,
        system: str,
        user: str,
        result: TicketResult,
        terminal: set[str],
        max_steps: int,
    ) -> tuple[str, str | None, Any]:
        """Run one agent. Returns (final_text, terminal_tool_that_succeeded, its_result)."""
        model = self._models[agent]
        messages: list = [SystemMessage(system), HumanMessage(user)]
        for _ in range(max_steps):
            result.model_calls += 1
            ai: AIMessage = await model.ainvoke(messages)
            used = (ai.response_metadata or {}).get("model_name")
            if used and used not in result.models_used:
                result.models_used.append(used)
            messages.append(ai)
            if not ai.tool_calls:
                return _text(ai.content).strip(), None, None
            for call in ai.tool_calls:
                name, args = call["name"], dict(call.get("args") or {})
                status, content, data = await self._execute(agent, name, args, call, result)
                messages.append(ToolMessage(content, tool_call_id=call["id"], name=name))
                if status == "success" and name in terminal:
                    return "", name, data
        result.notes.append(f"{agent}: stopped after {max_steps} model calls")
        return "", None, None

    async def _execute(self, agent, name, args, call, result) -> tuple[str, str, Any]:
        """Run one tool call through the allowlist and safety gate, and record it."""

        def record(status: str, content: str) -> None:
            result.tool_calls.append(ToolCallRecord(agent, name, args, status, content[:300]))

        if name not in ALLOWLIST[agent] or name not in self.tools:
            msg = f"REJECTED: {agent} agent is not allowed to call {name}"
            record("rejected_not_allowed", msg)
            return "rejected_not_allowed", msg, None
        if args.get("ticket_id") != result.ticket_id:
            msg = f"REJECTED: tool call must use ticket_id {result.ticket_id}"
            record("rejected_wrong_ticket", msg)
            return "rejected_wrong_ticket", msg, None
        refusal = self.gate.check(result.ticket_id, name)
        if refusal:
            msg = f"BLOCKED by safety gate: {refusal}"
            record("blocked_by_safety_gate", msg)
            return "blocked_by_safety_gate", msg, None

        out: ToolMessage = await self.tools[name].ainvoke(
            {"name": name, "args": args, "id": call["id"], "type": "tool_call"}
        )
        content = _text(out.content)
        status = "error" if getattr(out, "status", "success") == "error" else "success"
        record(status, content)
        data = None
        if status == "success":
            try:
                data = json.loads(content)
            except ValueError:
                data = None
        return status, content, data

    async def run_ticket(self, ticket: dict[str, str]) -> TicketResult:
        tid = ticket["ticket_id"]
        result = TicketResult(ticket_id=tid)
        try:
            await self._handle(ticket, result)
        except Exception as e:  # noqa: BLE001 - one failed ticket must not stop the run
            message = f"{type(e).__name__}: {str(e)[:200]}"
            if result.outcome in {"safety_handoff", "rebooked", "refunded"}:
                # The remedy already went through; a later failure (e.g. the host message)
                # must not erase it.
                result.notes.append(f"after {result.outcome}: {message}")
            else:
                result.outcome = "needs_human"
                result.error = message
                result.notes.append(f"error: {message}")
        return result

    async def _handle(self, ticket: dict[str, str], result: TicketResult) -> None:
        tid = ticket["ticket_id"]

        # 1. Triage: safety first, from guest_message, before any other tool can run.
        triage_input = (
            f"ticket_id: {tid}\nguest_requested: {ticket['guest_requested']}\n"
            f"guest_message: {ticket['guest_message']}"
        )
        text, done, data = await self._run_agent(
            "triage",
            TRIAGE_PROMPT,
            triage_input,
            result,
            terminal={"handoff_to_safety_agent"},
            max_steps=2,
        )
        if done == "handoff_to_safety_agent":
            self.gate.mark_safety(tid)
            result.outcome = "safety_handoff"
            result.safety_conditions = list((data or {}).get("conditions", []))
            return
        if not re.fullmatch(r"\W*CLEAR\W*", text, flags=re.IGNORECASE):
            result.notes.append(f"triage gave no clear verdict: {text[:120]!r}; escalated")
            return  # FR-030: not cleared means no money or booking action, a human decides
        self.gate.clear(tid)

        # 2. Route (FR-005): refund if the guest asked for one, otherwise rebooking.
        result.route = "refund" if ticket["guest_requested"] == "refund" else "rebooking"
        if ticket["guest_requested"] in {"callback", "other"}:
            result.notes.append(
                f"guest_requested={ticket['guest_requested']}: flagged for a human supervisor"
            )

        if result.route == "rebooking":
            text, done, data = await self._run_agent(
                "rebooking",
                REBOOKING_PROMPT,
                f"ticket_id: {tid}",
                result,
                terminal={"hold_booking"},
                max_steps=5,
            )
            if done == "hold_booking":
                result.outcome = "rebooked"
            elif "NO_COMPARABLE" in text.upper():
                result.notes.append("no comparable home: owed a full refund (FR-021)")
                result.route = "refund"
            else:
                result.notes.append(f"rebooking did not complete: {text[:120]!r}; escalated")
                return

        if result.route == "refund":
            text, done, data = await self._run_agent(
                "refund",
                REFUND_PROMPT,
                f"ticket_id: {tid}\ntotal_paid_eur: {ticket['total_paid']}",
                result,
                terminal={"issue_refund"},
                max_steps=3,
            )
            if done != "issue_refund":
                result.notes.append(f"refund did not complete: {text[:120]!r}; escalated")
                return
            result.outcome = "refunded"

        # 3. Host messaging (FR-026), only once the ticket is resolved.
        summary = (
            "The guest could not check in and has been moved to another home."
            if result.outcome == "rebooked"
            else "The guest could not check in and has been refunded."
        )
        text, done, _ = await self._run_agent(
            "host_messaging",
            HOST_PROMPT,
            f"ticket_id: {tid}\noutcome: {summary}",
            result,
            terminal={"message_host"},
            max_steps=3,
        )
        if done == "message_host":
            result.host_messaged = True
        else:
            result.notes.append("host was not messaged")
