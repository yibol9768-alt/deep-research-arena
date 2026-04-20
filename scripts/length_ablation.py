"""Length-controlled ablation analysis.

For every (agent, task) run we have:
  - answer.md  → word count
  - final_*.json → per-pillar scores

Check whether any pillar score correlates with answer length. The concern:
LLM-judge (and DRACO checklist) may reward verbosity rather than substance.
If Spearman(judge_score, word_count) > 0.4 we need a length-normalized
variant so length gaming doesn't inflate the leaderboard.

Outputs:
  data/results/LENGTH_ABLATION.md  — report + suggested length-normalized
                                      Δ per agent
  data/results/length_ablation.json — raw regression results
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean

import numpy as np
from scipy.stats import spearmanr, linregress

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data" / "results"

PILLARS = [
    "markdown_structure",
    "citation",
    "fact_kg",
    "llm_judge",
    "checklist",
    "evidence_density",
    "efficiency",
]


def _word_count(text: str) -> int:
    # Strip inline code and URLs before counting.
    text = re.sub(r"`[^`]*`", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    return len(re.findall(r"\w+", text))


def _load_runs() -> list[dict]:
    """Gather (agent, task, word_count, pillar_scores, composite). Prefer .ed.json
    (latest v3.2 weights) if it exists, fall back to plain final_*.json."""
    rows = []
    for p in sorted(RESULTS.glob("final_*.json")):
        if p.name.endswith(".answer.md"):
            continue
        name = p.stem  # e.g. final_camel-ai_dr_cross_v3_0001[.ed]
        # Prefer .ed.json if present
        ed_path = p.with_name(p.stem + ".ed.json")
        source = ed_path if ed_path.exists() else p
        try:
            d = json.loads(source.read_text())
        except Exception:
            continue
        agent = d.get("agent")
        task_id = d.get("task_id")
        if not agent or not task_id:
            continue
        # Answer file lives next to the final_ file
        ans_path = RESULTS / f"final_{agent}_{task_id}.answer.md"
        wc = 0
        if ans_path.exists():
            wc = _word_count(ans_path.read_text(encoding="utf-8", errors="ignore"))
        pillars = d.get("pillars", {})
        scores = {k: (v.get("score") if isinstance(v, dict) else 0) for k, v in pillars.items()}
        rows.append({
            "agent": agent,
            "task_id": task_id,
            "words": wc,
            "composite": d.get("composite"),
            "scores": scores,
        })
    # Dedup: prefer ed.json (we may have loaded both for some). Key = (agent, task).
    dedup = {}
    for r in rows:
        dedup[(r["agent"], r["task_id"])] = r
    return list(dedup.values())


def analyze(rows: list[dict]) -> dict:
    if not rows:
        return {}
    words = np.array([r["words"] for r in rows])
    out: dict = {"n": len(rows), "pillars": {}}

    for pillar in PILLARS + ["composite"]:
        if pillar == "composite":
            y = np.array([r.get("composite") or 0 for r in rows])
        else:
            y = np.array([r["scores"].get(pillar, 0) or 0 for r in rows])
        if y.std() < 1e-6 or words.std() < 1e-6:
            out["pillars"][pillar] = {"spearman": None, "slope": None, "note": "zero variance"}
            continue
        rho, p = spearmanr(words, y)
        reg = linregress(words, y)
        flag = "OK" if abs(rho) < 0.4 else "SUSPECT" if abs(rho) < 0.6 else "STRONG"
        out["pillars"][pillar] = {
            "spearman": round(float(rho), 3),
            "p_value": round(float(p), 4),
            "slope_per_1k_words": round(float(reg.slope) * 1000, 4),
            "flag": flag,
        }

    # Per-agent mean word count; if one agent writes 2x longer than another,
    # it's getting a length advantage.
    by_agent: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        by_agent[r["agent"]].append(r["words"])
    out["avg_words_per_agent"] = {
        a: round(mean(v)) for a, v in sorted(by_agent.items(), key=lambda x: -mean(x[1]))
    }
    return out


def _length_normalized(rows: list[dict], pillar: str) -> dict[str, float]:
    """Subtract the length trend from pillar score, re-aggregate per agent."""
    words = np.array([r["words"] for r in rows])
    y = np.array([r["scores"].get(pillar, 0) or 0 for r in rows])
    if y.std() < 1e-6 or words.std() < 1e-6:
        return {}
    reg = linregress(words, y)
    residual = y - (reg.slope * words + reg.intercept)  # length-detrended
    by_agent: dict[str, list[float]] = defaultdict(list)
    for r, res in zip(rows, residual):
        by_agent[r["agent"]].append(float(res + y.mean()))  # re-anchor to mean
    return {a: round(mean(v), 3) for a, v in by_agent.items()}


def render_report(analysis: dict, rows: list[dict]) -> str:
    lines = [
        "# Length-Controlled Ablation",
        "",
        f"**n** = {analysis.get('n', 0)} runs across "
        f"{len({r['agent'] for r in rows})} agents × "
        f"{len({r['task_id'] for r in rows})} tasks.",
        "",
        "Goal: check whether any scoring pillar rewards verbosity. "
        "Spearman ρ > 0.4 = SUSPECT, > 0.6 = STRONG (needs length-normalized variant).",
        "",
        "## Per-pillar correlation with answer word count",
        "",
        "| Pillar | Spearman ρ | p | Δscore per +1000 words | Flag |",
        "|---|---:|---:|---:|:---:|",
    ]
    for p in PILLARS + ["composite"]:
        info = analysis["pillars"].get(p, {})
        if info.get("spearman") is None:
            lines.append(f"| {p} | — | — | — | {info.get('note','no data')} |")
        else:
            lines.append(
                f"| {p} | {info['spearman']:+.3f} | {info['p_value']:.3f} | "
                f"{info['slope_per_1k_words']:+.4f} | **{info['flag']}** |"
            )

    lines += [
        "",
        "## Avg word count per agent (longer-writing agents get a length advantage if ρ>0)",
        "",
    ]
    for a, w in analysis.get("avg_words_per_agent", {}).items():
        lines.append(f"- **{a}**: {w} words")

    # If any suspect pillar, compute length-normalized per-agent scores for it.
    suspect = [p for p, info in analysis["pillars"].items()
               if isinstance(info.get("spearman"), (int, float)) and abs(info["spearman"]) > 0.4]
    if suspect:
        lines += ["", "## Length-normalized per-agent mean (suspect pillars)", ""]
        for p in suspect:
            norm = _length_normalized(rows, p)
            if not norm:
                continue
            lines += [f"### {p} (normalized)", "", "| Agent | Normalized score |", "|---|---:|"]
            for a, s in sorted(norm.items(), key=lambda x: -x[1]):
                lines.append(f"| {a} | {s:.3f} |")
            lines.append("")

    lines += [
        "",
        "## Interpretation",
        "",
        "- Flag=OK → pillar is length-robust, keep as-is.",
        "- Flag=SUSPECT → report both raw and length-normalized in paper; "
        "add length as a covariate in regression tables.",
        "- Flag=STRONG → replace the pillar with a length-controlled variant OR "
        "cap per-answer word count at e.g. 1500 before scoring.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    rows = _load_runs()
    analysis = analyze(rows)
    out_json = RESULTS / "length_ablation.json"
    out_md = RESULTS / "LENGTH_ABLATION.md"
    out_json.write_text(json.dumps(analysis, indent=2, ensure_ascii=False))
    out_md.write_text(render_report(analysis, rows))
    print(f"Wrote {out_md}")
    print(f"Wrote {out_json}")
    # Summary to stdout
    for p, info in analysis.get("pillars", {}).items():
        rho = info.get("spearman")
        flag = info.get("flag", "?")
        if rho is not None:
            print(f"  {p:<20} ρ={rho:+.3f}  [{flag}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
