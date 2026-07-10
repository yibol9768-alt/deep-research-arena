"""Docs describe forum as a provenance dimension, not a scored source (ruling #6).

The truth number is earned on shopping (fact) + shopping/Wikipedia
(completeness, plus one virtual forum slot). The answer keys carry zero forum
vital nuggets; real forum vital nuggets (thread_score / comment_count
predicates) are a scheduled v2.1 dataset task. These pins go red if the README
or datasheet drift back to claiming three-source scoring.
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _flat(p: pathlib.Path) -> str:
    # Collapse markdown line-wrapping so multi-word phrases match regardless of
    # where the paragraph happens to wrap.
    return " ".join((ROOT / p).read_text(encoding="utf-8").split()).lower()


def test_readme_states_forum_is_provenance_not_scored():
    readme = _flat(pathlib.Path("README.md"))
    assert "provenance dimension" in readme
    assert "v2.1 dataset task" in readme
    # The board is not marketed as three-source scoring.
    assert "three-source scoring" in readme  # only ever in the "do not read" caveat


def test_datasheet_flags_forum_vital_nuggets_as_v2_1_task():
    ds = _flat(pathlib.Path("docs/DATASHEET.md"))
    assert "v2.1 dataset task" in ds
    assert "zero forum vital nuggets" in ds
    assert "provenance dimension" in ds
