"""Unit tests for verifiers (no browser required)."""

from src.verifiers import StringVerifier, URLVerifier


class FakePage:
    def __init__(self, url: str) -> None:
        self.url = url


def test_string_exact_match():
    cfg = {"eval": {"reference_answers": {"exact_match": "Quest Lumaflex™ Band"}}}
    assert StringVerifier().verify(task_config=cfg, answer="Quest Lumaflex™ Band").passed
    assert not StringVerifier().verify(task_config=cfg, answer="some other thing").passed


def test_string_must_include():
    cfg = {"eval": {"reference_answers": {"must_include": ["blue", "jacket"]}}}
    assert StringVerifier().verify(task_config=cfg, answer="A blue winter jacket").passed
    assert not StringVerifier().verify(task_config=cfg, answer="a red sweater").passed


def test_url_match():
    cfg = {"eval": {"reference_url": "http://shopping.local/catalogsearch/result/?q=blue"}}
    v = URLVerifier()
    assert v.verify(task_config=cfg, page=FakePage("http://shopping.local/catalogsearch/result/?q=blue")).passed
    assert v.verify(
        task_config=cfg,
        page=FakePage("http://shopping.local/catalogsearch/result/?q=blue&page=1"),
    ).passed  # extras allowed
    assert not v.verify(task_config=cfg, page=FakePage("http://shopping.local/home")).passed
