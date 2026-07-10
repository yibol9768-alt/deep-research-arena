"""The sentence/line citation-locality style cost is a disclosed limitation (ruling #4).

The maintainer kept same-sentence (facts) / same-line (nuggets) citation binding
because paragraph-level windows reopen citation-dumping laundering. That binding
penalizes an argumentative "state several sentences, cite at paragraph end"
style even when every claim is true and sourced. Ruling #4 records that cost in
the datasheet's known limitations rather than removing the binding. This pin
goes red if the disclosure is dropped.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_datasheet_discloses_citation_locality_style_cost():
    text = " ".join(
        (ROOT / "docs" / "DATASHEET.md").read_text(encoding="utf-8").split()
    ).lower()
    assert "ruling #4" in text
    assert "citation-locality" in text or "citation dumping" in text
    # Names the style it penalizes and that it is a deliberate, disclosed cost.
    assert "same sentence" in text and "same markdown line" in text
    assert "paragraph end" in text
