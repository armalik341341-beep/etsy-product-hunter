"""Pipeline: trends -> etsy miner -> competition -> hunter scoring.

run_pipeline(keywords, geo='US', price_band=(15,60), max_cards=24,
             include_digital=False)
returns ranked list of keyword score dicts and persists everything to sqlite.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import db
from trends.trends import get_trending
from etsy_miner import miner
from etsy_miner.miner import search
from competition.analyzer import analyze
from hunter.scorer import score_keyword, rank
from ebay.finding import research_keyword, get_app_id

EBAY_APP_ID = get_app_id()


def _enrich_top_images(scored: dict, miner_res: dict) -> dict:
    """Fill image_url on top listings for the official Etsy API path.

    search_api() leaves image_url=None (one extra call per listing is too
    expensive for a full search page), so we fetch lazily here for only the
    top listings that are actually surfaced. Cached per run.
    """
    if miner_res.get("source") != "etsy_api_v3":
        return scored
    api_key = os.environ.get("ETSY_API_KEY", "").strip()
    if not api_key:
        return scored
    cache: dict = {}

    def _img(lid: str):
        if lid not in cache:
            cache[lid] = miner.fetch_listing_image(lid, api_key)
        return cache[lid]

    for l in scored.get("top_listings", []):
        if not l.get("image_url") and l.get("listing_id"):
            l["image_url"] = _img(str(l["listing_id"]))
    # refresh hero in case enrichment found images
    if not scored.get("hero_image_url"):
        hero = next((l["image_url"] for l in scored["top_listings"]
                     if l.get("image_url")), None)
        if hero:
            scored["hero_image_url"] = hero
    return scored


def run_pipeline(keywords, geo: str = "US", price_band=(15.0, 60.0),
                 max_cards: int = 24, include_digital: bool = False) -> list:
    db.init_db()
    kws = [k.strip() for k in keywords if k and k.strip()]
    trends = get_trending(kws, geo=geo)

    results = []
    for kw in kws:
        kid = db.upsert_keyword(kw)
        ebay_res = research_keyword(EBAY_APP_ID, kw) if EBAY_APP_ID else {
            "error": "eBay key not configured (set EBAY_APP_ID)"}
        miner_res = search(kw, max_cards=max_cards)
        if "error" in miner_res:
            results.append({"keyword": kw, "error": miner_res["error"],
                            "opportunity_score": 0.0,
                            "ebay": ebay_res,
                            "hero_image_url": (ebay_res or {}).get("sample_image_url")})
            continue
        for listing in miner_res["listings"]:
            row_id = db.save_listing(kid, listing)
            listing["row_id"] = row_id
        comp = analyze(miner_res, price_band=price_band,
                       include_digital=include_digital)
        scored = score_keyword(kw, trends.get(kw, {}), miner_res, comp,
                               price_band=price_band, ebay=ebay_res,
                               include_digital=include_digital)
        scored = _enrich_top_images(scored, miner_res)
        results.append(scored)

    ranked = rank(results)
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO runs (keywords_json, result_json, ran_at) VALUES (?, ?, ?)",
        (json.dumps(kws), json.dumps(ranked), db.now()),
    )
    conn.commit()
    conn.close()
    return ranked


def latest_run():
    conn = db.get_conn()
    c = conn.cursor()
    c.execute("SELECT keywords_json, result_json, ran_at FROM runs ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {"keywords": json.loads(row["keywords_json"]),
            "results": json.loads(row["result_json"]),
            "ran_at": row["ran_at"]}


if __name__ == "__main__":
    kws = sys.argv[1:] or ["ceramic mug"]
    print(json.dumps(run_pipeline(kws), indent=2)[:5000])
