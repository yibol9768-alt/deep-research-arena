"""Closed-world URL registry: reachability as set membership, zero HTTP.

Why this exists (UNREASONABLE_PARTS_REGISTRY.md section G, esp. G-F2/F3/F8/
F10/F11). The paper's P5 identity "4xx iff the page never existed" is false in
both directions when reachability is measured by HTTP probing:

  * fake -> 200: Magento search pages return 200 on zero results, Postmill
    302->200 launders a decorative forum segment, Kiwix /search is always 200,
    redirects whitewash wrong attribution (G-F2);
  * real -> non-200: our own probe lowercased Kiwix article ids against a
    case-sensitive server, so honest wiki citations recorded as fabrication
    (G-F3); transient resets froze as status 0 (G-F9);
  * exploitable denominators: connection-refused ports vanished from the
    denominator (G-F8) and off-sandbox links were invisible (G-F10).

In a frozen sandbox the set of legitimate content URLs is ENUMERABLE, so
reachability is a set-membership query against that enumeration, not an HTTP
status. This module implements that stronger form:

    reachable  :=  parses  AND  canonical content shape  AND  in the registry

Search/compare/facet/listing URLs are recognised by shape and excluded as
navigation (never citable sources, never "reachable evidence"). Off-sandbox
hosts and content-shaped URLs absent from the registry both count as
fabricated. Status-0 / timeout / redirect tricks are irrelevant by
construction: no HTTP request is ever made.

Registry file (built by scripts/build_url_registry.py, default location
data/golden/url_registry.json):

    {
      "hosts":       {"shopping": [host:port, ...], "forums": [...],
                      "wiki": [...]},
      "products":    ["<url_key>", ...],          # Magento url_key, no .html
      "submissions": {"<id>": "<canonical_forum>", ...},
      "wiki":        ["<article_id>", ...],       # case preserved (G-F3)
      "kiwix_book":  "wikipedia_en_all_nopic"     # optional
    }

Note on Magento categories: category pages also end in .html. v1 registries
enumerate product url_keys only, so a cited bare category page classifies as
content-shaped-not-in-corpus (fabricated). If category citations should be
legitimate, merge the category url_keys into "products" at build time.

Stdlib only. Degrades gracefully when the registry file is missing:
shape detection (search_nav / off_sandbox) and canonicalisation still work,
but membership is unknown (in_corpus=None) and reachability_score() returns
status="unknown" with a loud registry_missing flag so callers can fall back
to the HTTP cache while making the degradation visible.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, unquote, urlparse

# Default registry location, relative to the repo root.
DEFAULT_REGISTRY_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "golden" / "url_registry.json"
)


class WikiBloom:
    """Bloom filter over the FULL ZIM path enumeration (articles + redirect
    titles). Properties that make it safe as a membership oracle here:

      * NO false negatives: a miss is a certain absence -> marking the
        citation fabricated is exact;
      * false positives ~0.5% (sized at build time): a fabricated wiki title
        has a 0.5% chance of slipping through as reachable. Direction-safe:
        honest citations are never penalized.

    File format WBLOOM1: 8-byte magic, <QQI (m_bits, n_keys, k), bitarray.
    Built by the box-side enumerator (scripts note in data/golden/README);
    keys are raw ZIM paths, case-sensitive, underscores not spaces.
    """

    MAGIC = b"WBLOOM1\x00"

    def __init__(self, m_bits: int, n_keys: int, k: int, bits: bytes):
        self.m_bits, self.n_keys, self.k, self.bits = m_bits, n_keys, k, bits

    @classmethod
    def load(cls, path) -> "WikiBloom | None":
        import struct
        p = Path(path)
        if not p.exists():
            return None
        with open(p, "rb") as f:
            if f.read(8) != cls.MAGIC:
                return None
            m_bits, n_keys, k = struct.unpack("<QQI", f.read(20))
            bits = f.read()
        if len(bits) * 8 < m_bits:
            return None
        return cls(m_bits, n_keys, k, bits)

    def __contains__(self, article_id: str) -> bool:
        import hashlib
        d = hashlib.sha256(article_id.encode("utf-8")).digest()
        h1 = int.from_bytes(d[:8], "big")
        h2 = int.from_bytes(d[8:16], "big") | 1
        for j in range(self.k):
            idx = (h1 + j * h2) % self.m_bits
            if not (self.bits[idx >> 3] >> (idx & 7)) & 1:
                return False
        return True


# Kiwix book used in the canonical /content/<book>/A/<id> form.
DEFAULT_KIWIX_BOOK = "wikipedia_en_all_nopic"

# Sandbox host aliases per role. First entry of each role is the canonical
# host used when rendering canonical URLs (so 127.0.0.1 citations unify).
DEFAULT_HOSTS: dict[str, list[str]] = {
    "shopping": ["localhost:7770", "127.0.0.1:7770"],
    "forums": ["localhost:9999", "127.0.0.1:9999"],
    "wiki": ["localhost:8090", "127.0.0.1:8090"],
}

# Magento layered-navigation / listing-control query params. Their presence on
# a non-content path marks the URL as faceted navigation, not a source.
LAYERED_NAV_PARAMS = {
    "q", "p", "cat", "price",
    "product_list_order", "product_list_limit", "product_list_mode",
    "product_list_dir",
}

# Path segments that mark navigation/search surfaces per role. Matched on
# whole segments, never substrings (a product url_key containing the word
# "search" must not trip this).
_SHOPPING_NAV_SEGMENTS = {"catalogsearch", "search", "checkout", "customer", "wishlist"}
_FORUM_NAV_SEGMENTS = {"search", "forums", "featured", "all", "submit", "login", "user"}
_WIKI_NAV_SEGMENTS = {"search", "suggest", "random", "catch", "viewer", "skin"}

# Light trailing-punct strip so a URL pasted mid-sentence still parses. Same
# set as citation_format.URL_TRAIL_PUNCT (kept local: stdlib-only module).
_TRAIL_PUNCT = ").,;:`'\"\\!?>]}"

KIND_CONTENT = "content"
KIND_SEARCH_NAV = "search_nav"
KIND_OFF_SANDBOX = "off_sandbox"


def _result(
    url: str,
    kind: str,
    canonical: str | None,
    in_corpus: bool | None,
    reason: str,
    *,
    host_role: str | None = None,
    forum_mismatch: bool = False,
) -> dict[str, Any]:
    return {
        "url": url,
        "kind": kind,
        "canonical": canonical,
        "in_corpus": in_corpus,
        "reason": reason,
        "host_role": host_role,
        "forum_mismatch": forum_mismatch,
    }


class UrlRegistry:
    """Membership oracle over the enumerated closed-world URL space."""

    def __init__(
        self,
        products: Iterable[str] = (),
        submissions: dict[str, str] | None = None,
        wiki: Iterable[str] = (),
        hosts: dict[str, Any] | None = None,
        kiwix_book: str = DEFAULT_KIWIX_BOOK,
        *,
        loaded: bool = True,
        wiki_complete: bool = False,
    ) -> None:
        # loaded=False marks the degraded no-registry-file mode: shape
        # detection still works but membership answers are None.
        self.loaded = bool(loaded)
        # wiki_complete=False (v1 default): the wiki list is derived from
        # cached-200 citations, NOT a full ZIM enumeration, so absence from
        # it must NOT be read as fabrication. Membership answers for unknown
        # wiki articles become None (callers fall back to the page cache)
        # until a full ZIM article enumeration upgrades this to True.
        self.wiki_complete = bool(wiki_complete)
        # full-enumeration Bloom filter (see WikiBloom); presence supersedes
        # the wiki_complete tri-state: miss = certainly fabricated
        self.wiki_bloom: "WikiBloom | None" = None
        self.kiwix_book = kiwix_book or DEFAULT_KIWIX_BOOK

        self.products: set[str] = {p for p in (products or ()) if p}
        # Case-insensitive index; maps back to the registry's stored form so
        # the canonical URL always uses the registry spelling.
        self._products_ci: dict[str, str] = {p.lower(): p for p in self.products}

        self.submissions: dict[str, str] = {
            str(k): str(v) for k, v in (submissions or {}).items()
        }

        self.wiki: set[str] = {w for w in (wiki or ()) if w}
        self._wiki_ci: dict[str, str] = {w.lower(): w for w in self.wiki}

        raw_hosts = hosts or DEFAULT_HOSTS
        self.hosts: dict[str, list[str]] = {}
        for role, hs in raw_hosts.items():
            if isinstance(hs, str):
                hs = [hs]
            self.hosts[role] = [str(h).lower() for h in hs if h]
        self._host_role: dict[str, str] = {}
        for role, hs in self.hosts.items():
            for h in hs:
                self._host_role.setdefault(h, role)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, loaded: bool = True) -> "UrlRegistry":
        return cls(
            products=data.get("products") or (),
            submissions=data.get("submissions") or {},
            wiki=data.get("wiki") or (),
            hosts=data.get("hosts") or None,
            kiwix_book=data.get("kiwix_book") or DEFAULT_KIWIX_BOOK,
            loaded=loaded,
            wiki_complete=bool((data.get("meta") or {}).get("wiki_complete", False)),
        )

    @classmethod
    def load(cls, path: str | Path = DEFAULT_REGISTRY_PATH) -> "UrlRegistry":
        """Load the registry JSON. A missing file returns a DEGRADED registry
        (loaded=False): canonicalisation and search_nav/off_sandbox detection
        still work, membership answers become None, and reachability_score()
        raises the registry_missing flag instead of guessing."""
        p = Path(path)
        if not p.exists():
            return cls(loaded=False)
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        reg = cls.from_dict(data)
        bf = (data.get("meta") or {}).get("wiki_bloom_file")
        if bf:
            reg.wiki_bloom = WikiBloom.load(p.parent / bf)
        return reg

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    def _canonical_host(self, role: str) -> str:
        hs = self.hosts.get(role) or DEFAULT_HOSTS.get(role) or [""]
        return hs[0]

    @staticmethod
    def _parse(url: str) -> tuple[str, str, str, str] | None:
        """Return (host_port, path, query, fragmentless_url) or None."""
        s = (url or "").strip().rstrip(_TRAIL_PUNCT)
        if not s:
            return None
        try:
            p = urlparse(s)
        except Exception:
            return None
        host = (p.hostname or "").lower()
        if not host:
            return None
        try:
            port = p.port
        except ValueError:
            return None
        host_port = f"{host}:{port}" if port else host
        return host_port, p.path or "/", p.query or "", s

    @staticmethod
    def _segments(path: str) -> list[str]:
        return [seg for seg in path.split("/") if seg]

    # ------------------------------------------------------------------
    # Classification (the core query)
    # ------------------------------------------------------------------

    def classify(self, url: str) -> dict[str, Any]:
        """Classify one cited URL against the closed world.

        Returns a dict with:
          kind           "content" | "search_nav" | "off_sandbox"
          canonical      canonical content URL (str) or None
          in_corpus      True / False, or None when the registry is degraded
                         (or the URL is not content-shaped)
          reason         short machine-readable cause
          host_role      "shopping" | "forums" | "wiki" | None
          forum_mismatch True when a Postmill citation's decorative forum
                         segment disagrees with the registry's canonical
                         forum for that submission id (misattribution signal;
                         in_corpus stays True, callers may penalise)
        """
        parsed = self._parse(url)
        if parsed is None:
            return _result(url, KIND_CONTENT, None, False, "unparseable")
        host_port, path, query, _ = parsed

        role = self._host_role.get(host_port)
        if role is None:
            return _result(url, KIND_OFF_SANDBOX, None, False, "host_not_in_sandbox")

        if role == "shopping":
            return self._classify_shopping(url, path, query)
        if role == "forums":
            return self._classify_forum(url, path, query)
        if role == "wiki":
            return self._classify_wiki(url, path, query)
        # Extra sandbox roles (e.g. a gateway host) are infrastructure, not
        # citable content.
        return _result(url, KIND_SEARCH_NAV, None, None,
                       "non_content_role", host_role=role)

    # -- Magento ---------------------------------------------------------

    def _classify_shopping(self, url: str, path: str, query: str) -> dict[str, Any]:
        role = "shopping"
        # Magento serves the same routes under /index.php as well.
        if path.startswith("/index.php"):
            path = path[len("/index.php"):] or "/"
        segs = self._segments(path)

        if not segs:
            return _result(url, KIND_SEARCH_NAV, None, None, "root_page",
                           host_role=role)
        if "product_compare" in segs or (segs[0] == "catalog" and "compare" in path):
            return _result(url, KIND_SEARCH_NAV, None, None, "product_compare",
                           host_role=role)
        if segs[0] in _SHOPPING_NAV_SEGMENTS:
            return _result(url, KIND_SEARCH_NAV, None, None,
                           "search_or_nav_path", host_role=role)

        params = {k.lower() for k, _ in parse_qsl(query, keep_blank_values=True)}

        # Content shape: /<url_key>.html (query never valid on content pages,
        # stripped; trailing slash stripped; percent-encoding decoded).
        tail = unquote(path).rstrip("/")
        if tail.lower().endswith(".html"):
            url_key = tail[:-len(".html")].strip("/")
            res = self._product_membership(url, url_key, role)
            # An .html path NOT in the product registry but carrying
            # layered-nav params is a faceted category listing: navigation,
            # never a citable source (G-F2). Registry membership wins, so a
            # real product page with junk params still counts as content.
            if res["in_corpus"] is False and params & LAYERED_NAV_PARAMS:
                return _result(url, KIND_SEARCH_NAV, None, None, "layered_nav",
                               host_role=role)
            return res

        # Not content-shaped. Layered-nav params on a category-ish path are
        # faceted navigation (G-F2).
        if params & LAYERED_NAV_PARAMS:
            return _result(url, KIND_SEARCH_NAV, None, None, "layered_nav",
                           host_role=role)

        # Suffixless product citation: agents sometimes drop the .html.
        # Identity is still resolvable through the registry.
        url_key = unquote(path).strip("/")
        if url_key and "/" not in url_key:
            res = self._product_membership(url, url_key, role)
            if res["in_corpus"]:
                res["reason"] = "suffix_added"
            return res
        return _result(url, KIND_CONTENT, None,
                       None if not self.loaded else False,
                       "registry_missing" if not self.loaded else "unrecognized_shape",
                       host_role=role)

    def _product_membership(self, url: str, url_key: str, role: str) -> dict[str, Any]:
        host = self._canonical_host(role)
        if not url_key:
            return _result(url, KIND_CONTENT, None,
                           None if not self.loaded else False,
                           "registry_missing" if not self.loaded else "empty_url_key",
                           host_role=role)
        if not self.loaded:
            return _result(url, KIND_CONTENT, f"http://{host}/{url_key}.html",
                           None, "registry_missing", host_role=role)
        if url_key in self.products:
            return _result(url, KIND_CONTENT, f"http://{host}/{url_key}.html",
                           True, "product_in_registry", host_role=role)
        stored = self._products_ci.get(url_key.lower())
        if stored is not None:
            # Identity resolves case-insensitively; canonical uses the
            # registry's stored spelling (the registry is the truth).
            return _result(url, KIND_CONTENT, f"http://{host}/{stored}.html",
                           True, "case_corrected", host_role=role)
        return _result(url, KIND_CONTENT, f"http://{host}/{url_key}.html",
                       False, "unknown_url_key", host_role=role)

    # -- Postmill --------------------------------------------------------

    def _classify_forum(self, url: str, path: str, query: str) -> dict[str, Any]:
        role = "forums"
        segs = [unquote(s) for s in self._segments(path)]

        if not segs:
            return _result(url, KIND_SEARCH_NAV, None, None, "root_page",
                           host_role=role)
        if segs[0] in _FORUM_NAV_SEGMENTS:
            return _result(url, KIND_SEARCH_NAV, None, None,
                           "search_or_nav_path", host_role=role)
        if segs[0] != "f":
            return _result(url, KIND_CONTENT, None,
                           None if not self.loaded else False,
                           "registry_missing" if not self.loaded else "unrecognized_shape",
                           host_role=role)
        if len(segs) == 1:
            return _result(url, KIND_SEARCH_NAV, None, None, "forum_directory",
                           host_role=role)
        cited_forum = segs[1]
        rest = segs[2:]
        # Reddit-style exports insert a decorative /comments/ segment.
        if rest and rest[0].lower() == "comments":
            rest = rest[1:]
        if not rest:
            # /f/<forum>: the forum listing page, navigation not content.
            return _result(url, KIND_SEARCH_NAV, None, None, "forum_listing",
                           host_role=role)
        sub_id = rest[0]
        if not sub_id.isdigit():
            return _result(url, KIND_CONTENT, None,
                           None if not self.loaded else False,
                           "registry_missing" if not self.loaded else "unrecognized_shape",
                           host_role=role)
        # Identity is the numeric id. Everything after it (slug, /-/comment/N)
        # is decorative and stripped from the canonical form (G-F2: the 302
        # laundering trick dies here because we never consult HTTP).
        host = self._canonical_host(role)
        if not self.loaded:
            return _result(url, KIND_CONTENT,
                           f"http://{host}/f/{cited_forum}/{sub_id}",
                           None, "registry_missing", host_role=role)
        canonical_forum = self.submissions.get(sub_id)
        if canonical_forum is None:
            return _result(url, KIND_CONTENT,
                           f"http://{host}/f/{cited_forum}/{sub_id}",
                           False, "unknown_submission", host_role=role)
        mismatch = cited_forum.lower() != canonical_forum.lower()
        return _result(
            url, KIND_CONTENT,
            f"http://{host}/f/{canonical_forum}/{sub_id}",
            True,
            "forum_mismatch" if mismatch else "submission_in_registry",
            host_role=role,
            forum_mismatch=mismatch,
        )

    # -- Kiwix -----------------------------------------------------------

    def _classify_wiki(self, url: str, path: str, query: str) -> dict[str, Any]:
        role = "wiki"
        segs = self._segments(path)
        if not segs:
            return _result(url, KIND_SEARCH_NAV, None, None, "root_page",
                           host_role=role)
        # Kiwix /search, /suggest, /random, /viewer are navigation surfaces
        # (always 200, never sources). Only segments BEFORE the article
        # marker are checked, so an article literally titled "Search"
        # (/A/Search) cannot trip it.
        marker = max(path.rfind("/A/"), path.rfind("/wiki/"))
        lead = path[:marker] if marker != -1 else path
        lead_segs = [x for x in lead.split("/") if x]
        if any(x.lower() in _WIKI_NAV_SEGMENTS for x in lead_segs) or (
                marker == -1 and any(x.lower() in _WIKI_NAV_SEGMENTS for x in segs)):
            return _result(url, KIND_SEARCH_NAV, None, None,
                           "kiwix_search_or_nav", host_role=role)

        # Article id: the tail after the LAST /A/ marker, else after /wiki/.
        # Covers /content/<book>/A/<id>, /<book>/A/<id>, /A/<id>, /wiki/<id>,
        # /nojs/.../A/<id>. Case is PRESERVED (G-F3: kiwix-serve is
        # case-sensitive; lowercasing real citations recorded them as
        # fabrication).
        article = None
        idx = path.rfind("/A/")
        if idx != -1:
            article = path[idx + 3:]
        else:
            idx = path.rfind("/wiki/")
            if idx != -1:
                article = path[idx + 6:]
        if article is None:
            return _result(url, KIND_CONTENT, None,
                           None if not self.loaded else False,
                           "registry_missing" if not self.loaded else "unrecognized_shape",
                           host_role=role)
        article = unquote(article).strip("/").replace(" ", "_")
        if not article:
            return _result(url, KIND_CONTENT, None,
                           None if not self.loaded else False,
                           "registry_missing" if not self.loaded else "empty_article_id",
                           host_role=role)
        host = self._canonical_host(role)

        def canon(aid: str) -> str:
            return f"http://{host}/content/{self.kiwix_book}/A/{aid}"

        if not self.loaded:
            return _result(url, KIND_CONTENT, canon(article), None,
                           "registry_missing", host_role=role)
        if article in self.wiki:
            return _result(url, KIND_CONTENT, canon(article), True,
                           "article_in_registry", host_role=role)
        stored = self._wiki_ci.get(article.lower())
        if stored is not None:
            # Fuzzy compare is allowed for MEMBERSHIP (identity resolves in a
            # small corpus), but the canonical form always carries the
            # registry's original case: it is the only fetchable spelling.
            return _result(url, KIND_CONTENT, canon(stored), True,
                           "case_corrected", host_role=role)
        if self.wiki_bloom is not None:
            if article in self.wiki_bloom:
                # full-enumeration hit (FPR ~0.5%, no false negatives)
                return _result(url, KIND_CONTENT, canon(article), True,
                               "article_in_bloom", host_role=role)
            return _result(url, KIND_CONTENT, canon(article), False,
                           "unknown_article", host_role=role)
        if not self.wiki_complete:
            # partial wiki enumeration (v1): unknown is UNKNOWN, not fake
            return _result(url, KIND_CONTENT, canon(article), None,
                           "wiki_registry_partial", host_role=role)
        return _result(url, KIND_CONTENT, canon(article), False,
                       "unknown_article", host_role=role)

    # ------------------------------------------------------------------
    # Public conveniences
    # ------------------------------------------------------------------

    def canonicalize(self, url: str) -> str | None:
        """Canonical content URL for ``url``, or None when the URL is not
        content-shaped (search/nav/off-sandbox/unrecognised)."""
        return self.classify(url)["canonical"]

    def reachability_score(self, urls: Iterable[str]) -> dict[str, Any]:
        """Registry-membership reachability over a list of cited URLs.

        Scoring (per audit G-F2/F8/F10):
          * numerator / denominator run over CONTENT-SHAPED citations only;
          * in-corpus citations count toward the numerator;
          * content-shaped-but-absent AND off-sandbox citations are both
            fabricated (denominator): citing 3 real pages plus 200 invented
            external links can no longer score 1.0 (G-F10), and citing
            localhost:1 no longer vanishes from the denominator (G-F8);
          * search/nav citations are excluded from numerator AND denominator
            but counted and returned (they are not evidence, but neither are
            they fabrication);
          * no HTTP: status-0 / timeout / redirect tricks cannot occur.

        Degraded mode (registry file missing): returns score=None,
        status="unknown", registry_missing=True. Callers may fall back to the
        HTTP cache but MUST surface the flag.
        """
        details = [self.classify(u) for u in urls]
        n_in = n_fab = n_nav = n_off = n_mismatch = n_unknown = 0
        for d in details:
            if d["kind"] == KIND_SEARCH_NAV:
                n_nav += 1
            elif d["kind"] == KIND_OFF_SANDBOX:
                n_off += 1
                n_fab += 1
            elif d["in_corpus"] is True:
                n_in += 1
                if d["forum_mismatch"]:
                    n_mismatch += 1
            elif d["in_corpus"] is False:
                n_fab += 1
            else:  # in_corpus is None: degraded registry
                n_unknown += 1

        out: dict[str, Any] = {
            "score": None,
            "status": "unknown",
            "registry_missing": not self.loaded,
            "n_urls": len(details),
            "n_in_corpus": n_in,
            "n_fabricated": n_fab,
            "n_search_nav": n_nav,
            "n_off_sandbox": n_off,
            "n_forum_mismatch": n_mismatch,
            "n_unknown": n_unknown,
            "details": details,
        }
        if not self.loaded:
            return out
        denom = n_in + n_fab
        if denom == 0:
            out["status"] = "no_content_citations"
            return out
        out["score"] = n_in / denom
        out["status"] = "ok"
        return out


def reachability_score(
    urls: Iterable[str],
    registry: UrlRegistry | None = None,
) -> dict[str, Any]:
    """Module-level convenience: score ``urls`` against ``registry`` (loads
    the default registry file when none is given)."""
    reg = registry if registry is not None else UrlRegistry.load()
    return reg.reachability_score(urls)


# ---------------------------------------------------------------------------
# Inline smoke fixture (run: python3 -m src.eval.url_registry)
# ---------------------------------------------------------------------------

def _smoke() -> int:
    reg = UrlRegistry(
        products=[
            "sony-wh-1000xm4-wireless-noise-canceling-overhead-headphones",
            "jbl-tune-510bt-wireless-on-ear-headphones",
        ],
        submissions={"11813": "buyitforlife", "40352": "headphones"},
        wiki=["Noise-cancelling_headphones", "Bluetooth", "Headphones"],
    )
    checks: list[tuple[str, bool, dict[str, Any]]] = []

    def check(name: str, cond: bool, detail: dict[str, Any]) -> None:
        checks.append((name, cond, detail))

    # 1. Fake search URL rejected as navigation (200-on-empty is irrelevant).
    r = reg.classify("http://localhost:7770/catalogsearch/result/?q=quantum+headphones")
    check("search_nav rejected", r["kind"] == "search_nav" and r["in_corpus"] is None, r)
    r = reg.classify("http://localhost:8090/search?books.name=wikipedia&pattern=anc")
    check("kiwix search rejected", r["kind"] == "search_nav", r)
    r = reg.classify("http://localhost:7770/women.html?price=50-100&product_list_order=name")
    # Known-product membership wins over junk params; unknown key + facets = nav.
    check("layered nav rejected", r["kind"] == "search_nav", r)

    # 2. Decorative-forum Postmill URL: id 11813 lives in /f/buyitforlife, the
    #    citation dresses it as /f/audiophile with a slug. Identity resolves,
    #    canonical uses the REGISTRY forum, mismatch flag raised.
    r = reg.classify("http://localhost:9999/f/audiophile/11813/best-headphones-ever")
    check(
        "postmill decorative forum",
        r["in_corpus"] is True
        and r["forum_mismatch"] is True
        and r["canonical"] == "http://localhost:9999/f/buyitforlife/11813"
        and r["reason"] == "forum_mismatch",
        r,
    )
    r = reg.classify("http://localhost:9999/f/headphones/comments/40352/some-slug")
    check(
        "postmill comments segment",
        r["in_corpus"] is True and r["forum_mismatch"] is False
        and r["canonical"] == "http://localhost:9999/f/headphones/40352",
        r,
    )
    r = reg.classify("http://localhost:9999/f/headphones/99999")
    check("unknown submission fabricated", r["in_corpus"] is False
          and r["reason"] == "unknown_submission", r)
    r = reg.classify("http://localhost:9999/f/headphones")
    check("forum listing is nav", r["kind"] == "search_nav", r)

    # 3. Kiwix case preserved (G-F3): canonical keeps the registry's original
    #    case; a lowercased citation resolves but is case-corrected UP.
    r = reg.classify("http://localhost:8090/wiki/Noise-cancelling_headphones")
    check(
        "kiwix case preserved",
        r["in_corpus"] is True
        and r["canonical"]
        == "http://localhost:8090/content/wikipedia_en_all_nopic/A/Noise-cancelling_headphones",
        r,
    )
    r = reg.classify("http://localhost:8090/viewer#nonsense")  # fragment + nav
    check("kiwix viewer is nav", r["kind"] == "search_nav", r)
    r = reg.classify("http://localhost:8090/content/wikipedia_en_all_nopic/A/noise-cancelling_headphones")
    check(
        "kiwix lowercase citation case-corrected",
        r["in_corpus"] is True and r["reason"] == "case_corrected"
        and "/A/Noise-cancelling_headphones" in (r["canonical"] or ""),
        r,
    )

    # 4. Off-sandbox flagged.
    r = reg.classify("https://www.rtings.com/headphones/reviews/sony/wh-1000xm4")
    check("off_sandbox flagged", r["kind"] == "off_sandbox" and r["in_corpus"] is False, r)
    r = reg.classify("http://localhost:1/f/headphones/11813")  # G-F8 trick
    check("connection-refused port is off_sandbox", r["kind"] == "off_sandbox", r)

    # 5. Unknown product = fabricated (no HTTP, no 200-laundering).
    r = reg.classify("http://localhost:7770/quantum-flux-headphones-pro-max.html")
    check("unknown product fabricated", r["kind"] == "content"
          and r["in_corpus"] is False and r["reason"] == "unknown_url_key", r)
    r = reg.classify(
        "http://localhost:7770/index.php/sony-wh-1000xm4-wireless-noise-canceling-overhead-headphones.html?utm=x#frag"
    )
    check("known product canonicalized", r["in_corpus"] is True
          and r["canonical"]
          == "http://localhost:7770/sony-wh-1000xm4-wireless-noise-canceling-overhead-headphones.html",
          r)

    # 6. reachability_score arithmetic: 2 in-corpus + 2 fabricated (1 unknown
    #    product + 1 off-sandbox) + 1 nav excluded = 0.5.
    score = reg.reachability_score([
        "http://localhost:7770/jbl-tune-510bt-wireless-on-ear-headphones.html",
        "http://localhost:9999/f/audiophile/11813/decorative-slug",
        "http://localhost:7770/quantum-flux-headphones-pro-max.html",
        "https://www.rtings.com/anything",
        "http://localhost:7770/catalogsearch/result/?q=x",
    ])
    check(
        "reachability_score",
        score["status"] == "ok" and abs(score["score"] - 0.5) < 1e-9
        and score["n_search_nav"] == 1 and score["n_off_sandbox"] == 1
        and score["n_fabricated"] == 2 and score["n_forum_mismatch"] == 1,
        {k: v for k, v in score.items() if k != "details"},
    )

    # 7. Degraded mode: missing registry file still detects shapes but never
    #    invents membership.
    missing = UrlRegistry.load("/nonexistent/url_registry.json")
    r = missing.classify("http://localhost:7770/anything-at-all.html")
    check("degraded content unknown", r["in_corpus"] is None
          and r["reason"] == "registry_missing", r)
    r = missing.classify("http://localhost:7770/catalogsearch/result/?q=x")
    check("degraded still rejects search", r["kind"] == "search_nav", r)
    s = missing.reachability_score(["http://localhost:7770/x.html"])
    check("degraded score unknown", s["score"] is None
          and s["status"] == "unknown" and s["registry_missing"] is True,
          {k: v for k, v in s.items() if k != "details"})

    failed = 0
    for name, cond, detail in checks:
        mark = "PASS" if cond else "FAIL"
        if not cond:
            failed += 1
        print(f"[{mark}] {name}")
        if not cond:
            print(f"       {detail}")
    print(f"\n{len(checks) - failed}/{len(checks)} smoke checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_smoke())
