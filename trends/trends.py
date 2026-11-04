"""Module 1 — Google Trends intake (pytrends, free, legal, no scraping).

get_trending(keywords, geo='US', timeframe='today 3-m') returns per keyword:
  - avg_interest: mean of interest-over-time (0-100 scale)
  - rising_queries: list of related queries marked "Rising" (may be empty)
  - top_queries: top related queries
Results are cached in sqlite (trends_cache) for 24h to stay well under limits.
"""
import time

from pytrends.request import TrendReq

import db

_TIME_SLEEP = 2.0  # polite pause between TrendReq payload builds


def _empty_result(keyword: str) -> dict:
    return {
        "keyword": keyword,
        "avg_interest": 0.0,
        "peak_interest": 0,
        "rising_queries": [],
        "top_queries": [],
        "error": None,
    }


def get_trending(keywords, geo: str = "US", timeframe: str = "today 3-m",
                 use_cache: bool = True) -> dict:
    """Fetch Google Trends data for keywords. Returns {keyword: result_dict}."""
    results = {}
    to_fetch = []
    for kw in keywords:
        kw = kw.strip()
        if not kw:
            continue
        cached = db.get_trends_cache(kw, geo, timeframe) if use_cache else None
        if cached is not None:
            cached["from_cache"] = True
            results[kw] = cached
        else:
            to_fetch.append(kw)

    if not to_fetch:
        return results

    # pytrends compares up to 5 keywords per payload; do them in small batches.
    for i in range(0, len(to_fetch), 5):
        batch = to_fetch[i:i + 5]
        try:
            py = TrendReq(hl="en-US", tz=360, retries=2, backoff_factor=0.5)
            py.build_payload(batch, cat=0, timeframe=timeframe, geo=geo, gprop="")
            iot = py.interest_over_time()
            related = py.related_queries()
        except Exception as e:  # network/429 etc — report, don't crash
            for kw in batch:
                r = _empty_result(kw)
                r["error"] = f"{type(e).__name__}: {e}"
                results[kw] = r
            time.sleep(_TIME_SLEEP)
            continue

        for kw in batch:
            r = _empty_result(kw)
            try:
                if not iot.empty and kw in iot.columns:
                    series = iot[kw].dropna()
                    if len(series):
                        r["avg_interest"] = round(float(series.mean()), 2)
                        r["peak_interest"] = int(series.max())
                rq = related.get(kw, {}) if isinstance(related, dict) else {}
                if rq:
                    rising = rq.get("rising")
                    if rising is not None and not rising.empty:
                        r["rising_queries"] = rising["query"].head(8).tolist()
                    top = rq.get("top")
                    if top is not None and not top.empty:
                        r["top_queries"] = top["query"].head(8).tolist()
            except Exception as e:
                r["error"] = f"{type(e).__name__}: {e}"
            r["from_cache"] = False
            results[kw] = r
            db.set_trends_cache(kw, geo, timeframe, r)
        time.sleep(_TIME_SLEEP)

    return results


if __name__ == "__main__":
    import json
    db.init_db()
    out = get_trending(["ceramic mug", "candle holder"], geo="US")
    print(json.dumps(out, indent=2)[:3000])
