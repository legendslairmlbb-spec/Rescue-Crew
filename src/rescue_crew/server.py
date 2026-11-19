"""Rescue Crew MCP server: the six incident tools, backed by the two exports.

Both CSV exports are loaded once, when the server is created. Holds, refunds, host messages
and safety hand-offs are recorded in this process's memory; there is no live Airbnb backend.

Which agent may call which tool is decided by the orchestrator that gives each agent its
tool list (spec FR-007); this server enforces the policy rules on every call it receives.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from rescue_crew import policy
from rescue_crew.data import (
    Listing,
    Ticket,
    check_full_export,
    load_listings,
    load_tickets,
)

DEFAULT_LISTINGS = Path("data/airbnb_lisbon_open_listings_2026-11-16.csv")
DEFAULT_TICKETS = Path("data/airbnb_lisbon_stranded_guest_tickets_2026-11-16.csv")

TicketId = Annotated[str, Field(pattern=r"^LIS-TKT-\d{4}$", description="e.g. LIS-TKT-0002")]
ListingId = Annotated[
    str,
    Field(
        pattern=r"^LST-1\d{5}$",
        description="A listing_id returned by search_open_listings (LST-100001..LST-100450)",
    ),
]

INSTRUCTIONS = """\
Rescue Crew tools for the Lisbon check-in incident of 16 November 2026. Rules come only from
the AirCover policy. Screen every ticket for safety before any other tool call: if the guest
describes injury or medical need, threat or violence, nowhere safe to wait, an unaccompanied
minor, or fear of a person, the only tool to call is handoff_to_safety_agent, even if the guest
asks only for a refund. Anger or figures of speech alone are not a safety condition."""


@dataclass
class IncidentState:
    tickets: dict[str, Ticket]
    listings: dict[str, Listing]
    live_status: dict[str, str] = field(default_factory=dict)
    holds: dict[str, str] = field(default_factory=dict)  # ticket_id -> listing_id
    refunds: dict[str, Decimal] = field(default_factory=dict)  # ticket_id -> amount
    handoffs: dict[str, list[str]] = field(default_factory=dict)  # ticket_id -> conditions
    host_messages: list[dict[str, str]] = field(default_factory=list)
    uplift_spent: Decimal = Decimal("0.00")
    lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        if not self.live_status:
            self.live_status = {lid: x.status for lid, x in self.listings.items()}

    def ticket(self, ticket_id: str) -> Ticket:
        try:
            return self.tickets[ticket_id]
        except KeyError:
            raise ToolError(f"unknown ticket_id {ticket_id}") from None

    def case_status(self, ticket_id: str) -> str:
        if ticket_id in self.handoffs:
            return "handed_to_safety_agent"
        if ticket_id in self.holds:
            return "rebooked"
        if ticket_id in self.refunds:
            return "refunded"
        return "open"

    def require_not_handed_off(self, ticket_id: str) -> None:
        if ticket_id in self.handoffs:
            raise ToolError(
                f"{ticket_id} was handed to a live safety agent; the safety agent decides any "
                "refund, booking or host contact"
            )


def _restore(state: IncidentState, path: Path) -> None:
    """Replay finished tickets from an earlier run so no home or remedy is used twice."""
    from rescue_crew.state import load_state

    for tid, row in load_state(path).items():
        if tid not in state.tickets:
            raise ValueError(f"run state names unknown ticket {tid}")
        lid = row.get("held_listing_id")
        if lid:
            if lid not in state.listings:
                raise ValueError(f"run state: {tid} held {lid}, which is not in the export")
            if lid in state.holds.values():
                raise ValueError(f"run state: {lid} is held by two tickets")
            state.live_status[lid] = "on_hold"
            state.holds[tid] = lid
            state.uplift_spent += policy.uplift(state.tickets[tid], state.listings[lid])
        if row.get("refund_eur"):
            state.refunds[tid] = Decimal(str(row["refund_eur"]))
        if row.get("outcome") == "safety_handoff":
            state.handoffs[tid] = list(row.get("safety_conditions") or [])


def _money(x: Decimal) -> str:
    return str(x.quantize(policy.CENT))


def create_server(
    listings_path: Path = DEFAULT_LISTINGS,
    tickets_path: Path = DEFAULT_TICKETS,
    *,
    require_full_export: bool = True,
    state_path: Path | None = None,
) -> FastMCP:
    """Load both exports (once) and return the server with all six tools registered.

    If ``state_path`` names a run-state file, tickets finished in earlier runs are restored
    first: their held listings are taken, and their refunds and hand-offs are on record.
    """
    listings = load_listings(Path(listings_path))
    if require_full_export:
        check_full_export(listings)
    state = IncidentState(tickets=load_tickets(Path(tickets_path)), listings=listings)
    if state_path is not None:
        _restore(state, Path(state_path))

    mcp = FastMCP("rescue-crew", instructions=INSTRUCTIONS)
    mcp.state = state  # exposed for tests and supervisors

    @mcp.tool
    def lookup_reservation(ticket_id: TicketId) -> dict:
        """Return a stranded guest's reservation and the current state of their case.

        Use it after the ticket has been screened for safety. If the guest's message
        describes any safety condition (injury or medical need, threat or violence, nowhere
        safe to wait, unaccompanied minor, fear of a person), do not call this tool; call
        handoff_to_safety_agent instead.
        """
        t = state.ticket(ticket_id)
        with state.lock:
            status = state.case_status(ticket_id)
            held = state.holds.get(ticket_id)
            refunded = state.refunds.get(ticket_id)
        return {
            "ticket_id": t.ticket_id,
            "reservation_id": t.reservation_id,
            "guest_language": t.guest_language,
            "original_listing_id": t.original_listing_id,
            "neighborhood": t.neighborhood,
            "bedrooms": t.bedrooms,
            "party_size": t.party_size,
            "check_in_date": t.check_in_date.isoformat(),
            "check_out_date": t.check_out_date.isoformat(),
            "nights": t.nights,
            "nightly_price_eur": _money(t.nightly_price),
            "total_paid_eur": _money(t.total_paid),
            "host_id": t.host_id,
            "host_cancelled_at": t.host_cancelled_at or None,
            "host_last_reply_at": t.host_last_reply_at or None,
            "guest_requested": t.guest_requested,
            "guest_message": t.guest_message,
            "case_status": status,
            "held_listing_id": held,
            "refunded_eur": _money(refunded) if refunded is not None else None,
        }

    @mcp.tool
    def search_open_listings(
        ticket_id: TicketId,
        limit: Annotated[int, Field(ge=1, le=20)] = 5,
    ) -> dict:
        """Find open Lisbon homes comparable to the guest's cancelled booking.

        Every result passes all five AirCover comparable-home tests against the ticket:
        available_from <= check_in_date and available_to >= check_out_date with no gap;
        max_guests >= party_size; bedrooms >= the original bedrooms; status is available;
        nightly_price <= 1.20 x the original nightly_price. Results are ranked same
        neighbourhood first, then neighbouring, then elsewhere (neighbourhood is never a
        pass/fail test), then by lowest price. Every listing_id returned comes from the open
        listings export (LST-100001..LST-100450). Offer only these IDs; never an
        original_listing_id (LST-200xxx) and never an ID you composed yourself. An empty
        result means no comparable home exists, and the guest is owed a full refund.
        """
        t = state.ticket(ticket_id)
        with state.lock:
            state.require_not_handed_off(ticket_id)
            passing = [
                x
                for x in state.listings.values()
                if not policy.failed_tests(t, x, state.live_status[x.listing_id])
            ]
        passing.sort(key=lambda x: (policy.neighbourhood_rank(t, x), x.nightly_price, x.listing_id))
        results = []
        for x in passing[:limit]:
            assert x.listing_id in state.listings  # only IDs from the export leave this tool
            results.append(
                {
                    "listing_id": x.listing_id,
                    "neighborhood": x.neighborhood,
                    "bedrooms": x.bedrooms,
                    "max_guests": x.max_guests,
                    "nightly_price_eur": _money(x.nightly_price),
                    "uplift_eur": _money(policy.uplift(t, x)),
                }
            )
        return {
            "ticket_id": ticket_id,
            "price_ceiling_eur": _money(policy.price_ceiling(t)),
            "comparable_count": len(passing),
            "listings": results,
        }

    @mcp.tool
    def hold_booking(ticket_id: TicketId, listing_id: ListingId) -> dict:
        """Hold a comparable home for the guest's whole remaining stay.

        Never use this on a safety ticket before handoff_to_safety_agent: if the guest
        describes injury or medical need, threat or violence, nowhere safe to wait, an
        unaccompanied minor or fear of a person, hand off instead, even if they ask for a
        room. After a hand-off the live safety agent decides any booking.

        The listing_id must come from search_open_listings. The hold covers check_in_date
        to check_out_date and is refused if the listing fails any comparable-home test at
        the moment of the hold (including status no longer available), if it is priced
        above 1.20 x the original nightly price, if the guest was already refunded (one
        remedy per stay) or already holds a home, or if it would exceed the EUR 9,000
        uplift budget.
        """
        t = state.ticket(ticket_id)
        listing = state.listings.get(listing_id)
        if listing is None:
            raise ToolError(
                f"{listing_id} is not in the open listings export; use a listing_id returned "
                "by search_open_listings"
            )
        with state.lock:
            state.require_not_handed_off(ticket_id)
            if ticket_id in state.refunds:
                raise ToolError(f"{ticket_id} was refunded; a refund closes the stay")
            if ticket_id in state.holds:
                raise ToolError(f"{ticket_id} already holds {state.holds[ticket_id]}")
            failed = policy.failed_tests(t, listing, state.live_status[listing_id])
            if failed:
                raise ToolError(f"{listing_id} is not comparable for {ticket_id}: {failed}")
            cost = policy.uplift(t, listing)
            if state.uplift_spent + cost > policy.UPLIFT_BUDGET_EUR:
                raise ToolError(
                    f"uplift EUR {cost} would exceed the EUR 9,000 incident budget; escalate"
                )
            state.live_status[listing_id] = "on_hold"
            state.holds[ticket_id] = listing_id
            state.uplift_spent += cost
            remaining = policy.UPLIFT_BUDGET_EUR - state.uplift_spent
        return {
            "held": True,
            "ticket_id": ticket_id,
            "listing_id": listing_id,
            "check_in_date": t.check_in_date.isoformat(),
            "check_out_date": t.check_out_date.isoformat(),
            "nights": t.nights,
            "nightly_price_eur": _money(listing.nightly_price),
            "uplift_eur": _money(cost),
            "uplift_budget_remaining_eur": _money(remaining),
        }

    @mcp.tool
    def issue_refund(
        ticket_id: TicketId,
        amount_eur: Annotated[Decimal, Field(description="Refund in EUR, e.g. 432.00")],
    ) -> dict:
        """Refund a stranded guest, capped at the ticket's total_paid.

        Never use this on a safety ticket before handoff_to_safety_agent: if the guest
        describes injury or medical need, threat or violence, nowhere safe to wait, an
        unaccompanied minor or fear of a person, hand off instead, even if they ask only
        for money. After a hand-off the live safety agent decides any refund.

        The amount must be from EUR 0.01 up to total_paid; nothing above total_paid is ever
        issued, including goodwill or inconvenience additions. A full refund is total_paid
        as recorded (not nights x nightly price). A refund closes the stay: it is refused if
        the guest already holds a rebooked home or was already refunded.
        """
        t = state.ticket(ticket_id)
        amount = Decimal(amount_eur)
        problem = policy.refund_problem(t, amount)
        if problem:
            raise ToolError(f"{ticket_id}: {problem}")
        with state.lock:
            state.require_not_handed_off(ticket_id)
            if ticket_id in state.holds:
                raise ToolError(
                    f"{ticket_id} is rebooked into {state.holds[ticket_id]}; one remedy per stay"
                )
            if ticket_id in state.refunds:
                raise ToolError(f"{ticket_id} was already refunded; a refund closes the stay")
            state.refunds[ticket_id] = amount
        return {
            "refunded": True,
            "ticket_id": ticket_id,
            "amount_eur": _money(amount),
            "total_paid_eur": _money(t.total_paid),
        }

    @mcp.tool
    def message_host(
        ticket_id: TicketId,
        message: Annotated[str, Field(min_length=1, max_length=1000)],
    ) -> dict:
        """Send the original host one factual message about the reservation's outcome.

        Say whether the guest was rebooked elsewhere or refunded, or that the guest could
        not get in. Do not include the guest's contact details. Never use this on a ticket
        handed to the safety agent; contact with that host is left to the safety agent.
        """
        t = state.ticket(ticket_id)
        with state.lock:
            state.require_not_handed_off(ticket_id)
            state.host_messages.append(
                {"ticket_id": ticket_id, "host_id": t.host_id, "message": message}
            )
        return {"sent": True, "ticket_id": ticket_id, "host_id": t.host_id}

    @mcp.tool
    def handoff_to_safety_agent(
        ticket_id: TicketId,
        conditions: Annotated[list[policy.SafetyCondition], Field(min_length=1)],
        guest_words: Annotated[
            str, Field(min_length=1, max_length=2000, description="The guest's own words")
        ],
    ) -> dict:
        """Hand a safety ticket to a live Trust and Safety agent. Call this first.

        Use it whenever the guest's message describes any of: injury_or_medical_need
        (hurt, unwell, pregnant, needs medication or a doctor), threat_or_violence
        (threatened, followed, shouted at or harmed), nowhere_safe_to_wait (on the street
        at night, phone dying, alone with luggage, nowhere to go), unaccompanied_minor
        (under 18 without an adult), stated_fear_of_person (afraid of the host, a neighbour,
        a stranger or someone in the party). This applies even when the guest asks only for
        a refund, and the guest need not use the word "safety". Anger or figures of speech
        alone ("I am dying out here") are not a condition. On a safety ticket this is the
        only tool to call; after it, Rescue Crew takes no further action on the ticket.
        """
        state.ticket(ticket_id)
        with state.lock:
            already = ticket_id in state.handoffs
            state.handoffs.setdefault(ticket_id, list(dict.fromkeys(conditions)))
        return {
            "handed_off": True,
            "ticket_id": ticket_id,
            "conditions": state.handoffs[ticket_id],
            "already_handed_off": already,
        }

    return mcp


def main() -> None:
    listings = Path(os.environ.get("RESCUE_CREW_LISTINGS_CSV", DEFAULT_LISTINGS))
    tickets = Path(os.environ.get("RESCUE_CREW_TICKETS_CSV", DEFAULT_TICKETS))
    state_file = os.environ.get("RESCUE_CREW_STATE_FILE")
    create_server(listings, tickets, state_path=Path(state_file) if state_file else None).run()
