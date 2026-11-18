"""Load and validate the two incident exports once, at server start.

If either file does not look like the export the AirCover policy describes, loading fails
and the server does not start. A server that cannot trust its listing IDs must not answer.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

LISTING_ID_RE = re.compile(r"^LST-1\d{5}$")
FIRST_LISTING_ID = "LST-100001"
LAST_LISTING_ID = "LST-100450"
EXPECTED_LISTING_COUNT = 450

LISTING_COLUMNS = {
    "listing_id",
    "neighborhood",
    "bedrooms",
    "max_guests",
    "nightly_price",
    "available_from",
    "available_to",
    "status",
}
TICKET_COLUMNS = {
    "ticket_id",
    "reservation_id",
    "guest_language",
    "original_listing_id",
    "neighborhood",
    "bedrooms",
    "party_size",
    "check_in_date",
    "check_out_date",
    "nightly_price",
    "total_paid",
    "host_id",
    "host_cancelled_at",
    "host_last_reply_at",
    "guest_requested",
    "guest_message",
}
LISTING_STATUSES = {"available", "on_hold", "booked"}


class DataError(ValueError):
    """An export is missing, malformed, or does not match the policy."""


@dataclass(frozen=True)
class Listing:
    listing_id: str
    host_id: str
    neighborhood: str
    title: str
    bedrooms: int
    max_guests: int
    nightly_price: Decimal
    available_from: date
    available_to: date
    status: str  # status in the export snapshot; live status is tracked by the server


@dataclass(frozen=True)
class Ticket:
    ticket_id: str
    reservation_id: str
    guest_name: str
    guest_language: str
    original_listing_id: str
    neighborhood: str
    bedrooms: int
    party_size: int
    check_in_date: date
    check_out_date: date
    nightly_price: Decimal
    total_paid: Decimal
    host_id: str
    host_cancelled_at: str
    host_last_reply_at: str
    guest_requested: str
    guest_message: str

    @property
    def nights(self) -> int:
        return (self.check_out_date - self.check_in_date).days


def _read_rows(path: Path, required: set[str], label: str) -> list[dict[str, str]]:
    if not path.is_file():
        raise DataError(f"{label} file not found: {path}")
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        header = set(reader.fieldnames or [])
        missing = required - header
        if missing:
            raise DataError(
                f"{label} line 1 must be the column headers; missing {sorted(missing)} in {path}"
            )
        return list(reader)


def load_listings(path: Path) -> dict[str, Listing]:
    rows = _read_rows(path, LISTING_COLUMNS, "Open listings")
    listings: dict[str, Listing] = {}
    for n, row in enumerate(rows, start=2):
        lid = row["listing_id"].strip()
        if not LISTING_ID_RE.match(lid) or not FIRST_LISTING_ID <= lid <= LAST_LISTING_ID:
            raise DataError(f"line {n}: listing_id {lid!r} is outside LST-100001..LST-100450")
        if lid in listings:
            raise DataError(f"line {n}: duplicate listing_id {lid}")
        status = row["status"].strip()
        if status not in LISTING_STATUSES:
            raise DataError(f"line {n}: unknown status {status!r} for {lid}")
        try:
            listings[lid] = Listing(
                listing_id=lid,
                host_id=row.get("host_id", "").strip(),
                neighborhood=row["neighborhood"].strip(),
                title=row.get("title", "").strip(),
                bedrooms=int(row["bedrooms"]),
                max_guests=int(row["max_guests"]),
                nightly_price=Decimal(row["nightly_price"]),
                available_from=date.fromisoformat(row["available_from"]),
                available_to=date.fromisoformat(row["available_to"]),
                status=status,
            )
        except (ValueError, ArithmeticError) as e:
            raise DataError(f"line {n}: bad value for {lid}: {e}") from e
    return listings


def load_tickets(path: Path) -> dict[str, Ticket]:
    rows = _read_rows(path, TICKET_COLUMNS, "Tickets")
    tickets: dict[str, Ticket] = {}
    for n, row in enumerate(rows, start=2):
        tid = row["ticket_id"].strip()
        if tid in tickets:
            raise DataError(f"line {n}: duplicate ticket_id {tid}")
        try:
            tickets[tid] = Ticket(
                ticket_id=tid,
                reservation_id=row["reservation_id"].strip(),
                guest_name=row.get("guest_name", "").strip(),
                guest_language=row["guest_language"].strip(),
                original_listing_id=row["original_listing_id"].strip(),
                neighborhood=row["neighborhood"].strip(),
                bedrooms=int(row["bedrooms"]),
                party_size=int(row["party_size"]),
                check_in_date=date.fromisoformat(row["check_in_date"]),
                check_out_date=date.fromisoformat(row["check_out_date"]),
                nightly_price=Decimal(row["nightly_price"]),
                total_paid=Decimal(row["total_paid"]),
                host_id=row["host_id"].strip(),
                host_cancelled_at=row["host_cancelled_at"].strip(),
                host_last_reply_at=row["host_last_reply_at"].strip(),
                guest_requested=row["guest_requested"].strip(),
                guest_message=row["guest_message"].strip(),
            )
        except (ValueError, ArithmeticError) as e:
            raise DataError(f"line {n}: bad value for {tid}: {e}") from e
        # expected_outcome, if present, is test data and is deliberately never loaded.
    return tickets


def check_full_export(listings: dict[str, Listing]) -> None:
    """The real incident export must hold exactly LST-100001..LST-100450."""
    if len(listings) != EXPECTED_LISTING_COUNT:
        raise DataError(
            f"open listings export has {len(listings)} listings, expected {EXPECTED_LISTING_COUNT}"
        )
