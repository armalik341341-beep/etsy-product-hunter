"""Module 3 — competition analyzer.

Input: miner result dict {total_results, listings:[{price, shop_name, ...}]}.
Output: competition metrics + a 0-100 competition score (higher = more crowded).

competition_score combines:
  - listing-count pressure: log10(total_results) scaled
  - price-band crowding: share of listings inside the hunter's price band
  - shop concentration: fewer distinct shops among top listings => a few
    dominant sellers (harder to break in)
"""
import math
from statistics import mean, median


def analyze(miner_result: dict, price_band: tuple = (15.0, 60.0),
            include_digital: bool = False) -> dict:
    listings = [l for l in (miner_result.get("listings") or [])
                if include_digital or not l.get("is_digital")]
    prices = [l["price"] for l in listings
              if isinstance(l.get("price"), (int, float))]

    total = miner_result.get("total_results")
    n = len(listings)

    avg_price = round(mean(prices), 2) if prices else None
    med_price = round(median(prices), 2) if prices else None

    lo, hi = price_band
    in_band = sum(1 for p in prices if lo <= p <= hi)
    band_share = round(in_band / len(prices), 3) if prices else 0.0

    bands = {"under_15": 0, "15_30": 0, "30_60": 0, "over_60": 0}
    for p in prices:
        if p < 15:
            bands["under_15"] += 1
        elif p < 30:
            bands["15_30"] += 1
        elif p < 60:
            bands["30_60"] += 1
        else:
            bands["over_60"] += 1

    shops = {l.get("shop_name") for l in listings if l.get("shop_name")}
    shop_count = len(shops)
    # concentration: 1.0 = all top listings from one shop (dominant)
    concentration = round(1 - (shop_count / n), 3) if n else 0.0

    # --- competition score 0..100
    if total:
        count_pressure = min(100.0, max(0.0, (math.log10(total + 1) - 2.0) * 28.0))
    else:
        count_pressure = 50.0
    score = round(
        0.55 * count_pressure
        + 0.25 * (band_share * 100)
        + 0.20 * (concentration * 100),
        1,
    )

    return {
        "keyword": miner_result.get("keyword"),
        "total_results": total,
        "sampled_listings": n,
        "avg_price": avg_price,
        "median_price": med_price,
        "price_bands": bands,
        "band_share_15_60": band_share,
        "distinct_shops": shop_count,
        "shop_concentration": concentration,
        "competition_score": score,  # 0..100, higher = more crowded
    }
