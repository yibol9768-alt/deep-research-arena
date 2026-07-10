"""The budget unit is disclosed as each backbone's own tokenizer token (ruling #11).

An 8192-token cap buys ~10-15% different English text across the three
tokenizers, so a report written to the budget has a backbone-dependent
completeness ceiling. Ruling #11 is disclosure-only: one line in the lane
protocol and one in the README. These pins go red if either drops it.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _flat(rel: str) -> str:
    return " ".join((ROOT / rel).read_text(encoding="utf-8").split()).lower()


def test_lane_protocol_header_discloses_token_unit():
    proto = _flat("config/lane_protocol.yaml")
    assert "own tokenizer token" in proto
    assert "ruling #11" in proto


def test_readme_discloses_token_unit():
    readme = _flat("README.md")
    assert "own tokenizer token" in readme
