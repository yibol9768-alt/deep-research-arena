"""Score one or more deep-tier agent answers against the deep golden.

Combines:
  - URLCoverageVerifier  (deterministic: must-cite / pool / domain balance)
  - gpt-5-chat judge     (checklist verdicts via judge_client.py)
  - markdown spec checks (word count, citation count, paragraphs)

Usage:
    python3 scripts/score_deep_answer.py \
        --task dr_cross_deep_0001 \
        --answer data/results/deep/gpt-researcher__dr_cross_deep_0001_smoke.md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.verifiers.url_coverage_verifier import URLCoverageVerifier  # noqa: E402
from src.verifiers.url_reachability_verifier import URLReachabilityVerifier  # noqa: E402
from src.verifiers.quote_match_verifier import QuoteMatchVerifier  # noqa: E402
from src.verifiers.claim_nli_verifier import ClaimNLIVerifier  # noqa: E402
from src.verifiers.judge_client import call_judge, judge_identity     # noqa: E402


_MD_LINK_RE = re.compile(r"\[[^\]]*\]\([^)]+\)")


def _word_count(md: str) -> int:
    text = re.sub(r"\[([^\]]*)\]\([^)]+\)", r"\1", md)
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"[#>*_~]", " ", text)
    return len([w for w in text.split() if w])


def _citation_count(md: str) -> int:
    return len(_MD_LINK_RE.findall(md))


def _paragraph_count(md: str) -> int:
    return len([p for p in re.split(r"\n\s*\n", md) if len(p.strip()) > 30])


def _markdown_spec_score(md: str, spec: dict) -> dict:
    wc = _word_count(md)
    cc = _citation_count(md)
    pc = _paragraph_count(md)
    return {
        "word_count":      wc,
        "min_words":       spec.get("min_words", 0),
        "max_words":       spec.get("max_words", 100000),
        "words_ok":        spec.get("min_words", 0) <= wc <= spec.get("max_words", 100000),
        "citation_count":  cc,
        "min_citations":   spec.get("min_citations", 0),
        "citations_ok":    cc >= spec.get("min_citations", 0),
        "paragraph_count": pc,
        "min_paragraphs":  spec.get("min_paragraphs", 0),
        "paragraphs_ok":   pc >= spec.get("min_paragraphs", 0),
    }


def _is_degenerate_answer(answer: str) -> tuple[bool, str]:
    """Wrapper around `src.verifiers.base.is_degenerate_answer` so the
    checklist judge shares one rule with all the LLM-based verifiers."""
    from src.verifiers.base import is_degenerate_answer
    return is_degenerate_answer(answer, min_words=50, require_citations=True)


_GROUNDING_KEYWORDS_RE = re.compile(
    r"\b(URL|URLs|cite|cited|cites|citation|citations|linked|markdown-linked|"
    r"distinct|reachable|sandbox|domain|domains|reddit|wikipedia|shopping|"
    r"thread|threads|article|articles|page|pages|forum|forums)\b",
    re.I,
)


def _criterion_requires_grounding(criterion_text: str) -> bool:
    """Heuristic: does this checklist item depend on real cited URLs?

    Used to downgrade PASS verdicts on grounding-dependent criteria when
    `url_reachability` says the agent's URLs don't actually resolve. Catches
    the gpt-researcher 0009 failure mode (judge says PASS on text that's
    well-written but cites 93 fabricated URLs).
    """
    return bool(_GROUNDING_KEYWORDS_RE.search(criterion_text or ""))


def _judge_checklist(
    checklist: list[str],
    answer: str,
    task_id: str,
    *,
    reachability: float | None = None,
    fab_threshold: float = 0.30,
) -> dict:
    if not checklist:
        return {"verdicts": [], "pass_rate": 0.0, "judge_error": "no checklist"}

    # Deterministic guard: don't waste an LLM call on degenerate output.
    # A lenient judge (DeepSeek-V4-flash observed) will return PASS for
    # all criteria when fed an empty answer; that gameable behaviour is
    # the bug we are fixing.
    degenerate, why = _is_degenerate_answer(answer)
    if degenerate:
        verdicts = ["FAIL"] * len(checklist)
        return {
            "verdicts": list(zip(checklist, verdicts)),
            "pass_count": 0,
            "fail_count": len(checklist),
            "unclear_count": 0,
            "pass_rate": 0.0,
            "judge_error": None,
            "skipped_judge": True,
            "skip_reason": why,
        }

    system = (
        "You are an impartial evaluator scoring a deep-research report. "
        "For each criterion, output exactly one of: PASS, FAIL, UNCLEAR. "
        "Output one verdict per line in order, no preamble, no commentary.\n\n"
        "Decision rules:\n"
        "  * PASS only if the report contains explicit textual evidence for the criterion.\n"
        "  * If the report is empty, a placeholder (e.g. '(empty ... output)'), an error "
        "message, or under ~200 words, output FAIL for ALL criteria.\n"
        "  * If a criterion requires specific URLs / citations / counts and the report does "
        "not show them, FAIL.\n"
        "  * UNCLEAR is reserved for genuinely ambiguous cases."
    )
    numbered = "\n".join(f"{i+1}. {c}" for i, c in enumerate(checklist))
    user = (
        f"# Task: {task_id}\n\n"
        f"# Criteria\n{numbered}\n\n"
        f"# Agent Answer (truncated to 32k chars below; treat empty/placeholder as FAIL-all)\n"
        f"{answer[:32000]}\n\n"
        f"# Your output: {len(checklist)} lines, each PASS/FAIL/UNCLEAR."
    )
    text, err = call_judge(system=system, user=user, max_tokens=600, temperature=0.0)
    if err:
        return {"verdicts": [], "pass_rate": 0.0, "judge_error": err}

    raw = (text or "").strip().splitlines()
    verdicts: list[str] = []
    for line in raw:
        line = line.strip().rstrip(".")
        line = re.sub(r"^\d+[.)]\s*", "", line)
        m = re.search(r"\b(PASS|FAIL|UNCLEAR)\b", line, re.I)
        if m:
            verdicts.append(m.group(1).upper())
        if len(verdicts) >= len(checklist):
            break
    while len(verdicts) < len(checklist):
        verdicts.append("UNCLEAR")

    # Sanity floor: a 21/21 PASS on a near-empty answer is the bug
    # signature. If the answer is short AND every verdict is PASS, the
    # judge is hallucinating — downgrade to FAIL. Threshold is set well
    # above the degenerate cutoff so genuinely strong answers are unaffected.
    if all(v == "PASS" for v in verdicts) and _word_count(answer) < 500:
        verdicts = ["FAIL"] * len(verdicts)
        floor_applied = "all_pass_short_answer"
    else:
        floor_applied = None

    # Reachability cross-check: if the agent's URLs don't resolve, downgrade
    # any PASS on a grounding-dependent criterion to FAIL. Solves the
    # gpt-researcher 0009 case where 93 fab URLs got 21/21 from the judge.
    grounding_downgrades = 0
    if reachability is not None and reachability < fab_threshold:
        for i, c in enumerate(checklist):
            if verdicts[i] == "PASS" and _criterion_requires_grounding(c):
                verdicts[i] = "FAIL"
                grounding_downgrades += 1

    pass_rate = sum(v == "PASS" for v in verdicts) / len(checklist)
    return {
        "verdicts": list(zip(checklist, verdicts)),
        "pass_count": sum(v == "PASS" for v in verdicts),
        "fail_count": sum(v == "FAIL" for v in verdicts),
        "unclear_count": sum(v == "UNCLEAR" for v in verdicts),
        "pass_rate": round(pass_rate, 4),
        "judge_error": None,
        "sanity_floor": floor_applied,
        "grounding_downgrades": grounding_downgrades,
        "reachability_used": reachability,
    }


def _composite(
    reachability: float,
    quote_match: float,
    claim_nli: float,
    url_cov: float,
    checklist_pass_rate: float,
    spec: dict,
    *,
    citation_alignment: float = 0.0,
    analysis_depth: float = 0.0,
    presentation: float = 0.0,
) -> dict:
    """Composite scoring with v1, v2, and v3 formulas.

    v1 (legacy additive):
      composite_v1 = reachability × quality
      quality      = 0.4·url_cov + 0.4·judge + 0.2·spec

    v2 (truthfulness-first, 3-layer multiplicative):
      truth     = reach × (0.5 + 0.5·quote_match) × (0.5 + 0.5·claim_nli)
      quality   = 0.4·url_cov + 0.4·judge + 0.2·spec
      composite = truth × quality

    v3 (7-dimension weighted, grounding-gated):
      grounding_gate = max(0.1, reachability)
      raw_score = (
          0.20 × url_coverage +
          0.20 × quote_fidelity +
          0.20 × judge_pass +
          0.10 × spec_compliance +
          0.15 × citation_alignment +
          0.10 × analysis_depth +
          0.05 × presentation
      )
      composite_v3 = grounding_gate × raw_score
    """
    spec_pass = sum([spec["words_ok"], spec["citations_ok"], spec["paragraphs_ok"]]) / 3.0

    # --- v2 ---
    quality = (
        0.40 * url_cov
        + 0.40 * checklist_pass_rate
        + 0.20 * spec_pass
    )
    qm_factor  = 0.5 + 0.5 * quote_match
    nli_factor = 0.5 + 0.5 * claim_nli
    truth = reachability * qm_factor * nli_factor
    composite_v2 = truth * quality

    # --- v1 (backward compat) ---
    composite_v1 = reachability * quality
    legacy_composite = 0.50 * url_cov + 0.35 * checklist_pass_rate + 0.15 * spec_pass

    # --- v3 ---
    grounding_gate = max(0.1, reachability)
    raw_score = (
        0.20 * url_cov
        + 0.20 * quote_match
        + 0.20 * checklist_pass_rate
        + 0.10 * spec_pass
        + 0.15 * citation_alignment
        + 0.10 * analysis_depth
        + 0.05 * presentation
    )
    composite_v3 = grounding_gate * raw_score

    return {
        "spec_pass_fraction":   round(spec_pass, 4),
        "quality_score":        round(quality, 4),
        "truth_factor":         round(truth, 4),
        "qm_factor":            round(qm_factor, 4),
        "nli_factor":           round(nli_factor, 4),
        # v3 new fields
        "grounding_gate":       round(grounding_gate, 4),
        "raw_score_v3":         round(raw_score, 4),
        "citation_alignment":   round(citation_alignment, 4),
        "analysis_depth":       round(analysis_depth, 4),
        "presentation":         round(presentation, 4),
        # composites
        "composite_v3":         round(composite_v3, 4),
        "composite_score":      round(composite_v2, 4),   # v2 remains default
        "composite_v2":         round(composite_v2, 4),
        "composite_v1":         round(composite_v1, 4),
        "legacy_composite":     round(legacy_composite, 4),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--answer", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    task_path = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep" / f"{args.task}.json"
    task_cfg = json.loads(task_path.read_text())

    sandbox_aliases = {
        "__SHOPPING__":  ["localhost:7770"],
        "__REDDIT__":    ["localhost:9999"],
        "__WIKIPEDIA__": ["localhost:8090"],
    }
    task_cfg.setdefault("domain_aliases", sandbox_aliases)

    answer_path = Path(args.answer)
    if not answer_path.exists():
        print(f"answer not found: {answer_path}", file=sys.stderr)
        return 2
    answer = answer_path.read_text(errors="ignore")

    print(f"=== scoring {answer_path.name} on task {args.task} ===")
    print(f"answer chars: {len(answer)}")

    url_v = URLCoverageVerifier()
    url_result = url_v.verify(task_config=task_cfg, answer=answer)
    print(f"\n[url_coverage] score={url_result.score} passed={url_result.passed}")
    print(f"  details: {json.dumps(url_result.details, ensure_ascii=False)}")

    reach_v = URLReachabilityVerifier(max_workers=4, max_urls=150)
    reach_result = reach_v.verify(task_config=task_cfg, answer=answer)
    print(f"\n[url_reachability] rate={reach_result.score} passed={reach_result.passed}")
    print(f"  details: {json.dumps(reach_result.details, ensure_ascii=False)}")

    if os.environ.get("SKIP_LAYER2", "0") != "1":
        qm_v = QuoteMatchVerifier(max_workers=3, max_urls=120)
        qm_result = qm_v.verify(task_config=task_cfg, answer=answer)
        print(f"\n[quote_match] rate={qm_result.score} passed={qm_result.passed}")
        print(f"  details: {json.dumps(qm_result.details, ensure_ascii=False)}")
    else:
        from src.verifiers.base import VerifierResult
        qm_result = VerifierResult.fail("skipped", reason="SKIP_LAYER2=1")

    if os.environ.get("SKIP_LAYER3", "0") != "1":
        nli_v = ClaimNLIVerifier(theta=0.80, max_calls=60, max_workers=3)
        nli_result = nli_v.verify(task_config=task_cfg, answer=answer)
        print(f"\n[claim_nli] rate={nli_result.score} passed={nli_result.passed}")
        print(f"  details: {json.dumps(nli_result.details, ensure_ascii=False)}")
    else:
        from src.verifiers.base import VerifierResult
        nli_result = VerifierResult.fail("skipped", reason="SKIP_LAYER3=1")

    spec_check = _markdown_spec_score(answer, task_cfg.get("markdown_spec", {}))
    print(f"\n[markdown_spec] {json.dumps(spec_check, ensure_ascii=False)}")

    checklist_path = ROOT / task_cfg.get("coverage_checklist_path", "")
    checklist = []
    if checklist_path.exists():
        checklist = json.loads(checklist_path.read_text()).get(args.task, [])
    print(f"\n[checklist] {len(checklist)} items, judge={judge_identity()}, reach={reach_result.score:.3f}")
    # Plumb reachability so the fab-URL cross-check fires (downgrades PASS
    # to FAIL on grounding-keyword criteria when reach < 0.30). Without
    # this kwarg the guard is dead in production scoring.
    checklist_result = _judge_checklist(
        checklist, answer, args.task, reachability=reach_result.score
    )
    print(f"  pass={checklist_result.get('pass_count')}/{len(checklist)} "
          f"fail={checklist_result.get('fail_count')} unclear={checklist_result.get('unclear_count')} "
          f"rate={checklist_result.get('pass_rate')}")
    if checklist_result.get('judge_error'):
        print(f"  ! judge error: {checklist_result['judge_error']}")

    # --- v3 + v4 new verifiers (graceful fallback) ---
    # SKIP_V4=1 keeps the run cheap (skips the four v4 pillars but still
    # runs v3 ones). SKIP_V3=1 skips both, dropping back to pure v2 baseline.
    skip_v3 = os.environ.get("SKIP_V3", "0") == "1"
    skip_v4 = os.environ.get("SKIP_V4", "0") == "1" or skip_v3

    v3_scores = {}
    v3_details = {}

    v3_verifiers = [
        ("citation_alignment", "src.verifiers.citation_alignment_verifier", "CitationAlignmentVerifier"),
        ("analysis_depth",     "src.verifiers.analysis_depth_verifier",     "AnalysisDepthVerifier"),
        ("presentation",       "src.verifiers.presentation_verifier",       "PresentationVerifier"),
    ]
    v4_verifiers = [
        # source_diversity goes first because it's zero-LLM and we want
        # the cheap deterministic pillar to land even if heavy verifiers
        # crash or time out. perspective_balance second (light LLM).
        # factual_exactness and internal_consistency are the heavy V4 Pro
        # consumers — they go last so a budget-exhausted run still has
        # the cheap pillars.
        ("source_diversity",     "src.verifiers.source_diversity_verifier",     "SourceDiversityVerifier"),
        ("perspective_balance",  "src.verifiers.perspective_balance_verifier",  "PerspectiveBalanceVerifier"),
        ("factual_exactness",    "src.verifiers.factual_exactness_verifier",    "FactualExactnessVerifier"),
        ("internal_consistency", "src.verifiers.internal_consistency_verifier", "InternalConsistencyVerifier"),
    ]

    all_extras = list(v3_verifiers)
    if not skip_v3:
        # v3 verifiers always run by default — they predate this scorer
        # and the leaderboard composites depend on them.
        pass
    else:
        all_extras = []
    if not skip_v4:
        all_extras.extend(v4_verifiers)

    for verifier_name, verifier_module, verifier_class in all_extras:
        try:
            import importlib
            mod = importlib.import_module(verifier_module)
            cls = getattr(mod, verifier_class)
            v_inst = cls()
            v_result = v_inst.verify(task_config=task_cfg, answer=answer)
            v3_scores[verifier_name] = v_result.score
            v3_details[verifier_name] = {
                "score": v_result.score, "passed": v_result.passed,
                "details": v_result.details,
            }
            print(f"\n[{verifier_name}] score={v_result.score} passed={v_result.passed}")
        except ImportError:
            v3_scores[verifier_name] = 0.0
            v3_details[verifier_name] = {
                "score": 0.0, "passed": False,
                "details": {"note": f"{verifier_module} not available; scored 0"},
            }
            print(f"\n[{verifier_name}] not available (module not found), scored 0")
        except Exception as exc:
            v3_scores[verifier_name] = 0.0
            v3_details[verifier_name] = {
                "score": 0.0, "passed": False,
                "details": {"note": f"error: {type(exc).__name__}: {exc}"},
            }
            print(f"\n[{verifier_name}] error: {exc}, scored 0")

    composite = _composite(
        reach_result.score,
        qm_result.score,
        nli_result.score,
        url_result.score,
        checklist_result.get('pass_rate', 0.0),
        spec_check,
        citation_alignment=v3_scores.get("citation_alignment", 0.0),
        analysis_depth=v3_scores.get("analysis_depth", 0.0),
        presentation=v3_scores.get("presentation", 0.0),
    )

    # composite_v4 — computed via the canonical formula in
    # src.scoring.leaderboard_composites. We materialise a partial
    # "score-shaped" dict so the canonical function reads it the same
    # way it reads on-disk score JSONs.
    from src.scoring.leaderboard_composites import composite_v4, composite_v4_weights
    v4_input = {
        "url_reachability":     {"score": reach_result.score},
        "url_coverage":         {"score": url_result.score},
        "quote_match":          {"score": qm_result.score},
        "citation_alignment":   v3_details.get("citation_alignment", {}),
        "analysis_depth":       v3_details.get("analysis_depth", {}),
        "presentation":         v3_details.get("presentation", {}),
        "source_diversity":     v3_details.get("source_diversity", {}),
        "perspective_balance":  v3_details.get("perspective_balance", {}),
        "factual_exactness":    v3_details.get("factual_exactness", {}),
        "internal_consistency": v3_details.get("internal_consistency", {}),
        "markdown_spec":        spec_check,
        "checklist":            checklist_result,
    }
    composite["composite_v4"] = round(float(composite_v4(v4_input)), 4)
    composite["composite_v4_weights"] = composite_v4_weights()
    # Stamp the v4-only pillar scores so audit pages can show the
    # breakdown without reading individual verifier blobs.
    composite["source_diversity"]     = round(float(v3_scores.get("source_diversity", 0.0)), 4)
    composite["perspective_balance"]  = round(float(v3_scores.get("perspective_balance", 0.0)), 4)
    composite["factual_exactness"]    = round(float(v3_scores.get("factual_exactness", 0.0)), 4)
    composite["internal_consistency"] = round(float(v3_scores.get("internal_consistency", 0.0)), 4)
    print(f"\n[composite] {json.dumps(composite, ensure_ascii=False)}")

    out = {
        "task": args.task,
        "answer_path": str(answer_path),
        "answer_chars": len(answer),
        "url_coverage":     {"score": url_result.score,   "passed": url_result.passed,
                             "details": url_result.details},
        "url_reachability": {"score": reach_result.score, "passed": reach_result.passed,
                             "details": reach_result.details},
        "quote_match":      {"score": qm_result.score,    "passed": qm_result.passed,
                             "details": qm_result.details},
        "claim_nli":        {"score": nli_result.score,   "passed": nli_result.passed,
                             "details": nli_result.details},
        "citation_alignment":   v3_details.get("citation_alignment", {}),
        "analysis_depth":       v3_details.get("analysis_depth", {}),
        "presentation":         v3_details.get("presentation", {}),
        # v4 NEW pillars — each falls back to {} when SKIP_V4=1 was used.
        "source_diversity":     v3_details.get("source_diversity", {}),
        "perspective_balance":  v3_details.get("perspective_balance", {}),
        "factual_exactness":    v3_details.get("factual_exactness", {}),
        "internal_consistency": v3_details.get("internal_consistency", {}),
        "markdown_spec": spec_check,
        "checklist": checklist_result,
        "composite": composite,
        "judge_identity": judge_identity(),
    }
    if args.out:
        Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
