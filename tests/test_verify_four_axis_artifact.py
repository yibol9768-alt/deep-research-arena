from __future__ import annotations

import json

from scripts.verify_four_axis_artifact import _jsonl


def test_jsonl_reader_does_not_split_unicode_line_separator(tmp_path):
    path = tmp_path / "rows.jsonl"
    rows = [
        {"id": 1, "text": "before\u2028after"},
        {"id": 2, "text": "ordinary"},
    ]
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    assert _jsonl(path) == rows
