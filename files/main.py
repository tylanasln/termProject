"""
main.py — Example entry point for the Red/Blue/Audit capstone simulation.

Usage:
    export ANTHROPIC_API_KEY=sk-...
    python main.py
"""

import json
import os

from orchestrator import Orchestrator

EXAMPLE_ARCHITECTURE = """
Web application: React SPA frontend, Node/Express REST API backend,
PostgreSQL database. Authentication via JWT issued by the API, stored in
localStorage on the client. Password reset flow emails a reset link with a
6-digit numeric code, valid for 15 minutes, no rate limiting on the
verification endpoint. Customer support staff have a shared internal admin
panel accessible from any IP with just username/password (no MFA), used to
look up user accounts and issue manual refunds. File uploads (profile
pictures) are stored on S3 with filenames derived directly from the
original uploaded filename.
""".strip()


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY before running.")

    orch = Orchestrator()
    state = orch.run(EXAMPLE_ARCHITECTURE, max_rounds=5, score_threshold=80)

    print("\n=== TRANSCRIPT ===")
    for line in state.transcript:
        print(line)

    print("\n=== FINAL REPORT ===")
    print(json.dumps(state.final_report, indent=2))

    os.makedirs("output", exist_ok=True)
    state.save("output/simulation_result.json")
    print("\nFull state saved to output/simulation_result.json")


if __name__ == "__main__":
    main()
