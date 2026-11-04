"""Module 2 — Etsy demand miner. Two paths:

(a) Official Etsy API v3 (legit path): needs ETSY_API_KEY env var.
    GET https://openapi.etsy.com/v3/application/listings/active
(b) Scraper fallback: curl_cffi (Chrome impersonation) on public search pages,
    DOM parsing of listing cards. Conservative: sleeps between requests,
    small batches.

Both return the same shape:
  {source, keyword, total_results, listings: [
     {listing_id, title, price, currency, favorites, shop_name, url,
      image_url, is_digital}]}
image_url is the source-provided product image (Etsy listing-images API for
the official path, card <img> for the scraper path); None when unavailable.
For the API path images are fetched lazily via fetch_listing_image() (one
extra call per listing) — the pipeline only enriches the top listings that
are actually surfaced, so search_api() itself leaves image_url as None.
"""
import json
import os
import random
import re
import time
import urllib.parse

from bs4 import BeautifulSoup
from curl_cffi import requests as crequests

DIGITAL_HINTS = ("digital", "download", "printable", "svg", "pattern", "pdf",
                 "template", "clipart", "stencil", "tutorial", "ebook")


def _is_digital(title: str) -> bool:
    t = (title or "").lower()
    return any(h in t for h in DIGITAL_HINTS)


def fetch_listing_image(listing_id: str, api_key: str) -> str | None:
    """Fetch the primary product image for one Etsy listing via API v3.

    Returns the 570xN rendition URL of the first image, or None on any
    failure. One HTTP call per listing — call sparingly (top listings only).
    """
    if not listing_id or not api_key:
        return None
    url = f"https://openapi.etsy.com/v3/application/listings/{listing_id}/images"
    try:
        r = crequests.get(url, params={"limit": 1},
                          headers={"x-api-key": api_key},
                          timeout=20, impersonate="chrome")
        if r.status_code != 200:
            return None
        imgs = r.json().get("results", [])
        if not imgs:
            return None
        img = imgs[0]
        return img.get("url_570xN") or img.get("url_fullxfull") or None
    except Exception:
        return None


# ---------------------------------------------------------------- API path
def search_api(keyword: str, limit: int = 25) -> dict:
    """Official Etsy API v3. Returns dict or {'error': ...}."""
    api_key = os.environ.get("ETSY_API_KEY", "").strip()
    if not api_key:
        return {"error": "API key not configured (set ETSY_API_KEY env var)"}
    url = "https://openapi.etsy.com/v3/application/listings/active"
    params = {"keywords": keyword, "limit": limit, "sort_on": "created",
              "sort_order": "desc"}
    headers = {"x-api-key": api_key}
    try:
        r = crequests.get(url, params=params, headers=headers, timeout=30,
                          impersonate="chrome")
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

    listings = []
    for item in data.get("results", []):
        price = item.get("price") or {}
        amount = price.get("amount")
        divisor = price.get("divisor") or 1
        listings.append({
            "listing_id": str(item.get("listing_id", "")),
            "title": item.get("title", ""),
            "price": (amount / divisor) if isinstance(amount, (int, float)) else None,
            "currency": price.get("currency_code"),
            "favorites": item.get("num_favorers"),
            "shop_name": "",
            "url": item.get("url", ""),
            # Enriched lazily via fetch_listing_image() (top listings only).
            "image_url": None,
            "is_digital": bool(item.get("is_digital", _is_digital(item.get("title", "")))),
        })
    return {
        "source": "etsy_api_v3",
        "keyword": keyword,
        "total_results": data.get("count"),
        "listings": listings,
    }


# ------------------------------------------------------------- scraper path
def _fetch(url: str, timeout: int = 30):
    time.sleep(random.uniform(2.5, 5.0))  # polite pacing
    return crequests.get(
        url,
        impersonate="chrome",
        headers={
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        },
        timeout=timeout,
    )


def _card_image(el) -> str | None:
    """Best-effort product image URL from a search-result card element.

    Prefers data-src, then src, then the largest srcset candidate.
    Returns None when no image tag is found.
    """
    img = el.find("img")
    if not img:
        return None
    for attr in ("data-src", "data-lazy-src", "src"):
        src = (img.get(attr) or "").strip()
        if src and not src.startswith("data:"):
            return src
    srcset = (img.get("srcset") or "").strip()
    if srcset:
        # last candidate is usually the largest rendition
        parts = [p.strip().split(" ")[0] for p in srcset.split(",") if p.strip()]
        parts = [p for p in parts if p and not p.startswith("data:")]
        if parts:
            return parts[-1]
    return None


def _parse_search_page(html: str) -> tuple:
    """Returns (total_results:int|None, cards:list[dict])."""
    soup = BeautifulSoup(html, "lxml")
    total = None
    # Etsy header shows e.g. "(12,345 Results)" or "12,345 Results"
    for tag in soup.find_all(string=re.compile(r"[\d,]+\s+Results?")):
        m = re.search(r"([\d,]+)\s+Results?", tag)
        if m:
            total = int(m.group(1).replace(",", ""))
            break

    cards = []
    seen = set()
    for el in soup.find_all(attrs={"data-listing-id": True}):
        lid = str(el.get("data-listing-id"))
        if not lid or lid in seen:
            continue
        seen.add(lid)
        title_el = el.find("h3") or el.find(attrs={"data-listing-title": True})
        title = title_el.get_text(" ", strip=True) if title_el else ""
        price = None
        currency = None
        price_el = el.find(class_=re.compile(r"currency-value"))
        if price_el:
            m = re.search(r"[\d,.]+", price_el.get_text(strip=True).replace(",", ""))
            if m:
                try:
                    price = float(m.group(0))
                except ValueError:
                    price = None
            cur_el = el.find(class_=re.compile(r"currency-symbol"))
            if cur_el:
                currency = cur_el.get_text(strip=True)
        shop = ""
        shop_el = el.find("a", href=re.compile(r"/shop/"))
        if shop_el:
            shop = shop_el.get_text(" ", strip=True)
        url = f"https://www.etsy.com/listing/{lid}"
        a_el = el.find("a", href=re.compile(r"/listing/"))
        if a_el and a_el.get("href"):
            href = a_el["href"].split("?")[0]
            if href.startswith("http"):
                url = href
            elif href.startswith("/"):
                url = "https://www.etsy.com" + href
        cards.append({
            "listing_id": lid,
            "title": title,
            "price": price,
            "currency": currency or "USD",
            "favorites": None,  # filled from detail pages for top items
            "shop_name": shop,
            "url": url,
            "image_url": _card_image(el),
            "is_digital": _is_digital(title),
        })
    return total, cards


def _fetch_favorites(listing_id: str):
    """Best-effort: read num_favorers from the public listing page."""
    try:
        r = _fetch(f"https://www.etsy.com/listing/{listing_id}")
        if r.status_code != 200:
            return None
        m = re.search(r'"num_favorers"\s*:\s*(\d+)', r.text)
        if m:
            return int(m.group(1))
        m = re.search(r"([\d,]+)\s+people have this in their carts", r.text)
        if m:
            return int(m.group(1).replace(",", ""))
    except Exception:
        pass
    return None


def search_scrape(keyword: str, max_cards: int = 24,
                  detail_favorites: int = 3) -> dict:
    """Public-search scraping fallback. Small batches, polite pacing."""
    q = urllib.parse.quote_plus(keyword)
    url = f"https://www.etsy.com/search?q={q}"
    try:
        r = _fetch(url)
        if r.status_code != 200:
            return {"error": f"HTTP {r.status_code} on Etsy search page"}
        total, cards = _parse_search_page(r.text)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

    cards = cards[:max_cards]
    for card in cards[:detail_favorites]:
        card["favorites"] = _fetch_favorites(card["listing_id"])
    return {
        "source": "etsy_scrape",
        "keyword": keyword,
        "total_results": total,
        "listings": cards,
    }


def search(keyword: str, max_cards: int = 24) -> dict:
    """Try API first (if key configured), else scraper fallback."""
    if os.environ.get("ETSY_API_KEY", "").strip():
        res = search_api(keyword, limit=max_cards)
        if "error" not in res:
            return res
    return search_scrape(keyword, max_cards=max_cards)


if __name__ == "__main__":
    print(json.dumps(search("ceramic mug", max_cards=6), indent=2)[:4000])
