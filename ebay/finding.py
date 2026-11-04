"""eBay Finding API integration (key-only, no OAuth).

Public endpoints used:
  findCompletedItems (SoldItemsOnly) -> real SOLD sales data
  findItemsByKeywords               -> active listing count (competition side)

Response shape (JSON):
  {"findCompletedItemsResponse": [{"ack": ["Success"],
    "searchResult": [{"@count": "N", "item": [...]}],
    "paginationOutput": [{"totalEntries": ["T"], "totalPages": ["P"]}]}]}
Each item: {"itemId": [...], "title": [...],
            "sellingStatus": [{"currentPrice": [{"@currencyId": "USD", "__value__": "19.99"}]}]}
"""
import json
import math
import os
import time
import urllib.parse
import urllib.request

BASE = "https://svcs.ebay.com/services/search/FindingService/v1"
HEADERS = {
    "X-EBAY-SOA-OPERATION-NAME": "findCompletedItems",
    "X-EBAY-SOA-SERVICE-VERSION": "1.0.0",
    "X-EBAY-SOA-REQUEST-DATA-FORMAT": "JSON",
    "X-EBAY-SOA-RESPONSE-DATA-FORMAT": "JSON",
    "X-EBAY-SOA-GLOBAL-ID": "EBAY-US",
}


def _get(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _params(app_id: str, op: str, keyword: str, sold_only: bool) -> str:
    q = {
        "OPERATION-NAME": op,
        "SERVICE-VERSION": "1.0.0",
        "SECURITY-APPNAME": app_id,
        "RESPONSE-DATA-FORMAT": "JSON",
        "REST-PAYLOAD": "",
        "keywords": keyword,
        "paginationInput.entriesPerPage": "100",
        "paginationInput.pageNumber": "1",
    }
    if sold_only:
        q["itemFilter(0).name"] = "SoldItemsOnly"
        q["itemFilter(0).value"] = "true"
    return BASE + "?" + urllib.parse.urlencode(q)


def _resp_body(data: dict, op_key: str):
    """Return (ack, body) for the operation wrapper key."""
    body = (data.get(op_key) or [{}])[0]
    ack = (body.get("ack") or ["Failure"])[0]
    return ack, body


def _total_entries(body: dict) -> int:
    pag = (body.get("paginationOutput") or [{}])[0]
    try:
        return int((pag.get("totalEntries") or ["0"])[0])
    except (ValueError, TypeError):
        return 0


def _sold_prices(body: dict):
    prices = []
    search = (body.get("searchResult") or [{}])[0]
    for item in search.get("item") or []:
        status = (item.get("sellingStatus") or [{}])[0]
        price = (status.get("currentPrice") or [{}])[0]
        try:
            prices.append(float(price.get("__value__")))
        except (TypeError, ValueError):
            continue
    return prices


def _sample_image(active_body: dict) -> str | None:
    """galleryURL of the first active listing — a representative product
    image for this keyword's market (not an Etsy listing image)."""
    search = (active_body.get("searchResult") or [{}])[0]
    items = search.get("item") or []
    if not items:
        return None
    gal = (items[0].get("galleryURL") or [None])[0]
    if gal and gal.startswith("http"):
        return gal
    return None


def _demand_score(total_sold: int, sell_through: float) -> float:
    volume = min(100.0, math.log10(total_sold + 1) * 25.0) if total_sold > 0 else 0.0
    velocity = min(100.0, sell_through * 100.0)
    return round(0.6 * volume + 0.4 * velocity, 1)


def research_keyword(app_id: str, keyword: str) -> dict:
    """Research one keyword on eBay. Returns dict with real sold data.

    On any API-level failure returns {"error": ...}.
    """
    if not app_id:
        return {"error": "eBay key not configured (set EBAY_APP_ID)"}

    try:
        sold_data = _get(_params(app_id, "findCompletedItems", keyword, True))
        time.sleep(0.5)  # polite pacing between the two calls
        active_data = _get(_params(app_id, "findItemsByKeywords", keyword, False))
    except Exception as e:  # network / timeout / HTTP errors
        return {"error": f"eBay API request failed: {e}"}

    ack, sold_body = _resp_body(sold_data, "findCompletedItemsResponse")
    if ack != "Success":
        msg = (sold_body.get("errorMessage") or [{}])[0]
        return {"error": f"eBay sold-items call failed (ack={ack}): {msg}"}
    ack2, active_body = _resp_body(active_data, "findItemsByKeywordsResponse")
    if ack2 != "Success":
        msg = (active_body.get("errorMessage") or [{}])[0]
        return {"error": f"eBay active-items call failed (ack={ack2}): {msg}"}

    total_sold = _total_entries(sold_body)
    active_count = _total_entries(active_body)
    prices = _sold_prices(sold_body)
    sell_through = round(min(1.0, total_sold / active_count), 3) if active_count else 0.0

    return {
        "source": "ebay",
        "keyword": keyword,
        "total_sold": total_sold,
        "active_count": active_count,
        "sell_through": sell_through,
        "sold_avg_price": round(sum(prices) / len(prices), 2) if prices else None,
        "sold_min_price": round(min(prices), 2) if prices else None,
        "sold_max_price": round(max(prices), 2) if prices else None,
        "sold_sampled": len(prices),
        "demand_score": _demand_score(total_sold, sell_through),
        # Representative market image (first active listing's galleryURL).
        "sample_image_url": _sample_image(active_body),
    }


def get_app_id() -> str | None:
    return os.environ.get("EBAY_APP_ID")
