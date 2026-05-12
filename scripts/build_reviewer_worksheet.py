"""Build a reviewer pack: the task intent + checklist (NO must-cite list)
plus a clickable index of every URL the scraper found, so a second
annotator can independently mark which URLs they would require an agent
to cite. Output is a single self-contained HTML file with checkbox UI
that exports a JSON list to the clipboard / a downloadable file.

Usage:
    python3 scripts/build_reviewer_worksheet.py --task dr_cross_deep_0001

Outputs:
    data/annotation/<task_id>/reviewer_pack.html
    data/annotation/<task_id>/scraper_must_cite.json   (the existing
        scraper-derived must-cite, used later as annotator-A in IAA)

The reviewer:
    1. Opens reviewer_pack.html in a browser.
    2. Reads the intent + checklist sidebar.
    3. For each URL group (shopping / reddit / wiki) ticks the boxes
       they think SHOULD be in must-cite.
    4. Clicks "Export reviewer_must_cite.json" — downloads a JSON list.
    5. Saves it to data/annotation/<task_id>/reviewer_must_cite.json.

Then the operator runs:
    python3 -m src.verifiers.iaa_score \\
        --annotator-a data/annotation/<task>/scraper_must_cite.json \\
        --annotator-b data/annotation/<task>/reviewer_must_cite.json
"""

from __future__ import annotations

import argparse
import json
import sys
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _expand_aliases(text: str) -> str:
    return (text
            .replace("__SHOPPING__", "http://localhost:7770")
            .replace("__REDDIT__",   "http://localhost:9999")
            .replace("__WIKIPEDIA__", "http://localhost:8090"))


def _category(url: str) -> str:
    if "7770" in url: return "shopping"
    if "9999" in url: return "reddit"
    if "8090" in url: return "wiki"
    return "other"


def _short_label(url: str, fallback: str = "") -> str:
    if fallback:
        return fallback[:80]
    last = url.rstrip("/").split("/")[-1].replace("-", " ").replace(".html", "")
    return last[:80] or url


HTML_HEAD = """<!doctype html>
<html><head><meta charset="utf-8">
<title>Reviewer Pack — {task_id}</title>
<style>
  body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;margin:0;padding:0;display:flex;height:100vh}}
  #sidebar{{width:32%;padding:1.5rem;border-right:1px solid #ccc;overflow-y:auto;background:#fafafa}}
  #main{{flex:1;padding:1.5rem;overflow-y:auto}}
  h1{{font-size:1.3rem}}
  h2{{margin-top:2rem;border-bottom:2px solid #333;padding-bottom:.3rem}}
  .group{{margin-bottom:1.5rem}}
  .url-row{{padding:.25rem .5rem;border-bottom:1px solid #eee;font-size:.85rem;display:flex;gap:.5rem;align-items:start}}
  .url-row:hover{{background:#fff8e1}}
  .url-row input{{margin-top:.2rem}}
  .url-row a{{color:#06c;text-decoration:none;flex:1;word-break:break-all}}
  .url-row a:hover{{text-decoration:underline}}
  .label{{color:#444;font-style:italic;font-size:.75rem}}
  pre{{background:#f4f4f4;padding:1rem;border-radius:4px;white-space:pre-wrap;font-size:.85rem}}
  ol li{{margin-bottom:.4rem;font-size:.9rem}}
  #export-bar{{position:sticky;top:0;background:#fff;padding:.5rem 0;border-bottom:1px solid #ccc;margin-bottom:1rem;z-index:10}}
  button{{padding:.5rem 1rem;font-size:1rem;cursor:pointer;background:#0066cc;color:#fff;border:none;border-radius:4px}}
  button:hover{{background:#0055aa}}
  .counter{{margin-left:1rem;font-weight:bold}}
</style>
</head><body>
<div id="sidebar">
<h1>Task: {task_id}</h1>
<h2>Intent</h2>
<pre>{intent}</pre>
<h2>Checklist (21 items judge will rate)</h2>
<ol>{checklist_items}</ol>
<h2>Sandbox URL aliases</h2>
<pre>__SHOPPING__   http://localhost:7770
__REDDIT__     http://localhost:9999
__WIKIPEDIA__  http://localhost:8090</pre>
<p style="font-size:.8rem;color:#888"><b>Reviewer instructions:</b><br>
Tick the URLs you would REQUIRE an agent to cite to fully address the
task intent above. Aim for 60–80 ticks. Do NOT consult the existing
must-cite list — work only from the intent + checklist.</p>
</div>
<div id="main">
<div id="export-bar">
  <button onclick="exportSelection()">Export reviewer_must_cite.json</button>
  <span class="counter" id="cnt">0 selected</span>
</div>
"""


HTML_FOOT = """
<script>
  const cnt = document.getElementById('cnt');
  function refresh() {
    const n = document.querySelectorAll('input.must:checked').length;
    cnt.textContent = n + ' selected';
  }
  document.addEventListener('change', refresh);
  refresh();

  function exportSelection() {
    const urls = [...document.querySelectorAll('input.must:checked')].map(x => x.value);
    const blob = new Blob([JSON.stringify(urls, null, 2)], {type:'application/json'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'reviewer_must_cite.json';
    a.click();
    URL.revokeObjectURL(url);
  }
</script>
</body></html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True, help="task id, e.g. dr_cross_deep_0001")
    args = ap.parse_args()

    task_path = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep" / f"{args.task}.json"
    if not task_path.exists():
        sys.exit(f"task not found: {task_path}")
    task = json.loads(task_path.read_text())

    golden_path = ROOT / "data" / "golden" / "deep" / f"{args.task}.json"
    if not golden_path.exists():
        sys.exit(f"golden not found: {golden_path}")
    golden = json.loads(golden_path.read_text())

    checklists_path = ROOT / "data" / "tasks" / "deep_research" / "cross_site_deep" / "checklists_deep.json"
    checklist_items = []
    if checklists_path.exists():
        all_lists = json.loads(checklists_path.read_text())
        items = all_lists.get(args.task, [])
        checklist_items = [f"<li>{escape(it)}</li>" for it in items]

    out_dir = ROOT / "data" / "annotation" / args.task.split("_")[-1]
    out_dir.mkdir(parents=True, exist_ok=True)

    # save scraper_must_cite for IAA later
    scraper_must = [e["url"] for e in golden.get("must_cite_urls", [])]
    (out_dir / "scraper_must_cite.json").write_text(json.dumps(scraper_must, indent=2))

    # build URL groups from expected_pool (the universe to tick from)
    universe = {e["url"]: e for e in golden.get("expected_pool_urls", [])}
    # also include must_cite URLs in case some weren't in pool
    for e in golden.get("must_cite_urls", []):
        universe.setdefault(e["url"], {"url": e["url"], "category": e.get("category", ""), "why": e.get("why", "")})

    grouped: dict[str, list[dict]] = {"shopping": [], "reddit": [], "wiki": [], "other": []}
    for url, e in universe.items():
        grouped[_category(url)].append(e)

    parts = [HTML_HEAD.format(
        task_id=args.task,
        intent=escape(_expand_aliases(task.get("intent", "") )),
        checklist_items="\n".join(checklist_items) or "<li>(none)</li>",
    )]

    cat_titles = {"shopping": "Shopping (Magento :7770)",
                  "reddit":   "Reddit / Postmill (:9999)",
                  "wiki":     "Wikipedia / Kiwix (:8090)",
                  "other":    "Other"}
    for cat in ("shopping", "reddit", "wiki", "other"):
        items = sorted(grouped[cat], key=lambda x: x["url"])
        if not items:
            continue
        parts.append(f'<h2>{cat_titles[cat]} — {len(items)} URLs</h2>')
        parts.append('<div class="group">')
        for e in items:
            url = e["url"]
            label = _short_label(url, e.get("why") or e.get("category") or "")
            parts.append(
                f'<div class="url-row">'
                f'<input type="checkbox" class="must" value="{escape(url)}">'
                f'<a href="{escape(url)}" target="_blank">{escape(url)}</a>'
                f'<span class="label">{escape(label)}</span>'
                f'</div>'
            )
        parts.append('</div>')

    parts.append(HTML_FOOT)
    out_html = out_dir / "reviewer_pack.html"
    out_html.write_text("".join(parts), encoding="utf-8")

    print(f"wrote {out_html}")
    print(f"wrote {out_dir / 'scraper_must_cite.json'} ({len(scraper_must)} URLs)")
    print(f"\nNext: open {out_html} in a browser, tick URLs, export reviewer_must_cite.json,")
    print(f"      save it to {out_dir}/reviewer_must_cite.json, then run iaa_score.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
