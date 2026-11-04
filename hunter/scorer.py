"""Module 4 — scoring engine.

opportunity = demand_score / (competition_score + 1)

demand_score (0..100) combines:
  - Google Trends avg_interest (0..100) .......... 40%
  - listing-count signal: log-scaled total_results . 30%
  - favorites signal: avg favorites of sampled physical listings, log-scaled .. 30%

Filters (configurable): price band default $15–60, physical products only
(digital listings are excluded before scoring).
"""
import math


def _log_scale(x: float, cap: float = 100.0) -> float:
    if not x or x <= 0:
        return 0.0
    return min(cap, math.log10(x + 1) * 25.0)


def demand_score(trend: dict, miner_result: dict, ebay: dict | None = None,
                 include_digital: bool = False) -> tuple:
    """Returns (combined_demand, ebay_demand_or_None).

    eBay sold data is REAL sales data, so it weighs heavily (50%) when
    available; the trend/listing-count/favorites signals make up the rest.
    """
    t = (trend or {}).get("avg_interest") or 0.0
    total = miner_result.get("total_results") or 0
    listings = [l for l in (miner_result.get("listings") or [])
                if include_digital or not l.get("is_digital")]
    favs = [l["favorites"] for l in listings
            if isinstance(l.get("favorites"), (int, float))]
    fav_signal = _log_scale(sum(favs) / len(favs)) if favs else 0.0
    base = 0.40 * min(100.0, t) + 0.30 * _log_scale(total) + 0.30 * fav_signal

    ebay_d = None
    if ebay and not ebay.get("error"):
        ebay_d = ebay.get("demand_score") or 0.0
        combined = round(0.5 * ebay_d + 0.5 * base, 1)
    else:
        combined = round(base, 1)
    return combined, ebay_d


def score_keyword(keyword: str, trend: dict, miner_result: dict,
                  competition: dict, price_band: tuple = (15.0, 60.0),
                  ebay: dict | None = None,
                  include_digital: bool = False) -> dict:
    d, ebay_d = demand_score(trend, miner_result, ebay, include_digital)
    c = competition.get("competition_score", 50.0)
    opportunity = round(d / (c + 1), 3)

    listings = [l for l in (miner_result.get("listings") or [])
                if include_digital or not l.get("is_digital")]
    lo, hi = price_band
    in_band = [l for l in listings
               if isinstance(l.get("price"), (int, float)) and lo <= l["price"] <= hi]

    top = [
        {k: l.get(k) for k in ("listing_id", "title", "price",
                              "currency", "favorites", "shop_name", "url",
                              "image_url")}
        for l in in_band[:8]
    ]
    hero = next((l["image_url"] for l in top if l.get("image_url")), None)
    if not hero:
        hero = (ebay or {}).get("sample_image_url")  # market fallback

    return {
        "keyword": keyword,
        "opportunity_score": opportunity,
        "demand_score": d,
        "competition_score": c,        "trend_avg_interest": (trend or {}).get("avg_interest"),
        "trend_rising": (trend or {}).get("rising_queries", [])[:5],
        "total_results": miner_result.get("total_results"),
        "avg_price": competition.get("avg_price"),
        "physical_sampled": len(listings),
        "in_price_band": len(in_band),
        "ebay_total_sold": (ebay or {}).get("total_sold"),
        "ebay_sell_through": (ebay or {}).get("sell_through"),
        "ebay_avg_sold_price": (ebay or {}).get("sold_avg_price"),
        "ebay_demand_score": ebay_d,
        "ebay_error": (ebay or {}).get("error"),
        "top_listings": top,
        # Hero image for the keyword card: first listing image, else an
        # eBay market-sample image, else None (UI shows a placeholder).
        "hero_image_url": hero,
        "source": miner_result.get("source"),
    }


def rank(results: list) -> list:
    return sorted(results, key=lambda r: r["opportunity_score"], reverse=True)
