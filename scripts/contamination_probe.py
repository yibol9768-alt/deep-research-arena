#!/usr/bin/env python3
"""Contamination probe for the Deep Research Arena (eval problem #5).

Goal
----
Verify that a *base* model cannot answer the cross-site deep-research tasks
*closed-book* (no retrieval, no tools, answering only from its own parametric
knowledge). If it could, the benchmark would be measuring memorization of the
sandbox corpus rather than genuine research / retrieval+grounding ability.

The sandbox corpus is PRIVATE: the One Stop Market product catalog, the Postmill
(Reddit-like) threads, and the served Wikipedia snapshot all live on
``localhost`` hosts and are not on the public web. The model therefore *cannot*
know the specific product pages, prices, thread scores, or URLs. A faithful
closed-book answer should be generic and/or should abstain. The EXPECTED and
HEALTHY result is that the base model FAILS to produce the sandbox-specific
answers closed-book.

What this script does
---------------------
For a sample of tasks (read from ``data/tasks/deep_research/cross_site_deep/``):

  1. Build a closed-book prompt that strips the sandbox placeholders
     (``__SHOPPING__`` etc.) and explicitly instructs the model: no tools, no
     browsing, answer only from your own knowledge, and self-report a
     confidence score in [0, 1].

  2. Ask the base model (Bailian / DashScope ``qwen3-30b-a3b-instruct-2507`` by
     default, OpenAI-compatible endpoint).

  3. Score the closed-book answer against the task's *golden* sandbox facts
     (loaded from ``data/golden/deep/<task_id>.json``):
       - ``sandbox_url_hits``     : count of verbatim sandbox URLs leaked.
       - ``sandbox_host_hits``    : count of sandbox hostnames mentioned.
       - ``invented_price_count`` : count of concrete price tokens emitted
                                     (inventing $-prices => guessing => bad).
       - ``golden_price_matches`` : how many of those prices match golden prices
                                     (a real memorization signal).
       - ``closed_book_specificity`` : a 0..1 score; HIGH = the answer asserts
                                     specific sandbox-shaped facts it could not
                                     legitimately know (a contamination red
                                     flag). LOW = generic / abstaining (healthy).
       - ``can_answer`` (coarse flag): did the model claim it can produce the
                                     concrete report, or did it abstain?

  4. Emit a per-task JSON result and a human-readable verdict, and write
     ``docs/CONTAMINATION_REPORT.md``.

Usage
-----
    source /root/.config/dra/bailian.env   # sets DASHSCOPE_API_KEY + _BASE_URL
    python3 scripts/contamination_probe.py --num-tasks 5

    # Offline (no network), deterministic canned answers for plumbing checks:
    python3 scripts/contamination_probe.py --dry-run --num-tasks 5

Environment
-----------
    DASHSCOPE_API_KEY   - Bailian/DashScope API key (required unless --dry-run)
    DASHSCOPE_BASE_URL  - OpenAI-compatible base URL (required unless --dry-run)

The API key is never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep"
GOLDEN_DIR = ROOT / "data" / "golden" / "deep"
REPORT_PATH = ROOT / "docs" / "CONTAMINATION_REPORT.md"

DEFAULT_MODEL = "qwen3-30b-a3b-instruct-2507"

# Sandbox host fingerprints. These hostnames only resolve inside the private
# sandbox, so a closed-book base model has no legitimate way to know them.
SANDBOX_HOSTS = ("localhost:7770", "localhost:9999", "localhost:8090",
                 "localhost:7780", "localhost:3000", "127.0.0.1:7770")

# Placeholder tokens used in task intents; we replace them with neutral words
# so the closed-book prompt never hands the sandbox identity to the model.
PLACEHOLDER_RE = re.compile(r"__([A-Z]+)__")

# Concrete price token, e.g. "$16.99" or "$1,299". Inventing these in a
# closed-book answer is a guessing / fabrication signal.
PRICE_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d{1,2})?")

# Phrases that signal the model is (correctly) abstaining / refusing to invent
# specific sandbox facts.
ABSTAIN_MARKERS = (
    "i cannot", "i can't", "i do not have", "i don't have", "without access",
    "cannot provide specific", "unable to", "no access to", "i'm not able",
    "i am not able", "cannot browse", "do not have access", "would need to",
    "i don't know", "i do not know", "cannot verify", "general information",
    "as a language model", "cannot retrieve", "not have real-time",
    "no way to know", "cannot access", "hypothetical", "illustrative",
)


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #


@dataclass
class TaskFacts:
    """Sandbox-specific facts extracted from a task's golden file."""

    task_id: str
    topic: str
    sandbox_urls: list[str] = field(default_factory=list)
    golden_prices: set[str] = field(default_factory=set)


@dataclass
class ProbeResult:
    """Per-task probe outcome."""

    task_id: str
    topic: str
    answer_chars: int
    self_reported_confidence: Optional[float]
    sandbox_url_hits: int
    sandbox_host_hits: int
    invented_price_count: int
    golden_price_matches: int
    abstained: bool
    can_answer: bool
    closed_book_specificity: float
    verdict: str
    answer_excerpt: str = ""


# --------------------------------------------------------------------------- #
# Task / golden loading
# --------------------------------------------------------------------------- #


def extract_topic(intent: str) -> str:
    """Pull the human topic phrase out of a deep-research intent string."""
    m = re.search(r"report on (.+?),\s*spanning", intent)
    if m:
        return m.group(1).strip()
    m = re.search(r"report on (.+?)\.", intent)
    if m:
        return m.group(1).strip()
    # Fall back to the first sentence.
    return intent.split(".")[0][:120].strip()


def neutralize_intent(intent: str) -> str:
    """Strip sandbox placeholders + URLs so the prompt cannot leak sandbox id.

    We replace ``__SHOPPING__`` -> "an online store", ``__REDDIT__`` -> "a
    community forum", ``__WIKIPEDIA__`` -> "an encyclopedia", and remove any
    explicit ``localhost`` URLs. The point is to ask the model the *research
    question* without telling it which private corpus to mine.
    """
    mapping = {
        "SHOPPING": "an online store",
        "REDDIT": "a community forum",
        "WIKIPEDIA": "an encyclopedia",
        "WIKI": "an encyclopedia",
    }

    def _sub(m: re.Match) -> str:
        return mapping.get(m.group(1), m.group(1).lower())

    text = PLACEHOLDER_RE.sub(_sub, intent)
    # Drop any leftover sandbox host references just in case.
    for host in SANDBOX_HOSTS:
        text = text.replace(host, "the source")
    text = re.sub(r"https?://[^\s)`]+", "(a source url)", text)
    return text


def load_tasks(num_tasks: int, task_ids: Optional[list[str]] = None) -> list[dict]:
    """Load up to ``num_tasks`` task JSONs (or the explicit ``task_ids``)."""
    if task_ids:
        paths = [TASKS_DIR / f"{tid}.json" for tid in task_ids]
    else:
        paths = sorted(
            p for p in TASKS_DIR.glob("dr_cross_deep_*.json")
            if re.match(r"dr_cross_deep_\d+\.json$", p.name)
        )[:num_tasks]
    tasks = []
    for p in paths:
        if not p.exists():
            print(f"[warn] task file missing: {p}", file=sys.stderr)
            continue
        tasks.append(json.loads(p.read_text()))
    return tasks


def load_task_facts(task: dict) -> TaskFacts:
    """Build the :class:`TaskFacts` for a task from its golden file."""
    task_id = task["task_id"]
    topic = extract_topic(task.get("intent", ""))
    facts = TaskFacts(task_id=task_id, topic=topic)

    golden_path = GOLDEN_DIR / f"{task_id}.json"
    if not golden_path.exists():
        return facts
    try:
        golden = json.loads(golden_path.read_text())
    except (json.JSONDecodeError, OSError):
        return facts

    for entry in golden.get("must_cite_urls", []):
        url = entry.get("url")
        if url:
            facts.sandbox_urls.append(url)
        why = entry.get("why") or ""
        for price in PRICE_RE.findall(why):
            facts.golden_prices.add(_norm_price(price))
    # Also harvest prices from triples if present.
    for tri in golden.get("triples", []):
        if isinstance(tri, dict):
            obj = str(tri.get("object", ""))
            for price in PRICE_RE.findall(obj):
                facts.golden_prices.add(_norm_price(price))
    return facts


def _norm_price(price: str) -> str:
    """Canonicalize a price token for comparison (strip spaces/commas)."""
    return price.replace(" ", "").replace(",", "")


# --------------------------------------------------------------------------- #
# Prompt construction
# --------------------------------------------------------------------------- #


CLOSED_BOOK_SYSTEM = (
    "You are answering CLOSED-BOOK. You have NO tools, NO web browsing, NO "
    "retrieval, and NO access to any database, store, forum, or encyclopedia. "
    "Answer ONLY from your own internal knowledge. Do NOT invent specific "
    "product pages, prices, URLs, review counts, or forum thread scores: if you "
    "do not actually know a specific fact, say so plainly rather than guessing. "
    "It is correct and expected to abstain on specifics you cannot know."
)


def build_closed_book_prompt(facts: TaskFacts, neutral_intent: str) -> str:
    """Compose the closed-book user prompt for a single task."""
    return (
        "TASK (closed-book, no tools):\n"
        f"{neutral_intent}\n\n"
        "INSTRUCTIONS:\n"
        "1. Answer the above as best you can WITHOUT any tools or browsing, "
        "using only your own knowledge.\n"
        "2. If the task asks for specific product URLs, prices, ratings, forum "
        "thread scores, or encyclopedia article URLs that you cannot actually "
        "know without browsing, DO NOT fabricate them. State clearly that you "
        "cannot provide them closed-book.\n"
        "3. On the LAST line, output exactly:\n"
        "   CONFIDENCE: <number between 0 and 1>\n"
        "   where the number is your self-assessed probability that your answer "
        "contains the SPECIFIC, correct, sourced facts the task demands "
        "(specific real product pages, prices, and URLs). Be honest: if you are "
        "only giving generic guidance, this should be low."
    )


# --------------------------------------------------------------------------- #
# Model backend
# --------------------------------------------------------------------------- #


def make_dry_run_answer(facts: TaskFacts) -> str:
    """Deterministic canned closed-book answer for --dry-run / offline tests.

    Mimics a *healthy* base-model response: generic guidance plus an explicit
    abstention on the sandbox specifics, and a low confidence. This keeps the
    plumbing (parsing, scoring, reporting) exercisable with no network.
    """
    return (
        f"# {facts.topic.title()}: General Overview (closed-book)\n\n"
        "I cannot browse any store, forum, or encyclopedia, so I do not have "
        "access to the specific product pages, prices, review counts, or forum "
        "thread scores this task requests. Below is generic, well-known "
        "background information only.\n\n"
        f"In general, {facts.topic} spans a range of products and price tiers. "
        "Buyers typically weigh build quality, feature set, and reviews. "
        "Common technical concepts apply, but I cannot provide specific sourced "
        "URLs or verified prices without retrieval.\n\n"
        "I am not able to enumerate the exact catalog or cite real source URLs "
        "closed-book; doing so would require browsing.\n\n"
        "CONFIDENCE: 0.03\n"
    )


def call_model(prompt: str, system: str, model: str,
               max_tokens: int = 1200, temperature: float = 0.2) -> str:
    """Call the OpenAI-compatible Bailian/DashScope endpoint.

    Reads ``DASHSCOPE_API_KEY`` and ``DASHSCOPE_BASE_URL`` from the environment.
    The key is never printed.
    """
    try:
        from openai import OpenAI
    except ImportError:  # pragma: no cover - environment guard
        sys.exit("openai SDK not installed. pip install openai")

    base_url = os.environ.get("DASHSCOPE_BASE_URL")
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not base_url or not api_key:
        sys.exit(
            "Set DASHSCOPE_API_KEY and DASHSCOPE_BASE_URL "
            "(source /root/.config/dra/bailian.env)."
        )

    client = OpenAI(base_url=base_url, api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    return resp.choices[0].message.content or ""


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #


def parse_confidence(answer: str) -> Optional[float]:
    """Extract the self-reported ``CONFIDENCE: <x>`` value, if present."""
    matches = re.findall(r"CONFIDENCE:\s*([0-9]*\.?[0-9]+)", answer, re.IGNORECASE)
    if not matches:
        return None
    try:
        val = float(matches[-1])
    except ValueError:
        return None
    # Normalize to [0, 1]. Some models emit percentages (e.g. "85"); a value
    # just above 1 (e.g. "1.5") is treated as a typo and clamped, while a value
    # clearly in percentage range (> 2) is scaled by 100.
    if val > 2.0:
        val = val / 100.0
    return max(0.0, min(1.0, val))


def detect_abstention(answer: str) -> bool:
    """True if the answer plainly abstains from inventing sandbox specifics."""
    low = answer.lower()
    return any(marker in low for marker in ABSTAIN_MARKERS)


def score_answer(answer: str, facts: TaskFacts) -> ProbeResult:
    """Score a closed-book answer against a task's sandbox facts.

    ``closed_book_specificity`` in [0, 1]: HIGH means the answer asserts
    specific sandbox-shaped facts it could not legitimately know (contamination
    / memorization red flag). LOW means generic / abstaining (the healthy
    outcome).
    """
    low = answer.lower()

    # Verbatim leaked sandbox URLs (strongest contamination signal).
    sandbox_url_hits = sum(1 for u in facts.sandbox_urls if u and u in answer)

    # Sandbox hostnames mentioned at all.
    sandbox_host_hits = sum(1 for h in SANDBOX_HOSTS if h in low)

    # Concrete price tokens the model emitted.
    emitted_prices = [_norm_price(p) for p in PRICE_RE.findall(answer)]
    invented_price_count = len(emitted_prices)
    golden_price_matches = sum(1 for p in emitted_prices if p in facts.golden_prices)

    abstained = detect_abstention(answer)
    confidence = parse_confidence(answer)

    # Coarse "can it answer?" flag: the model claims to deliver the concrete
    # sourced report iff it leaked a sandbox URL/host, OR matched MULTIPLE
    # golden prices, OR did not abstain while self-reporting high confidence.
    # A lone golden-price match alongside an explicit abstention is treated as
    # a coincidence (a single generic "$X" that happened to match), not as
    # evidence the model can answer.
    high_conf = confidence is not None and confidence >= 0.5
    can_answer = bool(
        sandbox_url_hits > 0
        or sandbox_host_hits > 0
        or golden_price_matches >= 2
        or (golden_price_matches == 1 and not abstained)
        or (not abstained and high_conf)
    )

    # Composite specificity score in [0, 1]. Each contamination signal pushes it
    # up; an explicit abstention pulls it down.
    specificity = 0.0
    specificity += min(1.0, sandbox_url_hits * 0.5)          # leaked URLs: huge
    specificity += min(0.3, sandbox_host_hits * 0.15)        # host mentions
    specificity += min(0.4, golden_price_matches * 0.2)      # matched golden $
    specificity += min(0.15, invented_price_count * 0.03)    # any invented $
    if not abstained:
        specificity += 0.1
    if abstained:
        specificity -= 0.1
    specificity = max(0.0, min(1.0, specificity))

    # Per-task verdict.
    if sandbox_url_hits > 0 or golden_price_matches >= 2:
        verdict = "CONTAMINATED"
    elif specificity >= 0.5 or (can_answer and not abstained):
        verdict = "SUSPICIOUS"
    else:
        verdict = "CLEAN"

    excerpt = answer.strip().replace("\n", " ")
    if len(excerpt) > 280:
        excerpt = excerpt[:280] + "..."

    return ProbeResult(
        task_id=facts.task_id,
        topic=facts.topic,
        answer_chars=len(answer),
        self_reported_confidence=confidence,
        sandbox_url_hits=sandbox_url_hits,
        sandbox_host_hits=sandbox_host_hits,
        invented_price_count=invented_price_count,
        golden_price_matches=golden_price_matches,
        abstained=abstained,
        can_answer=can_answer,
        closed_book_specificity=round(specificity, 3),
        verdict=verdict,
        answer_excerpt=excerpt,
    )


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def run_probe(tasks: list[dict], model: str,
              answer_fn: Callable[[TaskFacts, str], str]) -> list[ProbeResult]:
    """Probe each task and return scored results.

    ``answer_fn`` maps ``(facts, neutral_intent) -> raw_answer_text``. The CLI
    wires this to either the live model or the dry-run generator; tests inject a
    mock here.
    """
    results: list[ProbeResult] = []
    for task in tasks:
        facts = load_task_facts(task)
        neutral = neutralize_intent(task.get("intent", ""))
        answer = answer_fn(facts, neutral)
        result = score_answer(answer, facts)
        results.append(result)
    return results


def aggregate_verdict(results: list[ProbeResult]) -> dict:
    """Summarize per-task results into an overall verdict for the eval."""
    n = len(results)
    contaminated = [r for r in results if r.verdict == "CONTAMINATED"]
    suspicious = [r for r in results if r.verdict == "SUSPICIOUS"]
    clean = [r for r in results if r.verdict == "CLEAN"]
    mean_spec = round(sum(r.closed_book_specificity for r in results) / n, 3) if n else 0.0
    confs = [r.self_reported_confidence for r in results
             if r.self_reported_confidence is not None]
    mean_conf = round(sum(confs) / len(confs), 3) if confs else None
    total_url_leaks = sum(r.sandbox_url_hits for r in results)
    total_price_matches = sum(r.golden_price_matches for r in results)

    if contaminated:
        overall = "FAIL_CONTAMINATION_DETECTED"
        headline = (
            "Contamination detected: the base model reproduced sandbox-specific "
            "facts closed-book. The eval may be measuring memorization."
        )
    elif len(suspicious) > n / 2:
        overall = "WARN_HIGH_SPECIFICITY"
        headline = (
            "Caution: many closed-book answers were specific (not abstaining). "
            "No verbatim sandbox facts leaked, but specificity is elevated."
        )
    else:
        overall = "PASS_NO_MEMORIZATION"
        headline = (
            "Healthy: the base model CANNOT produce the sandbox-specific answers "
            "closed-book. The eval measures retrieval+grounding, not memorization."
        )

    return {
        "overall": overall,
        "headline": headline,
        "n_tasks": n,
        "n_contaminated": len(contaminated),
        "n_suspicious": len(suspicious),
        "n_clean": len(clean),
        "mean_closed_book_specificity": mean_spec,
        "mean_self_reported_confidence": mean_conf,
        "total_sandbox_url_leaks": total_url_leaks,
        "total_golden_price_matches": total_price_matches,
    }


# --------------------------------------------------------------------------- #
# Report rendering
# --------------------------------------------------------------------------- #


def _no_emdash(text: str) -> str:
    """Replace em/en dashes with a hyphen so the generated doc has no em-dash.

    Topic strings and answer excerpts are quoted from upstream task data and the
    model, which may contain em-dashes; the rendered report must not.
    """
    return text.replace("-", "-").replace("–", "-")


def render_report(results: list[ProbeResult], summary: dict, *,
                  model: str, dry_run: bool) -> str:
    """Render docs/CONTAMINATION_REPORT.md content as a string."""
    lines: list[str] = []
    a = lines.append

    a("# Contamination Probe Report (Eval Problem #5)")
    a("")
    a("## What this checks")
    a("")
    a("This probe verifies that a *base* model cannot answer the cross-site "
      "deep-research tasks **closed-book** (no retrieval, no tools). The "
      "sandbox corpus (One Stop Market products, Postmill forum threads, the "
      "served Wikipedia snapshot) is **private**: it lives on `localhost` "
      "hosts and is not on the public web. A base model therefore has no "
      "legitimate way to know the specific product pages, prices, thread "
      "scores, or URLs. We ask the model the research question closed-book, "
      "with placeholders neutralized so it is never told which private corpus "
      "to mine, and we check whether the answer asserts sandbox-specific facts "
      "anyway.")
    a("")
    a("The **EXPECTED and HEALTHY** result is that the base model **cannot** "
      "produce the sandbox-specific answers closed-book. That confirms the "
      "benchmark measures **retrieval + grounding**, not memorization.")
    a("")
    a(f"- Probe model: `{model}`" + (" (DRY-RUN / mocked)" if dry_run else " (Bailian / DashScope)"))
    a(f"- Tasks probed: {summary['n_tasks']}")
    a("")
    a("## Scoring legend")
    a("")
    a("- `closed_book_specificity` in [0,1]: HIGH = the closed-book answer "
      "asserts specific sandbox-shaped facts it could not legitimately know "
      "(red flag); LOW = generic / abstaining (healthy).")
    a("- `can_answer` (coarse): did the model claim it can deliver the concrete "
      "sourced report (leaked a sandbox URL/host, matched a golden price, or "
      "stayed confident without abstaining)?")
    a("- `url_leaks`: verbatim sandbox URLs reproduced (strongest signal).")
    a("- `golden_$`: emitted prices that match the task's golden prices.")
    a("- `inv_$`: total concrete `$` price tokens emitted (any guessing).")
    a("- Per-task verdict: `CLEAN` (healthy), `SUSPICIOUS` (specific but no "
      "verbatim leak), `CONTAMINATED` (leaked sandbox facts).")
    a("")
    a("## Overall verdict")
    a("")
    a(f"**{summary['overall']}** - {summary['headline']}")
    a("")
    a(f"- Clean: {summary['n_clean']} / {summary['n_tasks']}")
    a(f"- Suspicious: {summary['n_suspicious']} / {summary['n_tasks']}")
    a(f"- Contaminated: {summary['n_contaminated']} / {summary['n_tasks']}")
    a(f"- Mean closed-book specificity: {summary['mean_closed_book_specificity']}")
    a(f"- Mean self-reported confidence: {summary['mean_self_reported_confidence']}")
    a(f"- Total verbatim sandbox URL leaks: {summary['total_sandbox_url_leaks']}")
    a(f"- Total golden-price matches: {summary['total_golden_price_matches']}")
    a("")
    a("## Per-task results")
    a("")
    a("| task_id | topic | conf | spec | can_ans | abstain | url_leaks | golden_$ | inv_$ | verdict |")
    a("|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        conf = "n/a" if r.self_reported_confidence is None else f"{r.self_reported_confidence:.2f}"
        topic = _no_emdash(r.topic if len(r.topic) <= 40 else r.topic[:37] + "...")
        a(f"| {r.task_id} | {topic} | {conf} | {r.closed_book_specificity:.2f} "
          f"| {'yes' if r.can_answer else 'no'} | {'yes' if r.abstained else 'no'} "
          f"| {r.sandbox_url_hits} | {r.golden_price_matches} "
          f"| {r.invented_price_count} | {r.verdict} |")
    a("")
    a("## Per-task answer excerpts")
    a("")
    for r in results:
        a(f"### {r.task_id} - {_no_emdash(r.topic)}")
        a("")
        a(f"- specificity={r.closed_book_specificity:.2f}, "
          f"can_answer={r.can_answer}, abstained={r.abstained}, "
          f"confidence={r.self_reported_confidence}")
        a(f"- excerpt: {_no_emdash(r.answer_excerpt)}")
        a("")
    a("## Interpretation")
    a("")
    a("A `PASS_NO_MEMORIZATION` verdict means: across the probed tasks, the "
      "base model did not reproduce any verbatim sandbox URLs and did not match "
      "the golden prices; its closed-book answers were generic and/or "
      "abstaining. This is the desired outcome. It confirms that scoring well "
      "on these tasks requires actually retrieving from and grounding in the "
      "sandbox corpus, so the benchmark measures research ability rather than "
      "memorization of leaked data.")
    a("")
    a("A `WARN_HIGH_SPECIFICITY` or `FAIL_CONTAMINATION_DETECTED` verdict would "
      "indicate the opposite and should trigger a corpus-privacy / data-leak "
      "investigation.")
    a("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--num-tasks", type=int, default=5,
                    help="number of tasks to probe (default: 5)")
    ap.add_argument("--task-ids", nargs="*", default=None,
                    help="explicit task ids to probe (overrides --num-tasks)")
    ap.add_argument("--model", default=os.environ.get("PROBE_MODEL", DEFAULT_MODEL),
                    help=f"model name (default: {DEFAULT_MODEL})")
    ap.add_argument("--dry-run", action="store_true",
                    help="offline: use canned answers, never hit the network")
    ap.add_argument("--report-path", default=str(REPORT_PATH),
                    help="where to write the markdown report")
    ap.add_argument("--json-out", default=None,
                    help="optional path to also dump per-task results as JSON")
    args = ap.parse_args(argv)

    tasks = load_tasks(args.num_tasks, args.task_ids)
    if not tasks:
        print("[error] no tasks loaded", file=sys.stderr)
        return 2

    if args.dry_run:
        def answer_fn(facts: TaskFacts, neutral: str) -> str:
            return make_dry_run_answer(facts)
        mode = "dry-run"
    else:
        def answer_fn(facts: TaskFacts, neutral: str) -> str:
            prompt = build_closed_book_prompt(facts, neutral)
            return call_model(prompt, CLOSED_BOOK_SYSTEM, args.model)
        mode = "live"

    print(f"[probe] mode={mode} model={args.model} tasks={len(tasks)}")
    results = run_probe(tasks, args.model, answer_fn)
    summary = aggregate_verdict(results)

    report = render_report(results, summary, model=args.model, dry_run=args.dry_run)
    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report)
    print(f"[probe] wrote report -> {report_path}")

    if args.json_out:
        payload = {
            "summary": summary,
            "results": [asdict(r) for r in results],
        }
        Path(args.json_out).write_text(json.dumps(payload, indent=2))
        print(f"[probe] wrote json -> {args.json_out}")

    # Console summary.
    print(f"[probe] OVERALL: {summary['overall']} - {summary['headline']}")
    for r in results:
        print(f"  {r.task_id}: verdict={r.verdict} "
              f"spec={r.closed_book_specificity:.2f} "
              f"can_answer={r.can_answer} url_leaks={r.sandbox_url_hits} "
              f"golden_$={r.golden_price_matches} "
              f"conf={r.self_reported_confidence}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
