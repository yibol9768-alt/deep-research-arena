"""KG-based fact verification for v3 deep research tasks.

The v3 design replaces report_schema (which locked agents into JSON) with a
markdown answer + a golden-triple knowledge graph. This package:

  - db_connect    : subprocess wrapper that runs MySQL/PG queries via
                    `ssh westd wsl -- docker exec <container> ...`
  - db_schema_map : per-predicate SQL templates (Magento EAV + Postmill PG)
  - db_verifier   : MagentoTripleStore / PostmillTripleStore — answer
                    `verify((subj, pred, obj)) -> True | False | None`
  - triple_extractor : LLM-based (subject, predicate, object) extractor
                    from a markdown research report

Wired into the new `src.verifiers.fact_kg_verifier.FactKGVerifier`.
"""

from .db_connect import DBRunner

__all__ = ["DBRunner"]
