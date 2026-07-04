#!/usr/bin/env python3
"""Extract unit-typed numeric reference facts from frozen wiki anchor articles.

Feeds the wiki-facts input of scripts/build_gold_contradictions.py. The
extraction REUSES the builder's QuantityKind patterns (one source of truth):
a value counts only where a marketing claim of the same kind would count.

Reference semantics (same as the builder's honesty contract): per (article,
kind) the MAXIMUM value found in CEILING-CUED context is emitted, as the
technology upper bound the frozen corpus supports; values mentioned in
passing never become references (see CEILING_CUE), and version-ladder
kinds are ceiling-cued by construction. Errors in the too-high direction
only suppress candidates (conservative); the too-low direction is handled
downstream by the batch driver's flag-rate curation rule.

Input: a directory of article text files produced by the box-side dump,
each starting with two header lines:
    TOPIC\t<topic name>
    FINAL_URL\t<url the fetch resolved to>
followed by the article plain text.

Output JSON (default data/golden/contradictions/wiki_numeric_facts.json):
    {"generated_by", "source", "n_articles", "n_facts",
     "facts": [{"topic", "fact_text", "source_url", "numeric_value",
                "unit", "kind", "n_occurrences_in_article"}]}

`source_url` is rendered in the registry's canonical form
http://localhost:8090/content/wikipedia_en_all_nopic/A/<Article_id> using
the redirect-resolved article id, so every reference citation is itself a
registry member.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "golden" / "contradictions" / "wiki_numeric_facts.json"
CANON_BASE = "http://localhost:8090/content/wikipedia_en_all_nopic/A/"

_spec = importlib.util.spec_from_file_location(
    "build_gold_contradictions", ROOT / "scripts" / "build_gold_contradictions.py")
_bgc = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _bgc  # dataclass decorators need the module visible
_spec.loader.exec_module(_bgc)
KINDS = _bgc.KINDS


def canonical_article_url(final_url: str, topic: str) -> str:
    """Registry-canonical URL from the fetch's redirect-resolved location."""
    tail = final_url.rsplit("/", 1)[-1] if final_url else ""
    article = unquote(tail).strip() or topic.replace(" ", "_")
    return CANON_BASE + article.replace(" ", "_")


# A value mentioned in passing (a product example, an anecdote, a citation
# title) is not a technology ceiling. A reference is emitted only when the
# value's local context carries explicit ceiling language. Verified failure
# modes this kills on the frozen corpus: "Smartphones, providing 5000 mAh"
# (power banks legitimately exceed), the Nokia "N86 8MP" mention, "141
# Lumen, an asteroid", a 1600w speaker citation title.
CEILING_CUE = re.compile(
    r"\b(?:maximum|max\.?\b|at\s+most|up\s+to|no\s+more\s+than|"
    r"as\s+high\s+as|as\s+much\s+as|theoretical|highest|record|"
    r"less\s+than|below|cannot\s+exceed|limit(?:ed)?\s+(?:to|of)|"
    r"latest|most\s+recent|newest)", re.IGNORECASE)

# Version ladders are ceilings by construction: the largest released
# version in the frozen snapshot bounds what can honestly be claimed.
LADDER_KINDS = {"bluetooth_version"}


def extract_from_article(topic: str, source_url: str, text: str) -> list[dict]:
    facts = []
    for qk in KINDS:
        best_value, best_snippet, best_cue = None, "", None
        occurrences = cue_occurrences = 0
        for pat in qk.patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                try:
                    value = float(m.group(1).replace(",", ""))
                except ValueError:
                    continue
                occurrences += 1
                lo = max(0, m.start() - 60)
                hi = min(len(text), m.end() + 60)
                window = re.sub(r"\s+", " ", text[lo:hi]).strip()
                cue = CEILING_CUE.search(window)
                if cue is None and qk.kind not in LADDER_KINDS:
                    continue
                cue_occurrences += 1
                if best_value is None or value > best_value:
                    best_value = value
                    best_snippet = window
                    best_cue = (cue.group(0) if cue
                                else "version_ladder_semantics")
        if best_value is not None:
            facts.append({
                "topic": topic,
                "fact_text": best_snippet,
                "source_url": source_url,
                "numeric_value": best_value,
                "unit": qk.unit,
                "kind": qk.kind,
                "ceiling_cue": best_cue,
                "n_occurrences_in_article": occurrences,
                "n_ceiling_cued_occurrences": cue_occurrences,
            })
    return facts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--wiki-txt-dir", required=True,
                    help="directory of TOPIC/FINAL_URL-headed article dumps")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    txt_dir = Path(args.wiki_txt_dir)
    files = sorted(txt_dir.glob("*.txt"))
    if not files:
        print(f"error: no .txt files under {txt_dir}")
        return 1

    all_facts, n_articles = [], 0
    for f in files:
        raw = f.read_text(errors="replace")
        lines = raw.split("\n", 3)
        topic, final_url = "", ""
        body_start = 0
        for i, ln in enumerate(lines[:3]):
            if ln.startswith("TOPIC\t"):
                topic = ln.split("\t", 1)[1].strip()
            elif ln.startswith("FINAL_URL\t"):
                final_url = ln.split("\t", 1)[1].strip()
                body_start = i + 1
        if not topic:
            print(f"warn: {f.name} has no TOPIC header, skipped")
            continue
        # wiki dumps hard-wrap lines; context windows (.{0,40}) must not be
        # cut by a line break
        body = re.sub(r"\s+", " ", "\n".join(raw.split("\n")[body_start:]))
        n_articles += 1
        url = canonical_article_url(final_url, topic)
        all_facts.extend(extract_from_article(topic, url, body))

    # A version ladder is global, not per-article: an article that stopped
    # being edited at version N is not evidence that N is the ceiling. Keep
    # only the snapshot-wide maximum per ladder kind.
    for kind in LADDER_KINDS:
        kind_facts = [f for f in all_facts if f["kind"] == kind]
        if len(kind_facts) > 1:
            keep = max(kind_facts, key=lambda f: f["numeric_value"])
            all_facts = [f for f in all_facts
                         if f["kind"] != kind or f is keep]

    doc = {
        "generated_by": "scripts/extract_wiki_numeric_facts.py",
        "source": "frozen kiwix snapshot wikipedia_en_all_nopic (box dump)",
        "reference_semantics": "max value per (article, kind) = technology "
                               "upper bound the frozen corpus supports",
        "n_articles": n_articles,
        "n_facts": len(all_facts),
        "facts": all_facts,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    per_kind = {}
    for fact in all_facts:
        per_kind[fact["kind"]] = per_kind.get(fact["kind"], 0) + 1
    print(f"{n_articles} articles -> {len(all_facts)} reference facts")
    for k in sorted(per_kind):
        print(f"  {k}: {per_kind[k]}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
