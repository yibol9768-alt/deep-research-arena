"""Start a human-baseline session for a deep-tier task.

Sets up the work directory, opens the report template + notes file,
prints the task intent + rules from HUMAN_BASELINE_PROTOCOL.md, and
starts a 4-hour wall-clock timer that prints periodic reminders.

Usage:
    python3 scripts/start_human_baseline.py --task dr_cross_deep_0001

The session writes:
    data/results/deep/human__<task_id>.md     (your report — edit this)
    data/results/deep/human__<task_id>.notes.md  (free-text running notes)
    data/results/deep/human__<task_id>.tabs.txt  (manually paste browser tabs here at end)
    data/results/deep/human__<task_id>.session.json  (timestamps + commands)

Once you finish, hit Ctrl-C; the script will offer to score
your report. Or run separately:
    bash -c '. ./.env && python3 scripts/score_deep_answer.py \\
        --task <task_id> \\
        --answer data/results/deep/human__<task_id>.md \\
        --out    data/results/deep/human__<task_id>.score.json'
"""

from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "results" / "deep"


REPORT_TEMPLATE = """# Human Baseline — {task_id}

*Author:* (your name)
*Started:* {started_at}
*Time budget:* 4 hours hard cap

---

(Write the full report here. Format: markdown, every cited fact must be
`[label](http://localhost:7770|9999|8090/...)`. Include References section
at the end with `[N] [title](url)` lines. See HUMAN_BASELINE_PROTOCOL.md
for the rules. Phases:

- 0:00–0:45  exploration (no writing)
- 0:45–2:45  drafting + citing in-line
- 2:45–3:30  cross-source synthesis section
- 3:30–4:00  bibliography + URL validation

Sandbox URL aliases:
- __SHOPPING__   = http://localhost:7770
- __REDDIT__     = http://localhost:9999
- __WIKIPEDIA__  = http://localhost:8090

DO NOT use any LLM, no agent, no scripts. Browser only.)

"""

NOTES_TEMPLATE = """# Notes — {task_id}

*Started:* {started_at}

(Free-text running log. Add a timestamped line every ~15 minutes
documenting what you're doing.)

[{started_at}]  begin exploration phase.
"""


def _heartbeat(start_ts: float) -> None:
    target = start_ts + 4 * 3600
    while True:
        now = time.time()
        elapsed = now - start_ts
        remaining = target - now
        if remaining <= 0:
            print(f"\n  [HEARTBEAT] !!! 4-hour cap reached !!! "
                  f"Save your work and Ctrl-C to stop.")
        else:
            mins_remaining = int(remaining // 60)
            mins_elapsed = int(elapsed // 60)
            print(f"  [HEARTBEAT] elapsed {mins_elapsed} min  |  remaining {mins_remaining} min")
        time.sleep(15 * 60)


def _print_intro(task: dict, started_at: str, paths: dict) -> None:
    print()
    print("═" * 70)
    print(f"  HUMAN BASELINE — {task['task_id']}")
    print("═" * 70)
    print()
    print(f"  Started: {started_at}")
    print(f"  Hard cap: 4 hours")
    print()
    print("  Task intent (full text):")
    print()
    intent = (task.get("intent", "")
              .replace("__SHOPPING__", "http://localhost:7770")
              .replace("__REDDIT__",   "http://localhost:9999")
              .replace("__WIKIPEDIA__", "http://localhost:8090"))
    for line in intent.split("\n"):
        print(f"    {line}")
    print()
    print("  Files for this session:")
    for k, v in paths.items():
        print(f"    {k:7}  {v}")
    print()
    print("  Rules: NO LLM, NO scraping scripts. Browser + sandbox only.")
    print("  See HUMAN_BASELINE_PROTOCOL.md for full rules.")
    print()
    print("  This terminal will print a heartbeat every 15 min.")
    print("  Press Ctrl-C when you finish — you'll be offered scoring.")
    print()
    print("═" * 70)
    print()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True, help="task id, e.g. dr_cross_deep_0001")
    ap.add_argument("--no-open", action="store_true", help="don't auto-open files in editor")
    args = ap.parse_args()

    task_path = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep" / f"{args.task}.json"
    if not task_path.exists():
        sys.exit(f"task not found: {task_path}")
    task = json.loads(task_path.read_text())

    RESULTS.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    md_path = RESULTS / f"human__{args.task}.md"
    notes_path = RESULTS / f"human__{args.task}.notes.md"
    tabs_path = RESULTS / f"human__{args.task}.tabs.txt"
    session_path = RESULTS / f"human__{args.task}.session.json"

    if not md_path.exists():
        md_path.write_text(REPORT_TEMPLATE.format(task_id=args.task, started_at=started_at))
    if not notes_path.exists():
        notes_path.write_text(NOTES_TEMPLATE.format(task_id=args.task, started_at=started_at))
    if not tabs_path.exists():
        tabs_path.write_text("# paste every URL you opened during the session, one per line\n")

    paths = {
        "report": md_path,
        "notes":  notes_path,
        "tabs":   tabs_path,
    }
    _print_intro(task, started_at, paths)

    session = {
        "task_id": args.task,
        "started_at": started_at,
        "session_path": str(session_path),
        "report_path": str(md_path),
        "notes_path": str(notes_path),
        "tabs_path": str(tabs_path),
    }
    session_path.write_text(json.dumps(session, indent=2))

    if not args.no_open:
        # macOS open command, falls back gracefully on linux
        for p in (md_path, notes_path):
            try:
                subprocess.run(["open", str(p)], check=False)
            except Exception:
                pass

    start_ts = time.time()
    try:
        _heartbeat(start_ts)
    except KeyboardInterrupt:
        end_ts = time.time()
        elapsed = end_ts - start_ts
        ended_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        session["ended_at"] = ended_at
        session["elapsed_seconds"] = round(elapsed, 1)
        session_path.write_text(json.dumps(session, indent=2))
        print()
        print(f"  ended at {ended_at}, elapsed {int(elapsed//60)} min")
        print()
        print(f"  to score:")
        print(f"    set -a && . ./.env && set +a")
        print(f"    python3 scripts/score_deep_answer.py \\")
        print(f"        --task {args.task} \\")
        print(f"        --answer {md_path} \\")
        print(f"        --out    {RESULTS / f'human__{args.task}.score.json'}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
