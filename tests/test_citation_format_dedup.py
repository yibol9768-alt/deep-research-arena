"""Offline tests for citation dedup in src.verifiers.citation_format.

Regression coverage for the numbered-reference double-count bug: in a
numbered-reference report (inline `[N]` in the body plus a `[N] http://...`
References line), the bare catchall pass used to re-scan the reference line
and emit a SECOND Citation for the same URL, so every numbered citation was
counted twice. The fix makes the bare pass skip any canonical URL already
emitted by an anchored pass (markdown / source / bullet / numbered /
footnote).

These tests touch no network and exercise extract_citations directly.
"""

from __future__ import annotations

from src.verifiers.citation_format import extract_citations


HOSTS = {"localhost:7770"}


def _styles(cits):
    return [c.style for c in cits]


def test_numbered_reference_not_double_counted_as_bare():
    """A `[N] url` References line must not also surface as a bare URL."""
    report = (
        "The Sony product is great [1] and reliable.\n\n"
        "## References\n"
        "[1] http://localhost:7770/product/sony\n"
    )
    cits = extract_citations(report, sandbox_hosts=HOSTS)
    # The reference-line URL backs the numbered citation; it must not be
    # re-counted by the bare catchall.
    assert not any(c.style == "bare" for c in cits), _styles(cits)
    # Every emitted citation points at the one cited URL.
    assert {c.canonical_url for c in cits} == {
        "http://localhost:7770/product/sony"
    }


def test_footnote_reference_not_double_counted_as_bare():
    report = (
        "Claim here[^a].\n\n"
        "[^a]: http://localhost:7770/product/foo\n"
    )
    cits = extract_citations(report, sandbox_hosts=HOSTS)
    assert not any(c.style == "bare" for c in cits), _styles(cits)
    assert {c.canonical_url for c in cits} == {
        "http://localhost:7770/product/foo"
    }


def test_source_prefix_not_double_counted_as_bare():
    report = "Background reading. Source: http://localhost:7770/product/bar\n"
    cits = extract_citations(report, sandbox_hosts=HOSTS)
    assert len(cits) == 1, _styles(cits)
    assert cits[0].style == "source"
    assert cits[0].canonical_url == "http://localhost:7770/product/bar"


def test_bullet_url_not_double_counted_as_bare():
    report = "Sources:\n- http://localhost:7770/product/baz\n"
    cits = extract_citations(report, sandbox_hosts=HOSTS)
    assert len(cits) == 1, _styles(cits)
    assert cits[0].style == "bullet"


def test_markdown_url_not_double_counted_as_bare():
    report = (
        "Read [the page](http://localhost:7770/p/a). "
        "Raw mention: http://localhost:7770/p/a\n"
    )
    cits = extract_citations(report, sandbox_hosts=HOSTS)
    # Markdown is anchored; the trailing bare mention of the same URL is
    # suppressed as a duplicate of the same citation.
    assert _styles(cits) == ["markdown"], _styles(cits)


def test_distinct_bare_cites_of_same_url_are_kept():
    """Two genuine bare mentions (no anchored pass) stay distinct.

    The fix only suppresses bare URLs that duplicate an anchored citation.
    When the URL is only ever bare, every distinct site is a legitimate
    citation and must be preserved (claim_nli / quote_match iterate per
    citation site).
    """
    report = (
        "See http://localhost:7770/product/x for details. "
        "Also http://localhost:7770/product/x again."
    )
    cits = extract_citations(report, sandbox_hosts=HOSTS)
    assert _styles(cits) == ["bare", "bare"], _styles(cits)
    assert {c.char_offset for c in cits} != {cits[0].char_offset}


def test_distinct_urls_are_all_kept():
    report = (
        "First [1] then [2].\n\n"
        "[1] http://localhost:7770/product/a\n"
        "[2] http://localhost:7770/product/b\n"
    )
    cits = extract_citations(report, sandbox_hosts=HOSTS)
    assert {c.canonical_url for c in cits} == {
        "http://localhost:7770/product/a",
        "http://localhost:7770/product/b",
    }
    assert not any(c.style == "bare" for c in cits), _styles(cits)


def test_balanced_parentheses_survive_markdown_and_bare_parsing():
    url = "http://localhost:8090/content/wikipedia_en_all_nopic/A/Qi_(standard)"
    for report in (f"[Qi standard]({url})", f"Source: {url}.", url):
        cits = extract_citations(report, sandbox_only=False)
        assert len(cits) == 1
        assert cits[0].raw_url == url
        assert cits[0].canonical_url.endswith("/A/Qi_(standard)")
