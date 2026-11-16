"""
main.py - Runs the weekly AI Policy Tracker.

    python main.py              full run: scan, email subscribers, save to memory
    python main.py --dry-run    scan and save the digest file, but no email and no memory update
    python main.py --days 14    look back 14 days instead of 7
"""

import argparse
import datetime as dt
import json
import pathlib

from tracker import digest, memory
from tracker.agent import run_agent

ROOT = pathlib.Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    result = run_agent(days=args.days)
    print(f"\nDone in {result['steps_used']} steps. {len(result['findings'])} findings.")

    # Save the digest and the agent's step-by-step log (useful for checking its work)
    (ROOT / "digests").mkdir(exist_ok=True)
    (ROOT / "logs").mkdir(exist_ok=True)
    (ROOT / "digests" / f"{result['end']}.md").write_text(digest.to_markdown(result))
    (ROOT / "logs" / f"{result['end']}.json").write_text(
        json.dumps({k: v for k, v in result.items() if k != "memory"}, indent=2, default=str))
    print(digest.to_markdown(result))

    if args.dry_run:
        print("\nDry run: no email sent, memory not updated.")
        return

    recipients = digest.load_subscribers()
    if recipients:
        digest.send(result, recipients)
        print(f"Emailed {len(recipients)} subscriber(s).")
    memory.remember(result["memory"], result["findings"], result["end"])


if __name__ == "__main__":
    main()
