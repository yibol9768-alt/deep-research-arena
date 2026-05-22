"""Unit tests for `sandbox_compliance_verifier.verify_sandbox_compliance`.

Covers the four scenarios the strict-sandbox audit needs to distinguish:
  - All citations are sandbox URLs → no violation, pct = 1.0
  - All citations are external URLs → violation, pct = 0.0
  - Mixed citations → correct ratio + non_sandbox list populated
  - Multiple citation styles in one report (markdown, bare URL, numbered
    reference, footnote) are all detected and audited together
"""

from __future__ import annotations

from src.verifiers.sandbox_compliance_verifier import (
    DEFAULT_ALLOWED_ORIGINS,
    verify_sandbox_compliance,
)


def test_all_sandbox_no_violation() -> None:
    report = (
        "# Title\n\n"
        "See [shop A](http://localhost:7770/product-a.html) for prices and "
        "[forum B](http://localhost:9999/f/audio/123/foo) for sentiment.\n"
        "Background: [wiki C](http://localhost:8090/content/wikipedia_en_all_nopic/A/Headphones).\n"
    )
    r = verify_sandbox_compliance(report)
    assert r["policy_violation"] is False
    assert r["sandbox_url_pct"] == 1.0
    assert r["total_urls"] == 3
    assert r["sandbox_urls"] == 3
    assert r["non_sandbox_urls"] == []


def test_all_external_violation() -> None:
    report = (
        "# Title\n\n"
        "Read [evil](http://evil.com/foo) and [also bad](https://example.com/bar).\n"
    )
    r = verify_sandbox_compliance(report)
    assert r["policy_violation"] is True
    assert r["sandbox_url_pct"] == 0.0
    assert r["total_urls"] == 2
    assert r["sandbox_urls"] == 0
    assert set(r["non_sandbox_urls"]) == {
        "http://evil.com/foo",
        "https://example.com/bar",
    }


def test_mixed_ratio_correct() -> None:
    report = (
        "First [ok](http://localhost:7770/p) then [leak](http://evil.com).\n"
    )
    r = verify_sandbox_compliance(report)
    assert r["policy_violation"] is True
    assert r["sandbox_url_pct"] == 0.5
    assert r["total_urls"] == 2
    assert r["sandbox_urls"] == 1
    assert r["non_sandbox_urls"] == ["http://evil.com"]


def test_127_loopback_origin_accepted() -> None:
    """127.0.0.1:7770 is the same socket as localhost:7770 and must pass."""
    report = "See [a](http://127.0.0.1:7770/x) and [b](http://localhost:8090/y).\n"
    r = verify_sandbox_compliance(report)
    assert r["policy_violation"] is False
    assert r["sandbox_url_pct"] == 1.0
    assert r["total_urls"] == 2


def test_substring_lookalike_is_not_sandbox() -> None:
    """`localhost:77703` must NOT match `localhost:7770`. The shim and the
    verifier both use netloc equality, not substring, so a sneaky URL that
    embeds the sandbox host:port should still be flagged."""
    report = "Sneaky [x](http://localhost:77703/leak) and ok [y](http://localhost:7770/p).\n"
    r = verify_sandbox_compliance(report)
    assert r["policy_violation"] is True
    assert "http://localhost:77703/leak" in r["non_sandbox_urls"]
    assert r["sandbox_urls"] == 1


def test_mixed_citation_styles_all_detected() -> None:
    """A single report with markdown link + bare URL + numbered ref must
    have all three citations audited. This is the regression-test for the
    pre-citation_format days when only markdown links were extracted."""
    report = (
        "# Mixed styles\n\n"
        "Inline markdown: [shop](http://localhost:7770/p1.html).\n\n"
        "Bare URL: see http://localhost:8090/content/wikipedia_en_all_nopic/A/Foo for more.\n\n"
        "Numbered ref: [1] says batteries are bad.\n\n"
        "Footnote ref: this matters[^a].\n\n"
        "## References\n"
        "[1] http://localhost:9999/f/audio/9/discuss\n"
        "[^a]: http://evil-leak.example.com/blog/post-1\n"
    )
    r = verify_sandbox_compliance(report)
    # 4 distinct URLs: 3 sandbox + 1 external
    assert r["total_urls"] == 4
    assert r["sandbox_urls"] == 3
    assert r["non_sandbox_urls"] == ["http://evil-leak.example.com/blog/post-1"]
    assert r["policy_violation"] is True
    assert r["sandbox_url_pct"] == 0.75


def test_zero_urls_no_violation() -> None:
    """Empty / URL-less report is vacuously compliant; total_urls = 0 lets
    the caller treat that as a separate failure mode if they need to."""
    report = "Just text, no citations.\n"
    r = verify_sandbox_compliance(report)
    assert r["policy_violation"] is False
    assert r["sandbox_url_pct"] == 1.0
    assert r["total_urls"] == 0


def test_custom_allowed_origins_override_default() -> None:
    """Caller may pass `allowed_origins=[...]` to scope the audit to a
    subset of the sandbox (e.g. an experiment that disables Postmill)."""
    report = "See [shop](http://localhost:7770/p) and [forum](http://localhost:9999/f/x).\n"
    # Only shop is allowed; forum citation must flag as a violation.
    r = verify_sandbox_compliance(
        report, allowed_origins=["http://localhost:7770"],
    )
    assert r["policy_violation"] is True
    assert r["non_sandbox_urls"] == ["http://localhost:9999/f/x"]
    assert r["sandbox_urls"] == 1


def test_default_allowed_origins_contract() -> None:
    """Sanity-check the default allowlist covers the four sandbox endpoints
    on both localhost and 127.0.0.1 (8 origins total). Tests against the
    documented contract so refactors that drop an origin fail loudly."""
    assert len(DEFAULT_ALLOWED_ORIGINS) == 8
    expected_ports = {"7770", "8090", "9999", "8081"}
    seen_ports = {o.rsplit(":", 1)[-1] for o in DEFAULT_ALLOWED_ORIGINS}
    assert seen_ports == expected_ports
