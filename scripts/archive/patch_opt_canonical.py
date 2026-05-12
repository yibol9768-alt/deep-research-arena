"""Patch the deployed /opt/.../url_coverage_verifier.py to add Kiwix path
normalisation to its self-contained ``_canonical`` function.

The deployed file has a different shape from /mnt/d (older self-contained
version, no citation_format.py module). This patcher edits in place.
"""

from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path("/opt/deep_reserch/src/verifiers/url_coverage_verifier.py")

KIWIX_HELPER = '''
_KIWIX_HOSTS = {"localhost:8090"}


def _kiwix_normalize_path(path: str) -> str:
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
    return path


'''

OLD_CANONICAL_BODY = '''def _canonical(url: str) -> str:
    """Normalize for cited-vs-golden comparison. Tolerant to malformed URLs
    (markdown writers occasionally close links with backtick or stray punct)."""
    s = url.strip().rstrip("`'\\"\\\\)>,;:.")
    try:
        p = urlparse(s)
        host = (p.hostname or "").lower()
        try:
            port = p.port
        except (ValueError, TypeError):
            port = None
        if port and port not in (80, 443):
            host = f"{host}:{port}"
        path = (p.path or "").rstrip("/") or "/"
        qs = urlencode(sorted(parse_qsl(p.query, keep_blank_values=True)))
        return urlunparse((p.scheme.lower() or "http", host, path, "", qs, ""))
    except Exception:
        return s.lower()'''

NEW_CANONICAL_BODY = '''def _canonical(url: str) -> str:
    """Normalize for cited-vs-golden comparison. Tolerant to malformed URLs
    (markdown writers occasionally close links with backtick or stray punct).

    Also collapses Kiwix article-URL aliases (see ``_kiwix_normalize_path``).
    """
    s = url.strip().rstrip("`'\\"\\\\)>,;:.")
    try:
        p = urlparse(s)
        host = (p.hostname or "").lower()
        try:
            port = p.port
        except (ValueError, TypeError):
            port = None
        if port and port not in (80, 443):
            host = f"{host}:{port}"
        path = p.path or "/"
        if host in _KIWIX_HOSTS:
            path = _kiwix_normalize_path(path)
        path = path.rstrip("/") or "/"
        qs = urlencode(sorted(parse_qsl(p.query, keep_blank_values=True)))
        return urlunparse((p.scheme.lower() or "http", host, path, "", qs, ""))
    except Exception:
        return s.lower()'''


def main() -> int:
    if not TARGET.exists():
        print(f"target not found: {TARGET}")
        return 1
    text = TARGET.read_text()
    if "_kiwix_normalize_path" in text:
        print("already patched (kiwix helper present)")
        return 0
    if OLD_CANONICAL_BODY not in text:
        print("FAIL: could not find expected old _canonical body to replace")
        sys.exit(2)
    new_text = text.replace(OLD_CANONICAL_BODY, KIWIX_HELPER + NEW_CANONICAL_BODY)
    if new_text == text:
        print("no-op replacement - aborting")
        return 3
    backup = TARGET.with_suffix(".py.prekiwix.bak")
    backup.write_text(text)
    TARGET.write_text(new_text)
    print(f"patched {TARGET} (backup at {backup})")
    print(f"new size: {len(new_text)} bytes (was {len(text)})")
    # Smoke-test that file still parses
    import ast
    ast.parse(new_text)
    print("syntax OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
