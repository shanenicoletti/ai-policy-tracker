"""
memory.py - What the agent remembers between weekly runs.

Every item the agent reports gets saved to data/reported.json. Next week,
the agent checks this list so it doesn't send the same update twice.
"""

import json
import pathlib

MEMORY_FILE = pathlib.Path(__file__).resolve().parent.parent / "data" / "reported.json"


def _normalize(url: str) -> str:
    return url.strip().rstrip("/").lower().replace("http://", "https://")


def load() -> dict:
    if MEMORY_FILE.exists():
        return json.loads(MEMORY_FILE.read_text())
    return {}


def already_reported(memory: dict, url: str) -> bool:
    return _normalize(url) in memory


def remember(memory: dict, findings: list[dict], run_date: str) -> None:
    for f in findings:
        memory[_normalize(f["url"])] = {"title": f["title"], "reported_on": run_date}
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(json.dumps(memory, indent=2, sort_keys=True))
