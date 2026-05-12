"""Update the previously-patched /opt scorer's Kiwix normalizer to lowercase
the article id, so case-only mismatches (`calisthenics` vs `Calisthenics`)
match. Idempotent — only edits if the lowercase suffix isn't already there.
"""

from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path("/opt/deep_reserch/src/verifiers/url_coverage_verifier.py")

OLD_BODY = '''def _kiwix_normalize_path(path: str) -> str:
    """Collapse Kiwix article-URL aliases to one canonical path.

    Kiwix on localhost:8090 serves the same Wikipedia article under many
    URL forms (book name in path, no-JS variant, /A/ vs /wiki/, etc.).
    Without this, agents that cite the right article via a different
    prefix record 0 must_cite hits despite citing the correct page.
    """
    idx = path.rfind("/A/")
    if idx != -1:
        return f"/content/wikipedia_en_all_nopic/A/{path[idx + 3:]}"
    idx = path.rfind("/wiki/")
    if idx != -1:
        return f"/content/wikipedia_en_all_nopic/A/{path[idx + 6:]}"
    return path'''

NEW_BODY = '''def _kiwix_normalize_path(path: str) -> str:
    """Collapse Kiwix article-URL aliases to one canonical path. Lowercases
    the article id so case typos (calisthenics vs Calisthenics) match.

    Kiwix on localhost:8090 serves the same Wikipedia article under many
    URL forms (book name in path, no-JS variant, /A/ vs /wiki/, etc.).
    Without this, agents that cite the right article via a different
    prefix record 0 must_cite hits despite citing the correct page.
    """
    idx = path.rfind("/A/")
    if idx != -1:
        return f"/content/wikipedia_en_all_nopic/A/{path[idx + 3:].lower()}"
    idx = path.rfind("/wiki/")
    if idx != -1:
        return f"/content/wikipedia_en_all_nopic/A/{path[idx + 6:].lower()}"
    return path'''


def main() -> int:
    text = TARGET.read_text()
    if ".lower()" in text and "_kiwix_normalize_path" in text:
        print("already lowercased")
        return 0
    if OLD_BODY not in text:
        print("FAIL: old body not found")
        return 2
    new_text = text.replace(OLD_BODY, NEW_BODY)
    TARGET.write_text(new_text)
    import ast
    ast.parse(new_text)
    print("syntax OK; lowercase patch applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
