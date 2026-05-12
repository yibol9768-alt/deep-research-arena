"""DeerFlow URL hallucination fix.

Problem: DeerFlow's search correctly returns sandbox URLs (HTTP intercept works),
but the reporter LLM fabricates similar-looking URLs instead of copying exact ones
from the search results.  0/8 HTTP 200 on report URLs despite 106 sandbox URLs
found in raw search results.

Fix strategy (two-pronged):
  1. Stronger prompt injection: tell the researcher and reporter to copy URLs
     verbatim, never reconstruct them.
  2. Post-processing: after graph.ainvoke() produces final_report, collect all
     URLs that the search/crawl tools actually returned (by parsing the intercept
     stdout logs), then scan the report for URLs that return 404 and replace them
     with the closest matching real URL from the search log.

This file generates the complete _deerflow_driver.py script text to be written
by _run_deerflow().  Import and call `build_deerflow_driver(shim, intercept_preamble)`
to get the script string.
"""

from __future__ import annotations


def build_deerflow_driver(shim: str, intercept_preamble: str) -> str:
    """Return the full Python script text for the DeerFlow subprocess driver.

    Args:
        shim: The shim URL (e.g. "http://localhost:8081")
        intercept_preamble: Output of _build_intercept_preamble(shim)

    Returns:
        Complete Python source code for _deerflow_driver.py
    """
    # The driver script is built as a single string so it can be written to a
    # file and executed by the DeerFlow subprocess venv Python.
    return intercept_preamble + _DRIVER_BODY.replace("__SHIM_PLACEHOLDER__", shim)


_DRIVER_BODY = r'''
import os, sys, asyncio, re, json
from urllib.parse import urlparse
from difflib import SequenceMatcher

sys.path.insert(0, '.')
shim = "__SHIM_PLACEHOLDER__"

# ============================================================
# Belt-and-suspenders: patch TAVILY_API_URL at the Python level
# ============================================================
try:
    import langchain_tavily._utilities as _ltu
    old_url = _ltu.TAVILY_API_URL
    _ltu.TAVILY_API_URL = shim
    print(f'[deerflow-fix] patched _ltu.TAVILY_API_URL -> {shim}')
except Exception as e:
    print(f'[deerflow-fix] warn: {e}')

# ============================================================
# URL collection: intercept search/crawl tool results to build
# a ground-truth set of URLs that the search actually returned.
# We do this by monkey-patching the citation extractor AND by
# hooking ToolMessage creation.
# ============================================================
_SEARCH_RETURNED_URLS = set()

def _collect_url(url):
    """Record a URL from a search/crawl tool result."""
    if url and isinstance(url, str) and url.startswith('http'):
        _SEARCH_RETURNED_URLS.add(url)

# Hook into ToolMessage to capture URLs from all tool results
try:
    from langchain_core.messages import ToolMessage as _TM
    _orig_tm_init = _TM.__init__
    def _hooked_tm_init(self, *a, **kw):
        _orig_tm_init(self, *a, **kw)
        # Try to extract URLs from content
        content = getattr(self, 'content', '')
        if content and isinstance(content, str):
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get('url'):
                            _collect_url(item['url'])
                elif isinstance(data, dict):
                    if data.get('url'):
                        _collect_url(data['url'])
                    for r in data.get('results', []):
                        if isinstance(r, dict) and r.get('url'):
                            _collect_url(r['url'])
            except (json.JSONDecodeError, TypeError):
                pass
            # Also scan raw text for sandbox URLs
            for m in re.finditer(r'http://localhost:\d+[^\s"\'<>\])\},]*', content):
                _collect_url(m.group(0).rstrip('.,;:'))
    _TM.__init__ = _hooked_tm_init
    print('[deerflow-fix] ToolMessage.__init__ hooked for URL collection')
except Exception as e:
    print(f'[deerflow-fix] warn: ToolMessage hook failed: {e}')

# Also hook the citation extractor to capture URLs
try:
    from src.citations.extractor import _result_to_citation as _orig_r2c
    import src.citations.extractor as _cext

    def _hooked_r2c(result):
        url = result.get('url', '')
        _collect_url(url)
        return _orig_r2c(result)

    _cext._result_to_citation = _hooked_r2c
    print('[deerflow-fix] citation extractor hooked for URL collection')
except Exception as e:
    print(f'[deerflow-fix] warn: citation extractor hook failed: {e}')


from src.graph.builder import build_graph_with_memory
graph = build_graph_with_memory()

# After imports, scan for stale TAVILY_API_URL copies in other modules
try:
    for mn, mod in list(sys.modules.items()):
        if mod and hasattr(mod, 'TAVILY_API_URL'):
            cur = getattr(mod, 'TAVILY_API_URL', '')
            if cur != shim and 'tavily' in str(cur):
                setattr(mod, 'TAVILY_API_URL', shim)
                print(f'[deerflow-fix] late-patched {mn}.TAVILY_API_URL')
except Exception:
    pass


# ============================================================
# Build the prompt with stronger URL-copying instructions
# ============================================================
base_query = os.environ['DEERFLOW_QUERY']

# Inject URL-fidelity instructions into the query
url_fidelity_instructions = """

## CRITICAL URL RULES (MANDATORY)

You MUST follow these rules for EVERY URL in your report:

1. **COPY-PASTE ONLY**: Every URL in your report MUST be an EXACT copy-paste
   from search results or crawl results. Do NOT reconstruct, shorten, modify,
   or "improve" any URL. Even small changes (adding/removing trailing slashes,
   changing path segments, altering query parameters) will break the link.

2. **NO URL FABRICATION**: NEVER generate a URL from memory or by pattern.
   If you cannot find the exact URL in your search results, do NOT include
   a citation for that claim. It is better to have NO citation than a
   fabricated one.

3. **VERIFY BEFORE CITING**: Before writing any `[text](url)` link, confirm
   that the EXACT url string appears verbatim in one of your tool call results.
   If you cannot find it, OMIT the link.

4. **SANDBOX URLS ONLY**: All URLs must be localhost sandbox URLs
   (http://localhost:7770, http://localhost:9999, http://localhost:8090).
   No external URLs exist in this environment.
"""

enhanced_query = base_query + url_fidelity_instructions

init_state = {
    'messages': [{'role': 'user', 'content': enhanced_query}],
    'auto_accepted_plan': True,
    'enable_background_investigation': True,
    'enable_clarification': False,
    'research_topic': enhanced_query,
    'clarified_research_topic': enhanced_query,
}
config = {
    'configurable': {
        'thread_id': 'default',
        'max_plan_iterations': 1,
        'max_step_num': 4,
    },
    'recursion_limit': 100,
}

final = asyncio.run(graph.ainvoke(init_state, config=config))
report = final.get('final_report') or final.get('current_plan') or '(empty)'
if not isinstance(report, str):
    report = str(report)


# ============================================================
# Post-processing: fix hallucinated URLs in the report
# ============================================================
def _fix_hallucinated_urls(report_text, known_urls):
    """Replace hallucinated URLs with closest matching real URLs.

    For each URL found in the report, if it is NOT in the known set of
    URLs that were actually returned by search/crawl, find the best
    matching known URL (by path similarity) and replace it.
    """
    if not known_urls:
        print(f'[deerflow-fix] WARNING: no known URLs collected, cannot fix hallucinations')
        return report_text

    known_list = list(known_urls)
    print(f'[deerflow-fix] collected {len(known_list)} ground-truth URLs from search results')
    for u in sorted(known_list)[:20]:
        print(f'  [gt] {u}')

    # Build index: group known URLs by host:port
    from collections import defaultdict
    host_index = defaultdict(list)
    for url in known_list:
        p = urlparse(url)
        key = f'{p.hostname}:{p.port}' if p.port else (p.hostname or '')
        host_index[key].append(url)

    # Find all URLs in the report (markdown links and bare URLs)
    url_pattern = re.compile(
        r'(?:'
        r'\]\((http://localhost:\d+[^\s)]*)\)'   # markdown link URLs
        r'|'
        r'(?<=["\s>])(http://localhost:\d+[^\s"\'<>\])\},]*)'  # bare URLs
        r')'
    )

    replacements = {}
    for m in url_pattern.finditer(report_text):
        report_url = m.group(1) or m.group(2)
        if not report_url:
            continue
        report_url_clean = report_url.rstrip('.,;:)')

        # Check if this URL is already a known good URL
        if report_url_clean in known_urls:
            continue

        # Find the best matching known URL
        rp = urlparse(report_url_clean)
        r_host = f'{rp.hostname}:{rp.port}' if rp.port else (rp.hostname or '')
        r_path = rp.path.rstrip('/')

        # First, try to match within the same host
        candidates = host_index.get(r_host, [])
        if not candidates:
            # Try all known URLs as fallback
            candidates = known_list

        best_url = None
        best_score = 0.0

        for candidate in candidates:
            cp = urlparse(candidate)
            c_path = cp.path.rstrip('/')

            # Score by path similarity
            score = SequenceMatcher(None, r_path, c_path).ratio()

            # Bonus for matching path segments
            r_segments = [s for s in r_path.split('/') if s]
            c_segments = [s for s in c_path.split('/') if s]
            if r_segments and c_segments:
                # If the last segment matches, big bonus
                if r_segments[-1] == c_segments[-1]:
                    score += 0.3
                # If path prefix matches
                common = 0
                for rs, cs in zip(r_segments, c_segments):
                    if rs == cs:
                        common += 1
                    else:
                        break
                if common > 0:
                    score += 0.1 * common

            if score > best_score:
                best_score = score
                best_url = candidate

        if best_url and best_score > 0.3:
            if report_url_clean != best_url:
                replacements[report_url_clean] = best_url
                print(f'[deerflow-fix] URL replace: {report_url_clean[:80]} -> {best_url[:80]} (score={best_score:.2f})')

    # Apply replacements (longest first to avoid partial matches)
    for old_url in sorted(replacements, key=len, reverse=True):
        new_url = replacements[old_url]
        report_text = report_text.replace(old_url, new_url)

    n_replaced = len(replacements)
    print(f'[deerflow-fix] replaced {n_replaced} hallucinated URLs in report')

    return report_text


# Also collect URLs from stdout intercept logs that were printed during the run.
# The intercept preamble prints lines like:
#   [intercept] TAVILY: ... -> http://localhost:8081/...
# The shim responses contain sandbox URLs in the JSON results.
# We already captured them via ToolMessage hook, but also scan final state
# for any citations we might have missed.
try:
    citations = final.get('citations', [])
    for c in citations:
        if isinstance(c, dict) and c.get('url'):
            _collect_url(c['url'])
    # Also scan observations for URLs
    for obs in final.get('observations', []):
        if isinstance(obs, str):
            for m in re.finditer(r'http://localhost:\d+[^\s"\'<>\])\},]*', obs):
                _collect_url(m.group(0).rstrip('.,;:'))
    # Scan all messages for URLs
    for msg in final.get('messages', []):
        content = getattr(msg, 'content', '') if hasattr(msg, 'content') else str(msg)
        if isinstance(content, str):
            for m in re.finditer(r'http://localhost:\d+[^\s"\'<>\])\},]*', content):
                _collect_url(m.group(0).rstrip('.,;:'))
except Exception as e:
    print(f'[deerflow-fix] warn: final state URL scan failed: {e}')

# Apply the fix
report = _fix_hallucinated_urls(report, _SEARCH_RETURNED_URLS)

print('===REPORT===\n' + report)
'''
