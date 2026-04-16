"""Shopping Admin (Magento backend) scraper.

Magento admin has no public REST API for most backend data, so we scrape
the HTML pages after logging in via requests session.

Default credentials: admin / admin1234 (WebArena defaults).
"""

from __future__ import annotations

import os
import re
from typing import Any

import requests
from bs4 import BeautifulSoup

SHOPPING_ADMIN = os.environ.get("SHOPPING_ADMIN", "http://localhost:7780").rstrip("/")

_SESS = requests.Session()
_LOGGED_IN = False


def _login() -> None:
    global _LOGGED_IN
    if _LOGGED_IN:
        return
    # Fetch login page to get form_key
    r = _SESS.get(f"{SHOPPING_ADMIN}/admin/", timeout=20, allow_redirects=True)
    soup = BeautifulSoup(r.text, "html.parser")
    form_key_el = soup.select_one('input[name="form_key"]')
    form_key = form_key_el["value"] if form_key_el else ""
    _SESS.post(
        f"{SHOPPING_ADMIN}/admin/admin/dashboard/",
        data={
            "form_key": form_key,
            "login[username]": "admin",
            "login[password]": "admin1234",
        },
        timeout=20,
        allow_redirects=True,
    )
    _LOGGED_IN = True


def _get(path: str) -> BeautifulSoup:
    _login()
    r = _SESS.get(f"{SHOPPING_ADMIN}{path}", timeout=30, allow_redirects=True)
    return BeautifulSoup(r.text, "html.parser")


def dashboard_summary() -> dict:
    """Get dashboard summary stats (revenue, orders, etc.)."""
    soup = _get("/admin/dashboard/")
    info: dict[str, str] = {}
    for card in soup.select(".dashboard-totals-item, .dashboard-item"):
        label = card.select_one(".label, .title")
        value = card.select_one(".value, .amount")
        if label and value:
            info[label.get_text(strip=True)] = value.get_text(strip=True)
    return info


def recent_orders(limit: int = 20) -> list[dict]:
    """Get recent orders from admin panel."""
    soup = _get("/admin/sales/order/")
    orders = []
    for row in soup.select("table tbody tr")[:limit]:
        cells = row.select("td")
        if len(cells) >= 5:
            orders.append({
                "order_id": cells[0].get_text(strip=True),
                "customer": cells[1].get_text(strip=True) if len(cells) > 1 else "",
                "total": cells[2].get_text(strip=True) if len(cells) > 2 else "",
                "status": cells[3].get_text(strip=True) if len(cells) > 3 else "",
                "date": cells[4].get_text(strip=True) if len(cells) > 4 else "",
            })
    return orders


def product_inventory(search: str = "", limit: int = 20) -> list[dict]:
    """Search product catalog from admin side."""
    path = "/admin/catalog/product/"
    if search:
        path += f"?keyword={requests.utils.quote(search)}"
    soup = _get(path)
    products = []
    for row in soup.select("table tbody tr, .data-grid-row")[:limit]:
        cells = row.select("td, .data-grid-cell-content")
        if len(cells) >= 4:
            products.append({
                "id": cells[0].get_text(strip=True),
                "name": cells[1].get_text(strip=True) if len(cells) > 1 else "",
                "sku": cells[2].get_text(strip=True) if len(cells) > 2 else "",
                "price": cells[3].get_text(strip=True) if len(cells) > 3 else "",
                "stock": cells[4].get_text(strip=True) if len(cells) > 4 else "",
            })
    return products


def customer_list(limit: int = 20) -> list[dict]:
    """List customers from admin panel."""
    soup = _get("/admin/customer/index/")
    customers = []
    for row in soup.select("table tbody tr")[:limit]:
        cells = row.select("td")
        if len(cells) >= 3:
            customers.append({
                "name": cells[0].get_text(strip=True),
                "email": cells[1].get_text(strip=True) if len(cells) > 1 else "",
                "group": cells[2].get_text(strip=True) if len(cells) > 2 else "",
            })
    return customers


def browse_admin_page(path: str) -> str:
    """Generic admin page fetch, returns text content."""
    soup = _get(path)
    # Remove scripts/styles
    for tag in soup.select("script, style, nav, header"):
        tag.decompose()
    return soup.get_text(" ", strip=True)[:5000]
