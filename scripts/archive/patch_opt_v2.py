"""Direct edit of the deployed /opt scorer's Kiwix normaliser to add
.lower() on the article id."""

from __future__ import annotations

import sys
from pathlib import Path

TARGET = Path("/opt/deep_reserch/src/verifiers/url_coverage_verifier.py")
text = TARGET.read_text()

# In-place replacements that are unique enough to identify the kiwix lines
old1 = 'return f"/content/wikipedia_en_all_nopic/A/{path[idx + 3:]}"'
new1 = 'return f"/content/wikipedia_en_all_nopic/A/{path[idx + 3:].lower()}"'
old2 = 'return f"/content/wikipedia_en_all_nopic/A/{path[idx + 6:]}"'
new2 = 'return f"/content/wikipedia_en_all_nopic/A/{path[idx + 6:].lower()}"'

if old1 not in text:
    print("WARN: old1 not found - maybe already lowercased?")
else:
    text = text.replace(old1, new1)
    print("patched /A/ branch")
if old2 not in text:
    print("WARN: old2 not found")
else:
    text = text.replace(old2, new2)
    print("patched /wiki/ branch")
TARGET.write_text(text)
import ast
ast.parse(text)
print("syntax OK")
