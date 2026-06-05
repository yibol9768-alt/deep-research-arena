#!/usr/bin/env python3
"""Translate the /annotate pair bundle to Simplified Chinese via DeepSeek (DashScope).

Adds intent_zh / report_a_zh / report_b_zh to each pair in
frontend/public/annotate-pairs.json so the annotation page can be bilingual
(EN/ZH toggle). Markdown structure and sandbox URLs are preserved verbatim.

DeepSeek (deepseek-v3) is called via the DashScope OpenAI-compatible endpoint.
Parallel + resumable (skips fields already translated).

  DEEPSEEK_API_KEY=<bailian key> python3 scripts/translate_annotate_pairs.py
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import threading
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAIRS = ROOT / "frontend" / "public" / "annotate-pairs.json"
BASE = os.environ.get("DEEPSEEK_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v3")
KEY = os.environ.get("DEEPSEEK_API_KEY", "")
_LOCK = threading.Lock()

_SYS = ("You are a professional translator. Translate the user's English deep-research "
        "report text into natural, fluent Simplified Chinese. PRESERVE markdown structure "
        "(headings, lists, tables, bold) and EVERY URL / markdown link target verbatim "
        "(do not translate or alter URLs). Keep product names and proper nouns reasonable. "
        "Output ONLY the translation, no preamble.")


def _translate(text: str, retries: int = 3) -> str:
    if not text or not text.strip():
        return text
    body = {"model": MODEL, "temperature": 0.2, "max_tokens": 8000,
            "messages": [{"role": "system", "content": _SYS},
                         {"role": "user", "content": text}]}
    last = ""
    for _ in range(retries):
        try:
            req = urllib.request.Request(BASE.rstrip("/") + "/chat/completions",
                                         data=json.dumps(body).encode(), method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("Authorization", "Bearer " + KEY)
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read().decode())
            return d["choices"][0]["message"]["content"]
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
    raise RuntimeError(last)


def main() -> int:
    if not KEY:
        print("ERROR: set DEEPSEEK_API_KEY"); return 2
    data = json.loads(PAIRS.read_text(encoding="utf-8"))
    pairs = data["pairs"]
    # build work list of (pair_idx, field, src_field)
    jobs = []
    for i, p in enumerate(pairs):
        for src, dst in (("intent", "intent_zh"), ("report_a", "report_a_zh"), ("report_b", "report_b_zh")):
            if p.get(dst):  # resumable
                continue
            jobs.append((i, src, dst))
    print(f"{len(pairs)} pairs; {len(jobs)} fields to translate")
    done = [0]

    def work(job):
        i, src, dst = job
        try:
            zh = _translate(pairs[i].get(src, ""))
        except Exception as e:
            print(f"  FAIL pair {i} {src}: {e}", flush=True)
            return
        with _LOCK:
            pairs[i][dst] = zh
            done[0] += 1
            if done[0] % 20 == 0:
                PAIRS.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                print(f"  {done[0]}/{len(jobs)} translated (checkpoint saved)", flush=True)

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(work, jobs))

    data["bilingual"] = True
    data["translated_by"] = MODEL
    PAIRS.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    n_zh = sum(1 for p in pairs if p.get("report_a_zh") and p.get("report_b_zh"))
    print(f"done: {n_zh}/{len(pairs)} pairs fully bilingual; wrote {PAIRS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
