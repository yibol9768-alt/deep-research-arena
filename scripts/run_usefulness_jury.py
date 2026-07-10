"""Usefulness jury: pairwise battles judging human-usefulness of DR reports.

Design contract: internal/docs/USEFULNESS_JURY_DESIGN_2026-07-07.md (secs 1-10).
This module is the "load-bearing" implementation of section 10's CLI.

Rubric (told to every judge, protocol="uj_v1"):
  q1 answer directness / q2 actionability / q3 time-to-insight /
  q4 verifiability-for-a-human. Judges do NOT check citation truthfulness
  (a separate system does) and must not reward length or citation count.

Mechanics:
  - Battle bank: an append-only JSONL file. Each line is one immutable
    (backbone, task, a, b, order, judge) judgement. Re-running is a no-op
    (dedup by that key, keeping the newest ts) so `--fit` is a free,
    replayable, pure computation over the bank -- never re-judged.
  - Stub reports (broken runner lanes) are walkovers: the agent sits out
    of every battle for that task and nobody records a loss against it.
  - Bradley-Terry with ties (0.5/0.5) via src.scoring.bradley_terry
    (already used by the v1 real-report jury / build_real_leaderboard.py).

Usage: see internal/docs/USEFULNESS_JURY_DESIGN_2026-07-07.md sec 10, or
run with --help.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import math
import os
import random
import sys
import time
import traceback
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PROTOCOL = "uj_v2"
DEFAULT_WORD_BUDGET = 1500
DEFAULT_MAX_TOKENS = 600
DEFAULT_TIMEOUT_S = 30.0
DEFAULT_RETRIES = 3
DEFAULT_TASKS_DIR = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"
DEFAULT_ENV_FILE = Path("/root/.config/dra/bailian.env")
DEFAULT_DASHSCOPE_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"

# ---------------------------------------------------------------------------
# Stub detection: prefer the shared classifier, fall back to a conservative
# local heuristic if the import fails (e.g. this file got copied somewhere
# without the src/ tree next to it).
# ---------------------------------------------------------------------------
try:
    from src.eval.report_stubs import is_stub as _is_stub_shared
except Exception:
    _is_stub_shared = None

_FALLBACK_STUB_HEAD_RE = None


def is_stub_report(text: Optional[str]) -> bool:
    if _is_stub_shared is not None:
        try:
            return bool(_is_stub_shared(text))
        except Exception:
            pass
    # Fallback: length floor or a known stub-marker leading paren.
    import re

    global _FALLBACK_STUB_HEAD_RE
    if _FALLBACK_STUB_HEAD_RE is None:
        _FALLBACK_STUB_HEAD_RE = re.compile(
            r"^\(\s*[A-Za-z][^\n]{0,200}"
            r"(produced no report|timeout|error|stderr|empty)[^\n]*\)\Z",
            re.IGNORECASE,
        )
    s = (text or "").strip()
    if not s:
        return True
    if _FALLBACK_STUB_HEAD_RE.match(s):
        return True
    return len(s) < 600


# Family map for same_family tagging (self-preference audit trail). Prefer
# the shared judge_client helper; fall back to a small local table.
try:
    from src.verifiers.judge_client import family_of as _family_of_shared
except Exception:
    _family_of_shared = None

_FALLBACK_FAMILY_KEYWORDS = {
    "glm": "glm", "chatglm": "glm", "zhipu": "glm",
    "deepseek": "deepseek", "ds": "deepseek",
    "claude": "claude", "anthropic": "claude",
    "gpt": "openai", "openai": "openai",
    "qwen": "qwen", "gemini": "gemini",
    "kimi": "kimi", "moonshot": "kimi",
    "minimax": "minimax",
}


def family_of(name: Optional[str]) -> Optional[str]:
    if _family_of_shared is not None:
        try:
            fam = _family_of_shared(name)
            if fam:
                return fam
        except Exception:
            pass
    if not name:
        return None
    low = str(name).lower()
    for kw, fam in _FALLBACK_FAMILY_KEYWORDS.items():
        if kw in low:
            return fam
    return None


# ---------------------------------------------------------------------------
# Judge price table (CNY per 1M tokens). See design doc sec 6. glm-4.7 price
# is not confirmed -> flagged "estimated" so cost reports say so honestly.
# ---------------------------------------------------------------------------
PRICE_TABLE = {
    "deepseek": {"in": 1.0, "out": 2.0, "estimated": False},
    "minimax": {"in": 1.1, "out": 8.3, "estimated": False},
    "kimi": {"in": 4.3, "out": 21.6, "estimated": False},
    "glm": {"in": 2.0, "out": 8.0, "estimated": True},
}
DEFAULT_PRICE = {"in": 2.0, "out": 8.0, "estimated": True}
# Design doc sec 6: ~5.2k input / ~0.25k output tokens per call, used only
# before any real usage data exists (dry-run / pre-flight budget estimate).
EST_PROMPT_TOKENS = 5200
EST_COMPLETION_TOKENS = 250


def price_for(model_id: str) -> dict:
    fam = family_of(model_id) or ""
    return PRICE_TABLE.get(fam, DEFAULT_PRICE)


def call_cost_cny(model_id: str, prompt_tokens: int, completion_tokens: int) -> float:
    p = price_for(model_id)
    return (prompt_tokens / 1e6) * p["in"] + (completion_tokens / 1e6) * p["out"]


# ---------------------------------------------------------------------------
# Rubric prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = f"""You are one judge on a panel scoring which of two AI-generated \
deep-research reports (A and B) is more USEFUL TO A HUMAN who asked the question \
below. Both reports attempt to answer the SAME question.

Judge only usefulness. A separate system independently checks whether cited \
URLs/facts are genuine -- you must NOT judge citation truthfulness, and you must \
NOT reward a report for being longer or for citing more sources. A short, direct, \
well-organized report can beat a long padded one.

Answer four sub-questions, each 1-2 sentences comparing A vs B, then a single \
overall verdict:
  q1 answer directness    -- which report answers the user's actual question \
                              most directly, rather than a broad survey of the topic?
  q2 actionability         -- after reading, which report lets the user actually \
                              decide/act (e.g. pick a product, reach a conclusion)?
  q3 time-to-insight       -- which report's structure (front-loaded conclusion, \
                              comparison table, clear headings) gets the point \
                              across in the first 30 seconds of reading?
  q4 verifiability for a human -- which report's citations are easier for a human \
                              to spot-check (inline next to the claim) rather than \
                              dumped in an unlinked list at the end?

Respond with ONLY one JSON object, no markdown code fence, no text before or \
after it, exactly these keys:
{{"q1": "...", "q2": "...", "q3": "...", "q4": "...", "winner": "A", "rationale": "..."}}
"winner" must be exactly "A", "B", or "tie". protocol={PROTOCOL}"""


def build_user_prompt(intent: str, report_a: str, report_b: str, word_budget: int) -> str:
    a = truncate_words(report_a, word_budget)
    b = truncate_words(report_b, word_budget)
    return (
        f"# User question\n{intent.strip()}\n\n"
        f"# Report A\n{a}\n\n"
        f"# Report B\n{b}\n\n"
        "Now output the JSON verdict only."
    )


def truncate_words(text: str, budget: int) -> str:
    words = (text or "").split()
    if len(words) <= budget:
        return text or ""
    return " ".join(words[:budget]) + " [... truncated at word budget ...]"


def word_count(text: str) -> int:
    return len((text or "").split())


# ---------------------------------------------------------------------------
# Robust JSON extraction: judge output may carry a thinking prefix. Scan for
# balanced-brace top-level {...} substrings and try the LAST one that parses.
# ---------------------------------------------------------------------------
def extract_last_json_object(text: str) -> Optional[dict]:
    if not text:
        return None
    candidates: list[str] = []
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    candidates.append(text[start:i + 1])
    for cand in reversed(candidates):
        try:
            obj = json.loads(cand)
        except Exception:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def normalize_verdict(obj: dict) -> tuple[Optional[dict], Optional[str]]:
    """Validate a parsed judge JSON. Returns (clean_dict, error)."""
    if obj is None:
        return None, "no parseable JSON object in judge output"
    winner = str(obj.get("winner", "")).strip().strip('"').upper()
    if winner not in ("A", "B", "TIE"):
        return None, f"invalid winner field: {obj.get('winner')!r}"
    winner = "tie" if winner == "TIE" else winner
    out = {
        "q1": str(obj.get("q1", ""))[:600],
        "q2": str(obj.get("q2", ""))[:600],
        "q3": str(obj.get("q3", ""))[:600],
        "q4": str(obj.get("q4", ""))[:600],
        "winner": winner,
        "rationale": str(obj.get("rationale", ""))[:600],
    }
    return out, None


# ---------------------------------------------------------------------------
# Judge backends
# ---------------------------------------------------------------------------
def load_env_file(path: Path) -> None:
    """Best-effort `export VAR=value` sourcing into os.environ (no shell)."""
    if not path.exists():
        return
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            if "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass


def _endpoint_and_key() -> tuple[str, Optional[str]]:
    base = (
        os.environ.get("OPENAI_PROXY_UPSTREAM")
        or os.environ.get("DASHSCOPE_BASE_URL")
        or DEFAULT_DASHSCOPE_BASE
    )
    key = os.environ.get("OPENAI_PROXY_KEY") or os.environ.get("DASHSCOPE_API_KEY")
    base = base.rstrip("/")
    if not base.endswith("/chat/completions"):
        base = base + "/chat/completions"
    return base, key


def _extra_body_for(model: str) -> dict:
    """Disable 'thinking' for families whose reasoning eats the tight token
    budget and leaves `content` empty (mirrors src/verifiers/judge_client.py).
    """
    low = model.lower()
    if low.startswith("deepseek-v4") or low.startswith("glm"):
        return {"thinking": {"type": "disabled"}}
    if low.startswith("qwen3"):
        return {"enable_thinking": False}
    return {}


def call_real_judge(
    model: str,
    system: str,
    user: str,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = 0.0,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    retries: int = DEFAULT_RETRIES,
) -> dict:
    """Returns {"text","usage":{prompt,completion},"error"}."""
    import requests

    url, key = _endpoint_and_key()
    if not key:
        return {"text": None, "usage": {"prompt": 0, "completion": 0},
                "error": "no API key (OPENAI_PROXY_KEY / DASHSCOPE_API_KEY unset)"}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    body.update(_extra_body_for(model))

    last_err = None
    for attempt in range(retries):
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=timeout_s)
            if resp.status_code != 200:
                last_err = f"HTTP {resp.status_code}: {resp.text[:500]}"
            else:
                data = resp.json()
                choice = (data.get("choices") or [{}])[0]
                msg = choice.get("message", {}) or {}
                text = msg.get("content") or ""
                usage = data.get("usage") or {}
                if not text.strip():
                    reasoning = msg.get("reasoning_content") or ""
                    if reasoning:
                        text = reasoning
                if text.strip():
                    return {
                        "text": text,
                        "usage": {
                            "prompt": int(usage.get("prompt_tokens", 0) or 0),
                            "completion": int(usage.get("completion_tokens", 0) or 0),
                        },
                        "error": None,
                    }
                last_err = "empty content and empty reasoning_content"
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
        if attempt < retries - 1:
            time.sleep(2 ** attempt)
    return {"text": None, "usage": {"prompt": 0, "completion": 0}, "error": last_err}


def call_mock_judge(model: str, system: str, user: str, **_kw) -> dict:
    """Deterministic offline judge for self-test. Winner picked by a stable
    hash of the prompt so BT fitting over many battles has real structure
    to fit (not a flat all-tie board), without any network calls.
    """
    h = int(hashlib.sha256(f"{model}|{user}".encode("utf-8")).hexdigest()[:8], 16)
    r = h % 10
    winner = "A" if r < 4 else ("B" if r < 8 else "tie")
    obj = {
        "q1": "mock", "q2": "mock", "q3": "mock", "q4": "mock",
        "winner": winner, "rationale": "mock deterministic verdict",
    }
    text = json.dumps(obj)
    return {
        "text": text,
        "usage": {"prompt": len(system.split()) + len(user.split()), "completion": len(text.split())},
        "error": None,
    }


def run_judge(model: str, system: str, user: str, *, max_tokens: int, timeout_s: float, retries: int) -> dict:
    if model.strip().lower().startswith("mock"):
        return call_mock_judge(model, system, user)
    return call_real_judge(model, system, user, max_tokens=max_tokens, timeout_s=timeout_s, retries=retries)


# ---------------------------------------------------------------------------
# Staging discovery
# ---------------------------------------------------------------------------
def intent_for_battle(task_id: str, tasks_dir: Path, *, walkover: bool) -> str:
    """The question a battle is judged on, or a refusal to judge without one.

    A missing/unreadable task file used to be swallowed by ``or ""`` at the
    call sites: the jury sat over an EMPTY question and the verdict entered the
    bank with error=None, indistinguishable from clean data (SPEC_ISSUES G6).
    A walkover needs no intent (its outcome is decided by report stubs); any
    real judging call must refuse loudly and machine-readably instead.
    """
    intent = load_intent(task_id, tasks_dir)
    if intent is None and not walkover:
        raise FileNotFoundError(
            f"task_intent_missing: {task_id} has no readable task file under "
            f"{tasks_dir}; refusing to judge an empty question")
    return intent or ""


def load_intent(task_id: str, tasks_dir: Path) -> Optional[str]:
    p = tasks_dir / f"{task_id}.json"
    if not p.exists():
        return None
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    intent = cfg.get("intent", "")
    subs = {
        "__SHOPPING__": "http://localhost:17770",
        "__REDDIT__": "http://localhost:9999",
        "__WIKIPEDIA__": "http://localhost:8090",
    }
    for k, v in subs.items():
        intent = intent.replace(k, v)
    return intent


def discover_staging(
    staging_dir: Path, backbone: str, exclude_agents: set[str]
) -> dict[str, dict[str, Path | None]]:
    """Return every staged task crossed with every staged agent.

    A missing or stub report remains in the matrix as a deterministic walkover.
    Dropping it used to reward non-delivery by letting the lane sit out losses.
    """
    backbone_dir = staging_dir / backbone
    if not backbone_dir.is_dir():
        raise SystemExit(f"backbone dir not found: {backbone_dir}")
    found: dict[str, dict[str, Path]] = defaultdict(dict)
    agent_dirs = sorted(
        d for d in backbone_dir.iterdir()
        if d.is_dir() and d.name not in exclude_agents
    )
    for agent_dir in agent_dirs:
        agent = agent_dir.name
        for md in sorted(agent_dir.glob("*.md")):
            task_id = md.stem
            found[task_id][agent] = md
    tasks = sorted(found)
    return {
        task: {agent_dir.name: found.get(task, {}).get(agent_dir.name)
               for agent_dir in agent_dirs}
        for task in tasks
    }


def _report_text(path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _report_sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Battle plan
# ---------------------------------------------------------------------------
def build_plan(
    task_agents: dict[str, dict[str, Path | None]],
    *,
    only_agent: Optional[str],
    only_task: Optional[str],
    order_audit: float,
    seed: int,
) -> list[dict]:
    """Return list of {"task","a","b","order"} with a<b canonical, order in
    {"ab","ba"}. order_audit fraction of PAIRS get both orders.
    """
    rng = random.Random(seed)
    plan: list[dict] = []
    for task_id in sorted(task_agents):
        if only_task and task_id != only_task:
            continue
        agents = sorted(task_agents[task_id])
        if only_agent and only_agent not in agents:
            continue
        pairs = list(combinations(agents, 2))
        if only_agent:
            pairs = [p for p in pairs if only_agent in p]
        for a, b in pairs:
            primary_order = rng.choice(["ab", "ba"])
            audited = rng.random() < order_audit
            orders = ["ab", "ba"] if audited else [primary_order]
            for order in orders:
                ta, tb = _report_text(task_agents[task_id][a]), _report_text(task_agents[task_id][b])
                plan.append({
                    "task": task_id, "a": a, "b": b, "order": order,
                    "audited": audited,
                    "report_sha_a": _report_sha(ta),
                    "report_sha_b": _report_sha(tb),
                    "walkover": bool(is_stub_report(ta) or is_stub_report(tb)),
                })
    return plan


# ---------------------------------------------------------------------------
# Bank I/O
# ---------------------------------------------------------------------------
def bank_key(rec: dict) -> tuple:
    return (
        rec["protocol"], rec["backbone"], rec["task"], rec["a"], rec["b"],
        rec["order"], rec["judge"], rec.get("report_sha_a"),
        rec.get("report_sha_b"),
    )


def load_bank(bank_path: Path) -> dict[tuple, dict]:
    """Dedup by key, keeping the record with the latest ts (supersede
    semantics: a newer record for the same key silently wins)."""
    out: dict[tuple, dict] = {}
    if not bank_path.exists():
        return out
    with bank_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            try:
                k = bank_key(rec)
            except Exception:
                continue
            prev = out.get(k)
            if prev is None or rec.get("ts", 0) >= prev.get("ts", 0):
                out[k] = rec
    return out


def append_bank(bank_path: Path, rec: dict) -> None:
    bank_path.parent.mkdir(parents=True, exist_ok=True)
    with bank_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Battle execution
# ---------------------------------------------------------------------------
def rubric_hash() -> str:
    return hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:16]


def run_one_battle_judge(
    *,
    backbone: str,
    task_id: str,
    a: str,
    b: str,
    order: str,
    judge: str,
    intent: str,
    report_a: str,
    report_b: str,
    word_budget: int,
    max_tokens: int,
    timeout_s: float,
    retries: int,
) -> dict:
    # order "ab": position A=a, B=b. order "ba": position A=b, B=a.
    if order == "ab":
        pos_a_text, pos_b_text = report_a, report_b
    else:
        pos_a_text, pos_b_text = report_b, report_a
    user = build_user_prompt(intent, pos_a_text, pos_b_text, word_budget)
    result = run_judge(judge, SYSTEM_PROMPT, user, max_tokens=max_tokens, timeout_s=timeout_s, retries=retries)
    ts = time.time()
    base = {
        "ts": ts,
        "protocol": PROTOCOL,
        "rubric_hash": rubric_hash(),
        "word_budget": word_budget,
        "backbone": backbone,
        "task": task_id,
        "a": a,
        "b": b,
        "order": order,
        "judge": judge,
        "model_id": judge,
        "report_sha_a": _report_sha(report_a),
        "report_sha_b": _report_sha(report_b),
        "walkover": False,
        # Both agents in a battle share the same backbone LLM (staging is
        # partitioned by backbone), so "same_family" is one flag per battle:
        # is this judge's family the same as the backbone under test? Only
        # True when BOTH families resolve and match (two unresolved families
        # must never count as "same").
        "same_family": bool(family_of(judge)) and family_of(judge) == family_of(backbone),
    }
    if result.get("error"):
        base.update({
            "q1": None, "q2": None, "q3": None, "q4": None, "winner": None,
            "usage": result.get("usage", {"prompt": 0, "completion": 0}),
            "error": result["error"],
        })
        return base
    verdict, verr = normalize_verdict(extract_last_json_object(result["text"]))
    if verr:
        base.update({
            "q1": None, "q2": None, "q3": None, "q4": None, "winner": None,
            "usage": result.get("usage", {"prompt": 0, "completion": 0}),
            "error": verr,
        })
        return base
    base.update(verdict)
    base["usage"] = result.get("usage", {"prompt": 0, "completion": 0})
    base["error"] = None
    return base


def walkover_record(
    *, backbone: str, task_id: str, a: str, b: str, order: str, judge: str,
    report_a: str, report_b: str, word_budget: int,
) -> dict:
    """Deterministic outcome when one or both lanes did not deliver a report."""
    stub_a, stub_b = is_stub_report(report_a), is_stub_report(report_b)
    if stub_a == stub_b:
        winner_agent = "tie"
    else:
        winner_agent = b if stub_a else a
    if winner_agent == "tie":
        winner_pos = "tie"
    elif order == "ab":
        winner_pos = "A" if winner_agent == a else "B"
    else:
        winner_pos = "A" if winner_agent == b else "B"
    return {
        "ts": time.time(), "protocol": PROTOCOL, "rubric_hash": rubric_hash(),
        "word_budget": word_budget, "backbone": backbone, "task": task_id,
        "a": a, "b": b, "order": order, "judge": judge, "model_id": judge,
        "report_sha_a": _report_sha(report_a), "report_sha_b": _report_sha(report_b),
        "walkover": True, "walkover_reason": (
            "both_missing_or_stub" if stub_a and stub_b else
            (f"{a}_missing_or_stub" if stub_a else f"{b}_missing_or_stub")
        ),
        "q1": winner_pos, "q2": winner_pos, "q3": winner_pos, "q4": winner_pos,
        "winner": winner_pos, "usage": {"prompt": 0, "completion": 0},
        "error": None, "same_family": False,
    }


# ---------------------------------------------------------------------------
# Fit (Bradley-Terry + Fleiss kappa + cost summary)
# ---------------------------------------------------------------------------
def _fleiss_kappa(rows: list[list[int]]) -> Optional[float]:
    """rows: one row per item, each row is category counts (must sum to n
    raters, same n for every row). Returns None if <2 items or n<2."""
    if not rows:
        return None
    n = sum(rows[0])
    if n < 2:
        return None
    N = len(rows)
    k = len(rows[0])
    p_cat = [0.0] * k
    P_i = []
    for row in rows:
        if sum(row) != n:
            continue
        P_i.append((sum(c * c for c in row) - n) / (n * (n - 1)))
        for j in range(k):
            p_cat[j] += row[j]
    if not P_i:
        return None
    total = N * n
    p_cat = [c / total for c in p_cat]
    P_bar = sum(P_i) / len(P_i)
    P_e = sum(p * p for p in p_cat)
    if abs(1 - P_e) < 1e-12:
        return 1.0
    return (P_bar - P_e) / (1 - P_e)


def fit_from_bank(
    bank_records: list[dict],
    *,
    backbone: Optional[str],
    judges: Optional[list[str]] = None,
    bootstrap: int = 0,
    seed: int = 42,
) -> dict:
    from src.scoring import bradley_terry as bt

    recs = [r for r in bank_records if r.get("error") is None and r.get("winner") is not None]
    if backbone:
        recs = [r for r in recs if r["backbone"] == backbone]
    if judges is not None:
        wanted = set(judges)
        recs = [r for r in recs if r.get("judge") in wanted]

    # Protocol-mixing guard (design sec 9: rubric hash + judges + word_budget
    # must match to mix battles in one fit).
    proto_keys = {(r.get("protocol"), r.get("rubric_hash"), r.get("word_budget")) for r in recs}
    if len(proto_keys) > 1:
        raise SystemExit(
            "refusing to fit: bank contains mixed protocol/rubric_hash/word_budget "
            f"combinations: {proto_keys}. Split into separate protocol_version dirs."
        )

    by_backbone: dict[str, list[dict]] = defaultdict(list)
    for r in recs:
        by_backbone[r["backbone"]].append(r)

    def _fit_one(backbone_name: str, brecs: list[dict]) -> dict:
        # Item = (task, a, b, order) over ONE report pair. The bank can hold
        # several GENERATIONS of the same pairing (a re-staged report changes
        # report_sha_*, and bank_key keeps both); the old 4-tuple item key mixed
        # judges from different generations into one item and let bank record
        # order decide which generation's verdict survived per judge
        # (SPEC_ISSUES G6: "跨代拼池"). Group by the full report-pair identity,
        # then keep only the LATEST generation per pairing -- the same
        # supersede-by-newer semantics load_bank already declares for identical
        # keys -- so a fit never pools two different report pairs as one battle
        # and never double-counts the pairing.
        items_all: dict[tuple, dict[str, str]] = defaultdict(dict)
        gen_ts: dict[tuple, float] = {}
        for r in brecs:
            gkey = (r["task"], r["a"], r["b"], r["order"],
                    r.get("report_sha_a"), r.get("report_sha_b"))
            items_all[gkey][r["judge"]] = r["winner"]
            gen_ts[gkey] = max(gen_ts.get(gkey, 0.0), float(r.get("ts") or 0.0))
        latest_gen: dict[tuple, tuple] = {}
        for gkey in items_all:
            k4 = gkey[:4]
            if k4 not in latest_gen or gen_ts[gkey] > gen_ts[latest_gen[k4]]:
                latest_gen[k4] = gkey
        items = {k4: items_all[g] for k4, g in latest_gen.items()}

        battles = []
        fleiss_rows = []
        n_clean = 0
        n_total_items = len(items)
        n_superseded_generations = len(items_all) - len(items)
        cats = ["A", "B", "tie"]
        for (task, a, b, order), votes in items.items():
            if order == "ab":
                pos_agent = {"A": a, "B": b}
            else:
                pos_agent = {"A": b, "B": a}
            a_votes = sum(1 for v in votes.values() if v == "A")
            b_votes = sum(1 for v in votes.values() if v == "B")
            # MAJORITY vote (USEFULNESS_JURY_DESIGN sec "多数票裁决"), not a
            # plurality that ignores tie ballots: a side wins only with a strict
            # majority of the votes CAST. The old rule let votes={tie,tie,A}
            # crown A -- one judge overruling two tie verdicts (SPEC_ISSUES G6,
            # jury 整改). {A,A,tie} still resolves to A; {A,B,tie} stays tie.
            n_votes = len(votes)
            if 2 * a_votes > n_votes:
                winner_pos = "A"
            elif 2 * b_votes > n_votes:
                winner_pos = "B"
            else:
                winner_pos = "tie"
            winner_agent = pos_agent.get(winner_pos, "tie") if winner_pos != "tie" else "tie"
            battles.append({"agent_a": a, "agent_b": b, "winner": winner_agent})
            # Walkover status is a property of THIS generation's report pair;
            # an old generation's walkover must not taint the fresh item.
            chosen_gen = latest_gen[(task, a, b, order)]
            is_walkover = any(
                bool(r.get("walkover"))
                for r in brecs
                if (r["task"], r["a"], r["b"], r["order"],
                    r.get("report_sha_a"), r.get("report_sha_b")) == chosen_gen
            )
            if judges and set(votes) == set(judges) and not is_walkover:
                n_clean += 1
                row = [0, 0, 0]
                for v in votes.values():
                    row[cats.index(v)] += 1
                fleiss_rows.append(row)

        agents = sorted({r["a"] for r in brecs} | {r["b"] for r in brecs})
        elo = bt.fit_bradley_terry(battles) if battles else {a: 1000.0 for a in agents}
        elo_scale = bt.ELO_SCALE
        r_of = {a: (elo.get(a, 1000.0) - 1000.0) / elo_scale for a in agents}

        agent_rows = {}
        n_battle_count = defaultdict(int)
        n_win = defaultdict(int)
        n_loss = defaultdict(int)
        n_tie = defaultdict(int)
        for b_ in battles:
            aa, bb, w = b_["agent_a"], b_["agent_b"], b_["winner"]
            n_battle_count[aa] += 1
            n_battle_count[bb] += 1
            if w == "tie":
                n_tie[aa] += 1
                n_tie[bb] += 1
            elif w == aa:
                n_win[aa] += 1
                n_loss[bb] += 1
            else:
                n_win[bb] += 1
                n_loss[aa] += 1

        for ag in agents:
            others = [o for o in agents if o != ag]
            if others:
                probs = [1.0 / (1.0 + math.exp(r_of[o] - r_of[ag])) for o in others]
                winrate_vs_avg = sum(probs) / len(probs)
            else:
                winrate_vs_avg = 0.5
            n_b = n_battle_count[ag]
            agent_rows[ag] = {
                "bt_elo": round(elo.get(ag, 1000.0), 1),
                "winrate_vs_avg_opponent": round(winrate_vs_avg, 4),
                "n_battles": n_b,
                "n_wins": n_win[ag],
                "n_losses": n_loss[ag],
                "n_ties": n_tie[ag],
                "tie_rate": round(n_tie[ag] / n_b, 4) if n_b else None,
            }

        kappa = _fleiss_kappa(fleiss_rows) if fleiss_rows else None

        return {
            "backbone": backbone_name,
            "n_items_ab_order_pairs": n_total_items,
            "n_clean_items_all_judges_voted": n_clean,
            # Older report-pair generations dropped by the supersede rule above;
            # non-zero means the bank holds re-staged pairings and this fit used
            # only the newest of each (machine-readable, never silent).
            "n_superseded_generations": n_superseded_generations,
            "fleiss_kappa": round(kappa, 4) if kappa is not None else None,
            "agents": agent_rows,
        }

    def _bootstrap_ci(brecs: list[dict], n_boot: int, seed_: int) -> dict:
        """Cluster bootstrap over TASKS (the sampling unit that varies between
        runs). Duplicated tasks are re-tagged so their battles stay distinct
        items instead of collapsing in the majority-vote dedup. Returns per
        agent 95% CI on winrate_vs_avg and on rank; adjacent systems whose
        rank CIs overlap are statistically tied at this task count."""
        rnd = random.Random(seed_)
        by_task: dict[str, list[dict]] = defaultdict(list)
        for r in brecs:
            by_task[r["task"]].append(r)
        tasks = sorted(by_task)
        winrates: dict[str, list[float]] = defaultdict(list)
        rank_samples: dict[str, list[int]] = defaultdict(list)
        for _ in range(n_boot):
            recs_b: list[dict] = []
            for i, t in enumerate(rnd.choices(tasks, k=len(tasks))):
                for r in by_task[t]:
                    recs_b.append({**r, "task": f"{r['task']}#b{i}"})
            rows_b = _fit_one("_boot", recs_b)["agents"]
            order = sorted(rows_b, key=lambda a: -rows_b[a]["winrate_vs_avg_opponent"])
            for rank, ag in enumerate(order, 1):
                winrates[ag].append(rows_b[ag]["winrate_vs_avg_opponent"])
                rank_samples[ag].append(rank)
        out: dict[str, dict] = {}
        for ag, vals in winrates.items():
            vals.sort()
            rs = sorted(rank_samples[ag])
            lo_i = int(0.025 * (len(vals) - 1))
            hi_i = int(0.975 * (len(vals) - 1))
            out[ag] = {
                "winrate_ci95": [round(vals[lo_i], 4), round(vals[hi_i], 4)],
                "rank_ci95": [rs[lo_i], rs[hi_i]],
                "n_boot_present": len(vals),
            }
        return out

    def _with_ci(backbone_name: str, brecs: list[dict]) -> dict:
        sub = _fit_one(backbone_name, brecs)
        if bootstrap and brecs:
            ci = _bootstrap_ci(brecs, bootstrap, seed)
            for ag, extra in ci.items():
                if ag in sub["agents"]:
                    sub["agents"][ag].update(extra)
            sub["bootstrap_n"] = bootstrap
        return sub

    result = {
        "protocol": PROTOCOL,
        "rubric_hash": list(proto_keys)[0][1] if proto_keys else rubric_hash(),
        "word_budget": list(proto_keys)[0][2] if proto_keys else DEFAULT_WORD_BUDGET,
        "generated_at": time.time(),
    }
    if backbone:
        result.update(_with_ci(backbone, by_backbone.get(backbone, [])))
    else:
        result["by_backbone"] = {
            bb: _with_ci(bb, brecs) for bb, brecs in sorted(by_backbone.items())
        }
    return result


def cost_report(bank_records: list[dict]) -> dict:
    per_judge = defaultdict(lambda: {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cny": 0.0, "estimated_price": False})
    for r in bank_records:
        usage = r.get("usage") or {}
        p, c = int(usage.get("prompt", 0) or 0), int(usage.get("completion", 0) or 0)
        judge = r.get("judge", "unknown")
        row = per_judge[judge]
        row["calls"] += 1
        row["prompt_tokens"] += p
        row["completion_tokens"] += c
        row["cny"] += call_cost_cny(judge, p, c)
        row["estimated_price"] = row["estimated_price"] or price_for(judge)["estimated"]
    total_cny = sum(v["cny"] for v in per_judge.values())
    for v in per_judge.values():
        v["cny"] = round(v["cny"], 4)
    return {"per_judge": dict(per_judge), "total_cny": round(total_cny, 4)}


def panel_from_fit(fit_result: dict, *, backbone: str | None = None) -> dict:
    """{agent: winrate} for build_truth_board.py --panel, plus provenance.

    The reserved "_provenance" key carries the fit's protocol / rubric_hash /
    word_budget / backbone stamps into the panel file. The previous version
    stripped them, making --panel the only board input with ZERO provenance
    binding: any {agent: float} json could silently reorder tie-broken ranks
    and board.json recorded nothing about where the numbers came from
    (SPEC_ISSUES §2, presentation-panel entry). build_truth_board pops the key
    (agent lookups are unaffected) and publishes it as `panel_provenance`.
    """
    out: dict = {}
    if "agents" in fit_result:
        for agent, row in fit_result["agents"].items():
            out[agent] = row["winrate_vs_avg_opponent"]
    elif "by_backbone" in fit_result:
        choices = fit_result["by_backbone"]
        if backbone is None:
            raise ValueError(
                "panel output mixes multiple backbones; choose one explicitly"
            )
        if backbone not in choices:
            raise ValueError(f"backbone {backbone!r} is absent from fit result")
        for agent, row in choices[backbone]["agents"].items():
            out[agent] = row["winrate_vs_avg_opponent"]
    out["_provenance"] = {
        "protocol": fit_result.get("protocol"),
        "rubric_hash": fit_result.get("rubric_hash"),
        "word_budget": fit_result.get("word_budget"),
        "backbone": backbone,
        "generated_at": fit_result.get("generated_at"),
    }
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--staging", type=Path, default=None)
    ap.add_argument("--backbone", type=str, default=None)
    ap.add_argument("--judges", type=str, default=None,
                    help="CSV of judge model ids, or 'mock' for the built-in offline judge")
    ap.add_argument("--bank", type=Path, default=None)
    ap.add_argument("--order-audit", type=float, default=0.1)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--calibrate", type=int, default=None,
                    help="run K real battle-judge calls, print usage/cost, do NOT write to bank")
    # Default empty. It defaulted to "claude-code", so the documented plain
    # invocation silently dropped that lane from every pairwise battle: it had
    # no winrate and vanished from the arena ranking with no note anywhere.
    # Excluding a competitor is a decision, and it must be typed out.
    ap.add_argument("--exclude-agents", type=str, default="")
    ap.add_argument("--max-spend-cny", type=float, default=200.0)
    ap.add_argument("--fit", action="store_true")
    ap.add_argument("--bootstrap", type=int, default=200,
                    help="--fit: cluster-bootstrap resamples over tasks for 95%% CI (0 to disable)")
    ap.add_argument("--out", type=Path, default=None, help="--fit output path (BT json)")
    ap.add_argument("--panel-out", type=Path, default=None,
                    help="--fit: also write {agent: winrate} json for build_truth_board.py --panel")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--only-agent", type=str, default=None)
    ap.add_argument("--only-task", type=str, default=None)
    ap.add_argument("--supersede", action="store_true",
                    help="allow re-judging keys already in the bank (newest ts wins at fit time)")
    ap.add_argument("--tasks-dir", type=Path, default=DEFAULT_TASKS_DIR)
    ap.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    ap.add_argument("--word-budget", type=int, default=DEFAULT_WORD_BUDGET)
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--timeout-s", type=float, default=DEFAULT_TIMEOUT_S)
    ap.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    ap.add_argument("--cost-report", action="store_true",
                    help="print a cost report computed from --bank usage fields and exit")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    random.seed(args.seed)
    load_env_file(args.env_file)

    if args.cost_report:
        if not args.bank or not args.bank.exists():
            print("error: --cost-report needs an existing --bank", file=sys.stderr)
            return 2
        recs = list(load_bank(args.bank).values())
        print(json.dumps(cost_report(recs), indent=2, ensure_ascii=False))
        return 0

    if args.fit:
        if not args.bank or not args.bank.exists():
            print("error: --fit needs an existing --bank", file=sys.stderr)
            return 2
        judges_list = [j.strip() for j in args.judges.split(",")] if args.judges else None
        recs = list(load_bank(args.bank).values())
        result = fit_from_bank(recs, backbone=args.backbone, judges=judges_list,
                               bootstrap=args.bootstrap, seed=args.seed)
        out_path = args.out or Path("bt_result.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {out_path}")
        if args.panel_out:
            panel = panel_from_fit(result, backbone=args.backbone)
            args.panel_out.parent.mkdir(parents=True, exist_ok=True)
            args.panel_out.write_text(json.dumps(panel, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"wrote {args.panel_out}")
        print(json.dumps(result, indent=2, ensure_ascii=False)[:3000])
        return 0

    # --- battle-running paths (calibrate / dry-run / real run) ---
    if not args.staging or not args.backbone or not args.judges:
        print("error: --staging, --backbone, --judges are required unless --fit/--cost-report", file=sys.stderr)
        return 2

    exclude_agents = {a.strip() for a in args.exclude_agents.split(",") if a.strip()}
    judges = [j.strip() for j in args.judges.split(",") if j.strip()]

    task_agents = discover_staging(args.staging, args.backbone, exclude_agents)
    if not task_agents:
        print("error: no usable (non-stub) reports found under staging/backbone", file=sys.stderr)
        return 2

    plan = build_plan(
        task_agents, only_agent=args.only_agent, only_task=args.only_task,
        order_audit=args.order_audit, seed=args.seed,
    )

    existing = load_bank(args.bank) if args.bank and args.bank.exists() else {}

    # Expand plan x judges into concrete call units, skipping already-banked
    # keys unless --supersede was passed.
    calls = []
    for item in plan:
        for judge in judges:
            key = (
                PROTOCOL, args.backbone, item["task"], item["a"], item["b"],
                item["order"], judge, item["report_sha_a"], item["report_sha_b"],
            )
            if key in existing and not args.supersede:
                continue
            calls.append({**item, "judge": judge})

    n_pairs = len({(it["task"], it["a"], it["b"]) for it in plan})
    n_audited = len({(it["task"], it["a"], it["b"]) for it in plan if it["audited"]})
    est_cost = sum(
        call_cost_cny(c["judge"], EST_PROMPT_TOKENS, EST_COMPLETION_TOKENS)
        for c in calls if not c.get("walkover")
    )
    print(
        f"plan: {n_pairs} unordered pairs across {len(task_agents)} tasks "
        f"({n_audited} order-audited), {len(plan)} battle-order instances, "
        f"{len(judges)} judges -> {len(calls)} new judge calls needed "
        f"(estimated cost ¥{est_cost:.2f} at ~{EST_PROMPT_TOKENS}+{EST_COMPLETION_TOKENS} tok/call)"
    )

    if args.dry_run:
        return 0

    if args.calibrate is not None:
        sample = calls[: args.calibrate]
        if not sample:
            print("nothing to calibrate: plan already fully covered by bank (use --supersede to re-run)")
            return 0
        results = []
        for c in sample:
            try:
                intent = intent_for_battle(c["task"], args.tasks_dir,
                                           walkover=bool(c.get("walkover")))
            except FileNotFoundError as e:
                # Same guard as the real run: never judge an empty question.
                results.append({
                    "error": str(e), "judge": c["judge"],
                    "usage": {"prompt": 0, "completion": 0},
                })
                continue
            report_a = _report_text(task_agents[c["task"]][c["a"]])
            report_b = _report_text(task_agents[c["task"]][c["b"]])
            runner = walkover_record if c.get("walkover") else run_one_battle_judge
            kwargs = dict(
                backbone=args.backbone, task_id=c["task"], a=c["a"], b=c["b"], order=c["order"],
                judge=c["judge"], intent=intent,
                report_a=report_a, report_b=report_b, word_budget=args.word_budget,
            )
            if c.get("walkover"):
                kwargs.pop("intent")
            else:
                kwargs.update(max_tokens=args.max_tokens, timeout_s=args.timeout_s,
                              retries=args.retries)
            rec = runner(**kwargs)
            results.append(rec)
        n_ok = sum(1 for r in results if r["error"] is None)
        tot_p = sum(r["usage"]["prompt"] for r in results)
        tot_c = sum(r["usage"]["completion"] for r in results)
        tot_cost = sum(call_cost_cny(r["judge"], r["usage"]["prompt"], r["usage"]["completion"]) for r in results)
        print(json.dumps({
            "n_calibrate": len(results), "n_ok": n_ok, "n_error": len(results) - n_ok,
            "total_prompt_tokens": tot_p, "total_completion_tokens": tot_c,
            "avg_prompt_tokens": round(tot_p / len(results), 1) if results else 0,
            "avg_completion_tokens": round(tot_c / len(results), 1) if results else 0,
            "measured_cost_cny": round(tot_cost, 4),
            "projected_full_plan_cost_cny": round(
                (tot_cost / max(len(results), 1)) * len(calls), 2
            ) if calls else 0.0,
            "errors": [r["error"] for r in results if r["error"]],
        }, indent=2, ensure_ascii=False))
        print("(calibration battles NOT written to bank)")
        return 0

    # Real run: budget gate.
    if est_cost > args.max_spend_cny:
        print(
            f"error: estimated cost ¥{est_cost:.2f} exceeds --max-spend-cny {args.max_spend_cny}; "
            "refusing to start. Re-run with a higher --max-spend-cny, a smaller --only-task/--only-agent "
            "scope, or fewer judges.",
            file=sys.stderr,
        )
        return 3

    if not args.bank:
        print("error: --bank is required for a real run", file=sys.stderr)
        return 2

    n_written = 0
    n_error = 0

    def _do(c: dict) -> dict:
        # Raises task_intent_missing for a non-walkover battle with no task
        # file; the executor's error path below records the machine-readable
        # failure (which fit_from_bank filters out) instead of letting the
        # jury judge an empty question as clean data (SPEC_ISSUES G6).
        intent = intent_for_battle(c["task"], args.tasks_dir,
                                   walkover=bool(c.get("walkover")))
        report_a = _report_text(task_agents[c["task"]][c["a"]])
        report_b = _report_text(task_agents[c["task"]][c["b"]])
        common = dict(
            backbone=args.backbone, task_id=c["task"], a=c["a"], b=c["b"], order=c["order"],
            judge=c["judge"], report_a=report_a, report_b=report_b,
            word_budget=args.word_budget,
        )
        if c.get("walkover"):
            return walkover_record(**common)
        return run_one_battle_judge(
            **common, intent=intent, max_tokens=args.max_tokens,
            timeout_s=args.timeout_s, retries=args.retries,
        )

    with cf.ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as ex:
        futs = {ex.submit(_do, c): c for c in calls}
        for fut in cf.as_completed(futs):
            c = futs[fut]
            try:
                rec = fut.result()
            except Exception as e:
                rec = {
                    "ts": time.time(), "protocol": PROTOCOL, "rubric_hash": rubric_hash(),
                    "word_budget": args.word_budget, "backbone": args.backbone,
                    "task": c["task"], "a": c["a"], "b": c["b"], "order": c["order"],
                    "judge": c["judge"], "model_id": c["judge"],
                    "report_sha_a": c["report_sha_a"],
                    "report_sha_b": c["report_sha_b"], "walkover": c.get("walkover", False),
                    "q1": None, "q2": None, "q3": None, "q4": None, "winner": None,
                    "usage": {"prompt": 0, "completion": 0},
                    "error": f"{type(e).__name__}: {e}\n{traceback.format_exc()[-500:]}",
                }
            append_bank(args.bank, rec)
            n_written += 1
            if rec.get("error"):
                n_error += 1

    print(f"done: {n_written} records appended to {args.bank} ({n_error} errors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
