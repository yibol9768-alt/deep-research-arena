#!/usr/bin/env python3
"""Aggregate the ds_proxy usage log into whole-run token counts and money.

Input: the JSONL written by integrations/ds_proxy/app.py when
DSPROXY_USAGE_LOG is set. Two record kinds share the file:
  usage lines  {"ts", "model", "stream", "prompt_tokens",
                "completion_tokens", "total_tokens"}
  mark lines   {"ts", "mark": true, "run_id", "phase": "start"|"end",
                plus free-form tags (agent, task_id, backbone, ...)}

Runs execute serially on the box, so attribution is by timeline slicing:
every usage line between a run's start and end mark belongs to that run.
Usage outside any run is reported under "_untagged" instead of dropped, so
the totals always reconcile with the raw log.

Money: data/model_prices.json maps model slug -> verified per-Mtok prices.
A model with null prices contributes tokens but no cost; the run's cost is
then reported as a lower bound with `cost_complete: false`. Nothing is ever
priced by guesswork.

Usage:
  python3 scripts/aggregate_run_costs.py --log usage.jsonl \
      [--prices data/model_prices.json] [--out run_costs.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_prices(path: Path) -> tuple[dict, dict]:
    doc = json.loads(path.read_text())
    return doc.get("prices", {}), doc.get("aliases", {})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--log", required=True, help="ds_proxy usage JSONL")
    ap.add_argument("--prices", default=str(ROOT / "data" / "model_prices.json"))
    ap.add_argument("--out", help="write per-run JSON here (default: stdout table only)")
    args = ap.parse_args()

    prices, aliases = load_prices(Path(args.prices))

    def price_of(model: str) -> dict | None:
        slug = aliases.get(model or "", model or "")
        p = prices.get(slug)
        if p and p.get("input_per_mtok") is not None:
            return p
        return None

    runs: dict[str, dict] = {}
    order: list[str] = []
    current: str | None = None
    warnings: list[str] = []

    def bucket(run_key: str) -> dict:
        if run_key not in runs:
            runs[run_key] = {"run_id": run_key, "tags": {}, "n_calls": 0,
                            "prompt_tokens": 0, "completion_tokens": 0,
                            "total_tokens": 0, "usage_missing_calls": 0,
                            "per_model": defaultdict(lambda: {
                                "n_calls": 0, "prompt_tokens": 0,
                                "completion_tokens": 0})}
            order.append(run_key)
        return runs[run_key]

    n_lines = 0
    for raw in open(args.log, errors="replace"):
        raw = raw.strip()
        if not raw:
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            warnings.append(f"unparseable line skipped: {raw[:80]}")
            continue
        n_lines += 1
        if rec.get("mark"):
            run_id = str(rec.get("run_id", "unnamed"))
            phase = rec.get("phase")
            if phase == "start":
                if current is not None:
                    warnings.append(f"run {current!r} not ended before "
                                    f"{run_id!r} started; closing it")
                current = run_id
                b = bucket(run_id)
                b["tags"].update({k: v for k, v in rec.items()
                                  if k not in ("mark", "run_id", "phase", "ts")})
                b.setdefault("started_ts", rec.get("ts"))
            elif phase == "end":
                if current != run_id:
                    warnings.append(f"end mark for {run_id!r} while current "
                                    f"is {current!r}")
                if current is not None:
                    runs[current]["ended_ts"] = rec.get("ts")
                current = None
            continue
        b = bucket(current if current is not None else "_untagged")
        b["n_calls"] += 1
        if rec.get("usage_missing"):
            b["usage_missing_calls"] += 1
            continue
        pt = int(rec.get("prompt_tokens") or 0)
        ct = int(rec.get("completion_tokens") or 0)
        b["prompt_tokens"] += pt
        b["completion_tokens"] += ct
        b["total_tokens"] += int(rec.get("total_tokens") or (pt + ct))
        m = b["per_model"][rec.get("model") or "unknown"]
        m["n_calls"] += 1
        m["prompt_tokens"] += pt
        m["completion_tokens"] += ct

    if current is not None:
        warnings.append(f"log ended while run {current!r} still open")

    out_runs = []
    for key in order:
        b = runs[key]
        cost, cost_complete, currency = 0.0, True, None
        for model, m in b["per_model"].items():
            p = price_of(model)
            if p is None:
                cost_complete = False
                continue
            if currency is None:
                currency = p.get("currency")
            elif currency != p.get("currency"):
                warnings.append(f"run {key!r}: mixed currencies, cost kept "
                                f"in first currency {currency!r}")
                cost_complete = False
                continue
            cost += (m["prompt_tokens"] * p["input_per_mtok"]
                     + m["completion_tokens"] * p["output_per_mtok"]) / 1e6
        b["per_model"] = {k: dict(v) for k, v in b["per_model"].items()}
        b["cost"] = round(cost, 6) if currency else None
        b["cost_currency"] = currency
        b["cost_complete"] = cost_complete and currency is not None
        out_runs.append(b)

    doc = {"log": args.log, "n_log_lines": n_lines, "runs": out_runs,
           "warnings": warnings}
    if args.out:
        Path(args.out).write_text(json.dumps(doc, indent=2, ensure_ascii=False)
                                  + "\n")
        print(f"wrote {args.out}")

    for b in out_runs:
        cost_s = (f"{b['cost']} {b['cost_currency']}"
                  + ("" if b["cost_complete"] else " (incomplete)")
                  if b["cost_currency"] else "tokens only")
        print(f"{b['run_id']:40s} calls={b['n_calls']:4d} "
              f"tok={b['total_tokens']:>10,} ({b['prompt_tokens']:,}p+"
              f"{b['completion_tokens']:,}c) cost={cost_s}")
    for w in warnings:
        print(f"warn: {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
