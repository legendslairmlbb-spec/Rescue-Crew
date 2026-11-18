"""Rescue Crew: MCP tools for the Lisbon check-in incident of 16 November 2026."""


def main() -> None:
    from rescue_crew.server import main as run_server

    run_server()
