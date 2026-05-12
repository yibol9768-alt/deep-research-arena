#!/usr/bin/env python3
"""Generate LaTeX tables from score JSON files under
data/results/deep/*.score.json.

Outputs:
  tables/leaderboard.tex
  tables/ranking_inversion.tex
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCORES_DIR = ROOT / "data" / "results" / "deep"
OUT_DIR = Path(__file__).resolve().parent / "tables"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def _agent_from_stem(stem: str) -> str:
    return stem.split("__")[0]


def _display_name(agent: str, suffix: str = "") -> str:
    base = {
        "gpt-researcher":  "GPT-Researcher",
        "smolagents":      "smolagents",
        "camel-ai":        "CAMEL-AI",
        "langchain-odr":   "LangChain-ODR",
        "storm":           "STORM",
    }.get(agent, agent)
    if "smoke3" in suffix:
        return f"{base} (v3, +embed)"
    if "smoke" in suffix and agent == "gpt-researcher":
        return f"{base} (v2)"
    return base


def _load_all() -> list[dict]:
    rows = []
    for p in sorted(SCORES_DIR.glob("*.score.json")):
        try:
            s = json.loads(p.read_text())
        except Exception:
            continue
        stem = p.stem.replace(".score", "")
        agent_key = _agent_from_stem(stem)
        suffix = stem.split("__dr_cross_deep_0001_")[-1] if "__dr_cross_deep_0001_" in stem else ""
        rows.append({
            "key":           stem,
            "agent":         agent_key,
            "name":          _display_name(agent_key, suffix),
            "reachability":  s.get("url_reachability", {}).get("score", 0.0),
            "quote_match":   s.get("quote_match", {}).get("score", 0.0),
            "claim_nli":     s.get("claim_nli", {}).get("score", 0.0),
            "claims_eval":   s.get("claim_nli", {}).get("details", {}).get("claims_evaluated", 0),
            "url_coverage":  s.get("url_coverage", {}).get("score", 0.0),
            "must_recall":   s.get("url_coverage", {}).get("details", {}).get("must_cite_recall", 0.0),
            "judge_pass":    s.get("checklist", {}).get("pass_rate", 0.0),
            "judge_count":   s.get("checklist", {}).get("pass_count", 0),
            "judge_total":   21,
            "composite":     s.get("composite", {}).get("composite_score", 0.0),
            "composite_v1":  s.get("composite", {}).get("composite_v1", 0.0),
            "legacy":        s.get("composite", {}).get("legacy_composite", 0.0),
            "word_count":    s.get("markdown_spec", {}).get("word_count", 0),
            "citation_count": s.get("markdown_spec", {}).get("citation_count", 0),
        })
    return rows


def _write_leaderboard(rows: list[dict]) -> None:
    rows_sorted = sorted(rows, key=lambda r: -r["composite"])
    lines = [
        r"\begin{table}[ht]",
        r"\centering",
        r"\small",
        r"\caption{Truthfulness-first leaderboard on \texttt{dr\_cross\_deep\_0001} "
        r"(single task, 5 unique agents, 6 runs). Composite$_{v2}$ uses 3-layer "
        r"truthfulness gating per Eq.~\ref{eq:composite}. \emph{Reach.}~=~HTTP-200 "
        r"rate of cited URLs (Layer 1); \emph{QM}~=~quote-match (Layer 2); "
        r"\emph{NLI}~=~entailment rate at $\theta=0.80$ (Layer 3, $n$ in parens "
        r"is the number of claims that had a golden quoted span available); "
        r"\emph{Judge}~=~GPT-5-chat checklist PASS count out of 21.}",
        r"\label{tab:leaderboard}",
        r"\begin{tabular}{rlccccrrr}",
        r"\toprule",
        r"\# & Agent & Reach. & QM & NLI~$(n)$ & Judge & "
        r"Comp.$_{v2}$ & Comp.$_{v1}$ & Legacy \\",
        r"\midrule",
    ]
    for i, r in enumerate(rows_sorted, 1):
        nli = f"{r['claim_nli']:.2f}~({r['claims_eval']})"
        lines.append(
            f"{i} & {r['name']} & "
            f"{r['reachability']:.2f} & "
            f"{r['quote_match']:.2f} & "
            f"{nli} & "
            f"{r['judge_count']}/{r['judge_total']} & "
            f"\\textbf{{{r['composite']:.3f}}} & "
            f"{r['composite_v1']:.3f} & "
            f"{r['legacy']:.3f} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    (OUT_DIR / "leaderboard.tex").write_text("\n".join(lines))


def _write_inversion(rows: list[dict]) -> None:
    rows_legacy = sorted(rows, key=lambda r: -r["legacy"])
    rows_new    = sorted(rows, key=lambda r: -r["composite"])
    legacy_rank = {r["key"]: i + 1 for i, r in enumerate(rows_legacy)}
    new_rank    = {r["key"]: i + 1 for i, r in enumerate(rows_new)}
    rows_display = rows_legacy  # show in legacy-rank order
    lines = [
        r"\begin{table}[ht]",
        r"\centering",
        r"\caption{Ranking inversion. Agents ordered by legacy composite "
        r"(Eq.~\ref{eq:legacy}); the truthfulness-first composite "
        r"(Eq.~\ref{eq:composite}) reorders them in inverse. $\Delta$~is "
        r"$\text{legacy rank} - \text{new rank}$; negative = truthful "
        r"agent penalised under legacy, positive = fabricator rewarded.}",
        r"\label{tab:inversion}",
        r"\begin{tabular}{lcccrrr}",
        r"\toprule",
        r"Agent & Reach & Judge & Legacy & Legacy rank & New rank & $\Delta$ \\",
        r"\midrule",
    ]
    for r in rows_display:
        lr = legacy_rank[r["key"]]
        nr = new_rank[r["key"]]
        delta = lr - nr
        color = "\\cellcolor{red!15}" if delta > 0 else ("\\cellcolor{green!15}" if delta < 0 else "")
        lines.append(
            f"{r['name']} & "
            f"{r['reachability']:.2f} & "
            f"{r['judge_count']}/21 & "
            f"{r['legacy']:.3f} & "
            f"{lr} & {nr} & "
            f"{color}{delta:+d} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    (OUT_DIR / "ranking_inversion.tex").write_text("\n".join(lines))


def main() -> int:
    rows = _load_all()
    if not rows:
        print("no score files found under", SCORES_DIR)
        (OUT_DIR / "leaderboard.tex").write_text(
            "% placeholder — run scripts/score_deep_batch.py first\n"
            "\\begin{table}[ht]\\centering\\caption{Leaderboard (pending data).}"
            "\\begin{tabular}{c} TBD \\\\ \\end{tabular}\\end{table}\n"
        )
        (OUT_DIR / "ranking_inversion.tex").write_text(
            "% placeholder\n\\begin{table}[ht]\\centering"
            "\\caption{Ranking inversion (pending data).}"
            "\\begin{tabular}{c} TBD \\\\ \\end{tabular}\\end{table}\n"
        )
        return 1
    _write_leaderboard(rows)
    _write_inversion(rows)
    print(f"wrote tables for {len(rows)} runs to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
