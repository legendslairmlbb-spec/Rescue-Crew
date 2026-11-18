"""AirCover Lisbon incident rules, as pure functions.

Every rule here restates docs/policy/aircover-lisbon-rules.md. Nothing in this module may
add a threshold or exception the policy does not contain.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from rescue_crew.data import Listing, Ticket

PRICE_CEILING_FACTOR = Decimal("1.20")  # Policy: "Price ceiling" test
UPLIFT_BUDGET_EUR = Decimal("9000.00")  # Policy: "Uplift budget for this incident"
MIN_REFUND_EUR = Decimal("0.01")  # Policy: "Partial amounts"
CENT = Decimal("0.01")

SafetyCondition = Literal[
    "injury_or_medical_need",
    "threat_or_violence",
    "nowhere_safe_to_wait",
    "unaccompanied_minor",
    "stated_fear_of_person",
]

# Ranking only (Policy: neighbourhood "is not a pass or fail test"). The policy does not list
# which Lisbon neighbourhoods are neighbours; this map is a working assumption for ranking.
NEIGHBOURS: dict[str, set[str]] = {
    "Alfama": {"Graca", "Baixa"},
    "Graca": {"Alfama"},
    "Baixa": {"Alfama", "Chiado"},
    "Chiado": {"Baixa", "Bairro Alto"},
    "Bairro Alto": {"Chiado", "Principe Real"},
    "Principe Real": {"Bairro Alto", "Estrela"},
    "Estrela": {"Principe Real", "Alcantara"},
    "Alcantara": {"Estrela", "Belem"},
    "Belem": {"Alcantara"},
    "Parque das Nacoes": set(),
}


def price_ceiling(ticket: Ticket) -> Decimal:
    return (ticket.nightly_price * PRICE_CEILING_FACTOR).quantize(CENT)


def failed_tests(ticket: Ticket, listing: Listing, live_status: str) -> list[str]:
    """Return the names of the comparable-home tests the listing fails (empty = comparable)."""
    failed = []
    if not (
        listing.available_from <= ticket.check_in_date
        and listing.available_to >= ticket.check_out_date
    ):
        failed.append("dates_covered")
    if listing.max_guests < ticket.party_size:
        failed.append("fits_the_party")
    if listing.bedrooms < ticket.bedrooms:
        failed.append("enough_bedrooms")
    if live_status != "available":
        failed.append("can_be_held_now")
    if listing.nightly_price > price_ceiling(ticket):
        failed.append("price_ceiling")
    return failed


def neighbourhood_rank(ticket: Ticket, listing: Listing) -> int:
    """0 = same neighbourhood, 1 = neighbouring, 2 = elsewhere in Lisbon."""
    if listing.neighborhood == ticket.neighborhood:
        return 0
    if listing.neighborhood in NEIGHBOURS.get(ticket.neighborhood, set()):
        return 1
    return 2


def uplift(ticket: Ticket, listing: Listing) -> Decimal:
    """(rebooked price - original price) x nights, when positive."""
    per_night = listing.nightly_price - ticket.nightly_price
    return max(Decimal(0), per_night * ticket.nights).quantize(CENT)


def refund_problem(ticket: Ticket, amount: Decimal) -> str | None:
    """Return why a refund amount is outside policy, or None if it is allowed."""
    if amount != amount.quantize(CENT):
        return "refund amount must be in whole cents"
    if amount < MIN_REFUND_EUR:
        return "refund amount must be at least EUR 0.01"
    if amount > ticket.total_paid:
        return (
            f"refund EUR {amount} exceeds total_paid EUR {ticket.total_paid}; "
            "no amount above total_paid may be issued, including goodwill additions"
        )
    return None
