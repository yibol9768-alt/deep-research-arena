"""Shared scrapers for WebArena / Magento 2 Luma storefront.

All functions take a Playwright `Page` and are synchronous.
"""

from __future__ import annotations

from typing import Any


LIST_JS = r"""
() => {
  const items = [];
  document.querySelectorAll('li.item.product.product-item, .products-grid .product-item').forEach(el => {
    const a = el.querySelector('a.product-item-link, .product-item-name a');
    const name = a ? a.innerText.trim() : '';
    const url  = a ? a.href : '';
    let price = null;
    const pEl = el.querySelector('[data-price-amount]');
    if (pEl && pEl.getAttribute('data-price-amount')) {
      price = parseFloat(pEl.getAttribute('data-price-amount'));
    } else {
      const ptxt = el.querySelector('.price');
      if (ptxt) {
        const m = ptxt.innerText.match(/([0-9][0-9,]*\.?[0-9]*)/);
        if (m) price = parseFloat(m[1].replace(/,/g,''));
      }
    }
    let rating = null;
    const r = el.querySelector('.rating-result');
    if (r) {
      const title = r.getAttribute('title') || (r.querySelector('span') && r.querySelector('span').getAttribute('title')) || '';
      const m = title.match(/([0-9]+)%/);
      if (m) rating = Math.round(parseInt(m[1]) / 20 * 10) / 10;
    }
    items.push({name, product_url: url, price, rating});
  });
  return JSON.stringify(items);
}
"""

PRODUCT_JS = r"""
() => {
  const out = {};
  const name = document.querySelector('h1.page-title span.base, .page-title .base');
  out.name = name ? name.innerText.trim() : '';
  const pEl = document.querySelector('[data-price-amount]');
  out.price = pEl ? parseFloat(pEl.getAttribute('data-price-amount')) : null;
  const r = document.querySelector('.rating-result');
  if (r) {
    const title = r.getAttribute('title') || (r.querySelector('span') && r.querySelector('span').getAttribute('title')) || '';
    const m = title.match(/([0-9]+)%/);
    out.rating = m ? Math.round(parseInt(m[1]) / 20 * 10) / 10 : null;
  } else {
    out.rating = null;
  }
  const rc = document.querySelector('.reviews-actions a, .review-count, a[href*="#reviews"]');
  if (rc) {
    const m = rc.innerText.match(/([0-9]+)/);
    out.review_count = m ? parseInt(m[1]) : null;
  } else {
    out.review_count = null;
  }
  out.product_url = document.location.href;
  return JSON.stringify(out);
}
"""

REVIEWS_JS = r"""
() => {
  const reviews = [];
  document.querySelectorAll('li.item.review-item, .review-item').forEach(el => {
    const author = el.querySelector('.review-details-value, [itemprop="author"], .review-author strong, .review-author');
    const body   = el.querySelector('.review-content, [itemprop="description"], .review-body');
    const title  = el.querySelector('.review-title');
    const ratEl  = el.querySelector('.rating-result [title]');
    let rating = null;
    if (ratEl) {
      const m = ratEl.getAttribute('title').match(/([0-9]+)%/);
      if (m) rating = Math.round(parseInt(m[1]) / 20);
    }
    reviews.push({
      author: author ? author.innerText.trim() : '',
      title:  title  ? title.innerText.trim()  : '',
      body:   body   ? body.innerText.trim()   : '',
      rating
    });
  });
  return JSON.stringify(reviews);
}
"""


def _loadjs(page: Any, js: str) -> Any:
    import json as _json
    raw = page.evaluate(js) or "[]"
    try:
        return _json.loads(raw)
    except Exception:
        return []


def list_products(page: Any) -> list[dict]:
    """Return current listing page's product items."""
    return _loadjs(page, LIST_JS)


def product_details(page: Any) -> dict:
    d = _loadjs(page, PRODUCT_JS)
    return d if isinstance(d, dict) else {}


def list_reviews(page: Any) -> list[dict]:
    """Return reviews visible on the current page (reviews tab or AJAX page)."""
    return _loadjs(page, REVIEWS_JS)
