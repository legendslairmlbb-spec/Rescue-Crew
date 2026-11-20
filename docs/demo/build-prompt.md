# Build prompt for the support chat window

This is the prompt given to Claude Code to build the demo chat window, kept so that someone
else can rebuild or change it the same way. The only edit is the extract's location, which
was a path on the author's machine and is shown here as a placeholder.

```text
Build a local support chat window for the Rescue Crew demo tonight, then open it in your
browser pane.

What it shows:
- Left: a chat where I paste a guest message (or pick a ticket from the 7 December extract at
  "<path to the 7 December queue extract CSV>"). Default to LIS-TKT-0075.
- Right: a live timeline of the team working the ticket: which agent is running, every tool
  call in order with its status (success / rejected / blocked by safety gate), and the final
  outcome. A blocked call must be clearly visible, not hidden.

How it works:
- Reuse the existing Team, SafetyGate, allowlists and prompts in src/rescue_crew/agents.py. Do
  not write a second agent or change the safety rules to make the demo work.
- Run against a throwaway in-memory server, as in the pilot. Never touch
  reports/lisbon-run-state.jsonl or data/, and assert the state file is unchanged at the end.
- The server only accepts the 16 November exports. Add a demo mode that loads the 7 December
  tickets without breaking that check for the real run. Never load or show expected_outcome.
- Add a "Try the refund anyway" button for 0075 that sends issue_refund through the team, so
  the audience sees the gate block it after the hand-off.
- Key and model come from .env only. Serve on 127.0.0.1, not on the network.

Make it safe to show live:
- Add a replay mode that plays back a recorded run of 0075, in case 9router rate-limits
  during the demo. Record it once now from a real run, and label replays as replays in the UI.
- Guest names stay out of logs and the browser console.

Done means: tests pass (add tests for demo mode and the "refund blocked after hand-off" path),
ruff is clean, the window is open in your browser pane with 0075 run live once and showing
handoff_to_safety_agent → issue_refund [blocked_by_safety_gate], and nothing is committed until
I say so.
```

## Why each part is there

- **Reuse the real team.** A demo that runs different code from the 60-ticket run proves nothing.
- **Throwaway server, state file untouched.** A stray hold or refund during a rehearsal would
  corrupt the real Lisbon results.
- **Demo mode.** Without it the server refuses to start: 0075 is not in the 16 November export.
- **"Try the refund anyway".** 0075 is a refund request with an emergency under it; seeing the
  refund blocked makes the point better than describing it.
- **Replay.** 9router returned 429s during the real run; a demo that stalls is the worst case.
- **No commit until reviewed.** The repo is public.

## Where each requirement landed

| Requirement | Where |
|---|---|
| Same Team, gate, allowlists, prompts | [`agents.py`](../../src/rescue_crew/agents.py): only an observer hook (`on_event`, can watch, cannot change calls) and `Team.attempt()`, which sends one call through the same allowlist and gate |
| Chat + ordered timeline, blocked calls visible | [`demo_page.html`](../../src/rescue_crew/demo_page.html) |
| Throwaway server, state file check, no names / `expected_outcome` | [`demo.py`](../../src/rescue_crew/demo.py) (`DemoSession`, `load_demo_tickets`, `state_untouched`) |
| Demo mode without weakening the real run | `DemoSession` loads the demo tickets with `state_path=None`; the 450-listing check still runs |
| "Try the refund anyway" | `DemoSession.try_refund` → `Team.attempt("refund", "issue_refund", …)` |
| Replay, labelled | `data/demo/replays/<ticket>.json` (git-ignored); header badge reads "REPLAY · recorded …" |
| `.env` only, 127.0.0.1 only | `make_model_factory`; `demo.main()` binds `127.0.0.1` |
| Tests | [`tests/test_demo.py`](../../tests/test_demo.py) |

Added after review:

- `?ticket=…&play=replay&refund=1&fast=1` autoplays a run (used for the screenshot below).
- [`scripts/screenshot.py`](../../scripts/screenshot.py) retakes the screenshot.
- `uv run rescue-crew-demo-run` ([`demo_run.py`](../../src/rescue_crew/demo_run.py)) runs the
  whole 7 December queue and writes
  [`reports/demo-2026-12-07-results.md`](../../reports/demo-2026-12-07-results.md).

## Proof: LIS-TKT-0075

![LIS-TKT-0075 handed to a live safety agent; the refund attempt blocked by the safety gate](lis-tkt-0075-handoff.png)

Row 1 is the only call the team made: `handoff_to_safety_agent` (success). Row 2 comes from the
"Try the refund anyway" button, a deliberate test, and is blocked by the safety gate. No lookup,
search or hold appears before the hand-off.
