"""The completeness axis is documented as a CENSUS, not saturating (ruling #5).

The implementation denominator is min(K*, |pool|), and every current task's
vital pool holds ~14-17 nuggets below K*=20, so saturation never fires and the
axis is in practice a census (cover every vital fact to score 1.0). The scoring
numbers do not change; ruling #5 only aligns the prose with what the code does.
These pins go red if the docstring/README/DATASHEET drift back to claiming a
saturating "focused shortlist of any K*" is enough.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.eval import decidable_scorer as ds  # noqa: E402


def test_score_completeness_docstring_states_census_semantics():
    doc = (ds.score_completeness.__doc__ or "").lower()
    assert "census" in doc, "docstring must name the census semantics"
    assert "upper cap" in doc, "docstring must note K* is only an upper cap"
    # The denominator that makes it a census must be stated verbatim.
    assert "min(k_star, |pool|)" in doc


def test_readme_and_datasheet_call_completeness_a_census():
    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    datasheet = (ROOT / "docs" / "DATASHEET.md").read_text(encoding="utf-8").lower()
    assert "census" in readme
    assert "census" in datasheet
    # Both must keep K* framed as a non-binding cap, not a saturation budget.
    assert "upper cap" in readme
    assert "upper cap" in datasheet
