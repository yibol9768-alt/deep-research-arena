"""Peek at one score JSON to see its actual key structure."""
import json
import sys
from pathlib import Path

fp = Path("/opt/deep_reserch/data/results/deep_v3/deerflow__dr_cross_deep_0001_matrix.score.json")
data = json.loads(fp.read_text(encoding="utf-8"))


def _walk(d, prefix=""):
    if isinstance(d, dict):
        for k, v in d.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, (dict, list)):
                print(f"{path}  ({type(v).__name__}, len={len(v)})")
                if isinstance(v, dict) and len(v) < 30:
                    _walk(v, path)
                elif isinstance(v, list) and v and isinstance(v[0], dict) and len(v) < 5:
                    _walk(v[0], f"{path}[0]")
            else:
                head = repr(v)[:80]
                print(f"{path} = {head}")


_walk(data)
