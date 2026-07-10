"""fact-support precision as a DETAIL column, silence != wrong (ruling #9).

The headline fact-support number is 0 both when every claim was wrong and when
no checkable claim was made. Ruling #9 adds a detail-only precision =
supported/tested so a reader can tell those apart; the headline truth number is
NOT touched. tested == 0 must render n/a (None), never 0: a lane that made no
checkable claim is not a lane that made false ones.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_truth_board import _fact_precision  # noqa: E402


def _cell(supported, contradicted):
    return {"detail": {"fact": {"supported": supported,
                                "claims_tested": supported + contradicted,
                                "contradicted": contradicted}}}


def test_precision_pools_supported_over_tested():
    cols = _fact_precision([_cell(3, 1), _cell(1, 0)])
    assert cols["supported"] == 4
    assert cols["tested"] == 5
    assert cols["precision"] == 0.8


def test_no_checkable_claim_is_na_not_zero():
    # Both reports made no checkable claim (tested == 0).
    cols = _fact_precision([_cell(0, 0), _cell(0, 0)])
    assert cols["tested"] == 0
    assert cols["precision"] is None, "silence must be n/a, never a 0"


def test_all_wrong_claims_is_zero_not_na():
    cols = _fact_precision([_cell(0, 2)])
    assert cols["tested"] == 2
    assert cols["precision"] == 0.0, "wrong claims are a real 0, distinct from n/a"
