"""Corpus-wide invariants for answer-key sources and honest oracle prose."""

from __future__ import annotations

from pathlib import Path

from src.eval.answer_key import AnswerKey
from src.eval import decidable_scorer as ds
from src.eval.url_registry import UrlRegistry
from src.verifiers.citation_format import extract_citations


ROOT = Path(__file__).resolve().parents[1]
KEYS = sorted((ROOT / "data/golden/answer_keys").glob("dr_cross_deep_*.json"))


def test_every_vital_source_is_in_corpus_and_roundtrips():
    registry = UrlRegistry.load(ROOT / "data/golden/url_registry.json")
    assert len(KEYS) == 100
    for path in KEYS:
        key = AnswerKey.load(path)
        for nugget in key.vital_nuggets:
            first = registry.classify(nugget.source_url)
            assert first["in_corpus"] is True, (path.name, nugget.subject, first)
            canonical = first["canonical"]
            second = registry.classify(canonical)
            assert second["in_corpus"] is True
            assert second["canonical"] == canonical
            cited = extract_citations(f"[source]({nugget.source_url})",
                                      sandbox_only=False)
            assert len(cited) == 1
            assert registry.classify(cited[0].raw_url)["canonical"] == canonical


def test_all_1200_buyer_sentiment_gold_lines_self_cover():
    total = covered = 0
    for path in KEYS:
        key = AnswerKey.load(path)
        buyers = [n for n in key.vital_nuggets if n.predicate == "buyer_sentiment"]
        assert len(buyers) == 12
        report = "\n".join(
            f"{n.subject} is rated {str(n.object).split('%/', 1)[0]}% positive "
            f"according to [the listing]({n.source_url})."
            for n in buyers
        )
        buyer_key = AnswerKey(task_id=key.task_id, relevant_set=key.relevant_set,
                              vital_nuggets=buyers)
        _score, detail = ds.score_completeness(
            report, buyer_key, k_star=len(buyers), pool_size=len(buyers))
        total += len(buyers)
        covered += detail["covered"]
        assert detail["covered"] == len(buyers), path.name
    assert (covered, total) == (1200, 1200)

