"""Run state shared between runs: one JSON line per finished ticket.

A row is appended only after a ticket's last step has finished, so a run that dies halfway
leaves no row for the ticket it was working on, and the next run redoes that ticket cleanly.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

STATE_VAR = "RESCUE_CREW_STATE_FILE"
DEFAULT_STATE = Path("reports/lisbon-run-state.jsonl")


def load_state(path: Path) -> dict[str, dict[str, Any]]:
    """Return finished tickets by ticket_id. A missing file means nothing has finished yet."""
    rows: dict[str, dict[str, Any]] = {}
    if not path.is_file():
        return rows
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as e:
            raise ValueError(f"{path} line {n} is not valid JSON: {e}") from e
        if row["ticket_id"] in rows:
            raise ValueError(f"{path} line {n}: {row['ticket_id']} appears twice")
        rows[row["ticket_id"]] = row
    return rows


def append_row(path: Path, row: dict[str, Any]) -> None:
    """Append one finished ticket and flush it to disk before returning."""
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {**row, "finished_at": row.get("finished_at") or datetime.now(UTC).isoformat()}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def held_listings(rows: dict[str, dict[str, Any]]) -> dict[str, str]:
    """ticket_id -> listing_id for every ticket whose home was held in an earlier run."""
    return {t: r["held_listing_id"] for t, r in rows.items() if r.get("held_listing_id")}
