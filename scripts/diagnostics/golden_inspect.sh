#!/bin/bash
set -u
cd /opt/deep_reserch
.venv-camel/bin/python - <<'PYEOF'
import json
from pathlib import Path

for task in ("dr_cross_deep_0001", "dr_cross_deep_0002"):
    g = Path("data/golden/deep") / f"{task}.json"
    print("="*70)
    print(f"TASK: {task}")
    print("="*70)
    if not g.exists():
        print("  no golden file")
        continue
    d = json.loads(g.read_text(encoding="utf-8"))
    print(f"keys: {list(d.keys())}")
    must_cite = d.get("must_cite_urls") or d.get("must_cite") or []
    print(f"must_cite count: {len(must_cite)}")
    print("first 8 golden URLs:")
    for u in must_cite[:8]:
        print(f"  {u}")
    if len(must_cite) > 8:
        print(f"  ... (+{len(must_cite)-8} more)")
    # also print other URL-bearing fields
    for k in ("pool_urls", "urls", "supporting_urls"):
        v = d.get(k)
        if v:
            print(f"\n{k} count: {len(v)}")
            for u in v[:5]:
                print(f"  {u}")
    print()
PYEOF
