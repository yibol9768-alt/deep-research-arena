"""Smoke test for v4 verifiers — runs all four against a synthetic report.

Run on any machine:
    .venv-camel/bin/python scripts/smoke_v4_verifiers.py

What this checks
~~~~~~~~~~~~~~~~
* `source_diversity`   — pure deterministic, must produce a sensible
                         non-zero score and report 4 subscores.
* `perspective_balance`— Tier A (sentiment lexicon) must compute, Tier B
                         calls the LLM judge via call_judge which is
                         **stubbed** here so the smoke test runs offline.
* `factual_exactness`  — extracts atomic facts via call_judge_heavy
                         (stubbed) and verifies them against fake page
                         bodies (stubbed `_fetch_url`). Confirms the
                         deterministic-first path + LLM fallback both work.
* `internal_consistency` — clusters entities, calls call_judge_heavy
                         (stubbed) on sentence pairs. Confirms cluster
                         construction and aggregation arithmetic.

Exit code 0 if all four return a usable `VerifierResult`; non-zero with a
short error report otherwise.

The point of this smoke test is to catch import / signature / dataflow
breakage WITHOUT needing the sandbox or the DeepSeek API to be reachable.
For a *real* validation (with live sandbox and live judge), run
`scripts/score_deep_answer.py --task <task> --answer <report.md>` on
westd/WSL.
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# --- judge stubs (must be installed BEFORE importing the verifiers) -------

import src.verifiers.judge_client as judge_client  # noqa: E402

_REAL_CALL_JUDGE = judge_client.call_judge
_REAL_CALL_JUDGE_HEAVY = judge_client.call_judge_heavy


def _stub_call_judge(system: str, user: str, *, max_tokens: int = 2000, temperature: float = 0.2):
    """Cheap stub: scans the user prompt for cue words and returns a verdict.

    For perspective_balance Tier B: looks for negative-sentiment cues
    near the entity name. If any limitation-y phrase appears we PASS,
    otherwise FAIL.
    """
    low = user.lower()
    neg_cues = (
        "uncomfortable", "expensive", "overpriced", "complain",
        "limitation", "drawback", "issue", "problem", "lack",
        "criticized", "weakness", "weaker", "compromise",
    )
    if any(c in low for c in neg_cues):
        return "VERDICT: PASS", None
    return "VERDICT: FAIL", None


def _stub_call_judge_heavy(system: str, user: str, *, max_tokens: int = 4000, temperature: float = 0.0):
    """Cheap stub for the heavy judge.

    Routes by the system prompt's content:
      - factual_exactness extraction prompt (mentions 'atomic') → emit a
        tiny JSON array with one verifiable fact.
      - factual_exactness verification prompt (mentions 'VERDICT:
        SUPPORTED') → return SUPPORTED iff the value appears in the page.
      - internal_consistency NLI prompt (mentions 'CONTRADICT') → look for
        contradiction cues; otherwise NEUTRAL.
    """
    s_low = system.lower()
    if "atomic" in s_low and "extract" in s_low:
        # Emit one extracted fact whose source_url is the first http
        # link mentioned in the user prompt.
        import re as _re
        m = _re.search(r"https?://[^\s)]+", user)
        url = m.group(0) if m else "http://localhost:7770/example.html"
        # Try to pull a $-prefixed price as the value for a plausible test.
        m2 = _re.search(r"\$\s?\d+(?:\.\d+)?", user)
        value = m2.group(0) if m2 else "$299"
        fact = {
            "subject":    "Sony WH-1000XM5",
            "predicate":  "is priced at",
            "value":      value.replace(" ", ""),
            "value_type": "price",
            "source_url": url,
            "raw_span":   "Sony WH-1000XM5 is priced at " + value,
        }
        return json.dumps([fact]), None
    if "verdict: supported" in s_low or "verifies whether" in s_low:
        # Look at the page-text body: if value appears, SUPPORTED.
        import re as _re
        m = _re.search(r"value:\s*([^\n]+)", user, _re.IGNORECASE)
        if m:
            val = m.group(1).strip().lower()
            if val and val in user.lower().split("page text", 1)[-1]:
                return "VERDICT: SUPPORTED", None
        return "VERDICT: NOT_SUPPORTED", None
    if "contradict" in s_low and "neutral" in s_low:
        # NLI stub: look for cue keywords in the s1/s2 pair.
        low = user.lower()
        if ("best" in low and "worst" in low) or ("ranks first" in low and "ranks last" in low):
            return "VERDICT: CONTRADICT", None
        if "additionally" in low or "also" in low or "moreover" in low:
            return "VERDICT: AGREE", None
        return "VERDICT: NEUTRAL", None
    return "VERDICT: NEUTRAL", None


judge_client.call_judge = _stub_call_judge
judge_client.call_judge_heavy = _stub_call_judge_heavy

# Also stub the fetcher in factual_exactness — we don't want HTTP requests
# during the smoke test. We monkey-patch the module's _fetch_url to return
# canned bodies that the deterministic check can match against.
import src.verifiers.factual_exactness_verifier as fe_mod  # noqa: E402


_FAKE_PAGES = {
    "http://localhost:7770/sony-wh1000xm5.html": (
        "Sony WH-1000XM5 noise cancelling wireless headphones. "
        "Bluetooth 5.3 supported. Battery life up to 30 hours. "
        "Price: $399. Customer rating 4.7 stars based on 1,234 reviews."
    ),
    "http://localhost:9999/f/headphones/comments/42/sony-vs-bose": (
        "Sony WH-1000XM5 is much better than Bose for ANC at higher freqs. "
        "Bose is more comfortable though. Battery is similar."
    ),
    "http://localhost:8090/content/wikipedia_en_all_nopic/A/Bluetooth": (
        "Bluetooth 5.3 was released in 2021 and supports LE Audio."
    ),
}


def _stub_fetch(url: str):
    return url, _FAKE_PAGES.get(url, "Sample page text. Sony WH-1000XM5 review article. Price $299 mentioned in body.")


fe_mod._fetch_url = _stub_fetch

# Now safe to import the four verifiers.
from src.verifiers.source_diversity_verifier import SourceDiversityVerifier  # noqa: E402
from src.verifiers.perspective_balance_verifier import PerspectiveBalanceVerifier  # noqa: E402
from src.verifiers.factual_exactness_verifier import FactualExactnessVerifier  # noqa: E402
from src.verifiers.internal_consistency_verifier import InternalConsistencyVerifier  # noqa: E402
from src.scoring.leaderboard_composites import composite_v4, composite_v4_weights  # noqa: E402


# --- synthetic report ------------------------------------------------------

_REPORT = """# Consumer ANC Headphones Market Intelligence

## Product Landscape

### Sony WH-1000XM5

The [Sony WH-1000XM5](http://localhost:7770/sony-wh1000xm5.html) is the
flagship over-ear ANC headphone from Sony. Price is $399 with 4.7 star
rating from 1,234 customer reviews. It supports
[Bluetooth 5.3](http://localhost:8090/content/wikipedia_en_all_nopic/A/Bluetooth)
including LE Audio. Battery life is rated 30 hours. Sony has been criticized
for being uncomfortable for long sessions, and some users complain about
the somewhat bright treble tuning.

### Bose QC45

The Bose QC45 is the main competitor. It is widely considered the most
comfortable ANC headphone, but some users complain about the dated USB-C
charging and the lack of LDAC support. ANC depth is excellent at low
frequencies.

## Community Sentiment

On the [headphones subreddit](http://localhost:9999/f/headphones/comments/42/sony-vs-bose)
the community generally praises Sony WH-1000XM5 for ANC at higher
frequencies but criticizes its comfort. Bose QC45 is preferred for
long-haul flights despite its older feature set. Additionally, several
users complain that the Sony WH-1000XM5 sometimes has connection drops.

## Technical Context

Bluetooth 5.3 was released in 2021 and introduces LE Audio. Sony
WH-1000XM5 supports LDAC for higher-bitrate Bluetooth playback, which
the Bose QC45 lacks.

## Buying Guide

For pure ANC depth at high frequencies, Sony WH-1000XM5 is the leader.
For maximum comfort during long sessions, Bose QC45 ranks higher despite
the missing LDAC codec.
"""

_TASK_CONFIG: dict[str, Any] = {
    "sandbox_hosts": ["localhost:7770", "localhost:9999", "localhost:8090"],
    "url_coverage": {
        "per_domain_minimum": {
            "__SHOPPING__": 1,
            "__REDDIT__": 1,
            "__WIKIPEDIA__": 1,
        },
    },
    "evaluated_entities": ["Sony WH-1000XM5", "Bose QC45"],
}


# --- harness ---------------------------------------------------------------

def run_one(name: str, verifier, *, allow_score: tuple[float, float] = (0.0, 1.0)) -> bool:
    print(f"\n=== {name} ===")
    try:
        res = verifier.verify(task_config=_TASK_CONFIG, answer=_REPORT)
    except Exception as exc:
        print(f"  ERROR: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return False
    print(f"  score   = {res.score}")
    print(f"  passed  = {res.passed}")
    # Compact details preview (first 600 chars).
    blob = json.dumps(res.details, ensure_ascii=False, default=str)
    if len(blob) > 600:
        blob = blob[:600] + " ..."
    print(f"  details = {blob}")
    lo, hi = allow_score
    in_range = lo <= res.score <= hi
    print(f"  range_ok = {in_range}")
    return in_range


def main() -> int:
    print("v4 verifiers smoke test")
    print(f"answer chars: {len(_REPORT)}")
    print(f"v4 weights:   {composite_v4_weights()}")

    ok_sd = run_one("source_diversity",     SourceDiversityVerifier(),     allow_score=(0.0, 1.0))
    ok_pb = run_one("perspective_balance",  PerspectiveBalanceVerifier(),  allow_score=(0.0, 1.0))
    ok_fe = run_one("factual_exactness",    FactualExactnessVerifier(max_paragraphs=4, max_total_facts=10), allow_score=(0.0, 1.0))
    ok_ic = run_one("internal_consistency", InternalConsistencyVerifier(max_pairs_per_cluster=6, max_total_pairs=30), allow_score=(0.0, 1.0))

    # Sanity: composite_v4 must compute without crashing when given the
    # output dicts shaped like real score JSONs.
    print("\n=== composite_v4 sanity ===")
    sd  = SourceDiversityVerifier().verify(task_config=_TASK_CONFIG, answer=_REPORT)
    pb  = PerspectiveBalanceVerifier().verify(task_config=_TASK_CONFIG, answer=_REPORT)
    fe  = FactualExactnessVerifier(max_paragraphs=4, max_total_facts=10).verify(task_config=_TASK_CONFIG, answer=_REPORT)
    ic  = InternalConsistencyVerifier(max_pairs_per_cluster=6, max_total_pairs=30).verify(task_config=_TASK_CONFIG, answer=_REPORT)
    composite_input = {
        "url_reachability":     {"score": 0.9},
        "url_coverage":         {"score": 0.7},
        "quote_match":          {"score": 0.6},
        "checklist":            {"pass_rate": 0.7},
        "markdown_spec":        {"words_ok": True, "citations_ok": True, "paragraphs_ok": True},
        "citation_alignment":   {"score": 0.55},
        "analysis_depth":       {"score": 0.5},
        "presentation":         {"score": 0.8},
        "source_diversity":     {"score": sd.score},
        "perspective_balance":  {"score": pb.score},
        "factual_exactness":    {"score": fe.score},
        "internal_consistency": {"score": ic.score},
    }
    v4 = composite_v4(composite_input)
    print(f"  composite_v4 = {v4:.4f}")
    ok_v4 = 0.0 <= v4 <= 1.0

    all_ok = all([ok_sd, ok_pb, ok_fe, ok_ic, ok_v4])
    print("\n=== summary ===")
    print(f"  source_diversity       {'PASS' if ok_sd else 'FAIL'}")
    print(f"  perspective_balance    {'PASS' if ok_pb else 'FAIL'}")
    print(f"  factual_exactness      {'PASS' if ok_fe else 'FAIL'}")
    print(f"  internal_consistency   {'PASS' if ok_ic else 'FAIL'}")
    print(f"  composite_v4           {'PASS' if ok_v4 else 'FAIL'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
