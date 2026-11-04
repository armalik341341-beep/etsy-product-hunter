"""Fixture data for local UI/API testing (no network, no API keys).

Used only when the HUNTER_FIXTURE=1 env var is set and the run request
carries keywords == "fixture". Never used in production / on Render.

fixture_run() seeds the local sqlite DB (keywords, listings with image_url,
watchlist entries + snapshot history) and returns a ranked list shaped
exactly like hunter.scorer.score_keyword() output, so /api/results,
/api/watchlist and the whole frontend can be exercised end-to-end.

Images: served locally from static/img/ (bundled with the repo) so the
fixture demo and screenshots work fully offline. Live paths (Etsy API,
eBay galleryURL, scraper cards) flow their own source URLs untouched.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import db
from tracker.snapshots import add_to_watchlist

IMG = "/static/img/{}.jpg"

_FIXTURES = [
    {
        "keyword": "ceramic mug",
        "opportunity_score": 1.42,
        "demand_score": 78.4,
        "competition_score": 54.2,
        "trend_avg_interest": 72,
        "trend_rising": ["ceramic mug handmade", "stoneware coffee mug",
                         "rustic pottery mug"],
        "total_results": 48210,
        "avg_price": 28.9,
        "in_price_band": 6,
        "ebay_total_sold": 1250,
        "ebay_sell_through": 0.298,
        "ebay_avg_sold_price": 26.06,
        "ebay_demand_score": 58.4,
        "listings": [
            ("1001", "Handmade Stoneware Ceramic Mug — Rustic Coffee Cup",
             24.99, 412, "ClayAndCo", "mug1"),
            ("1002", "Speckled Pottery Mug, Large 16oz — Dishwasher Safe",
             29.50, 388, "KilnHouse", "mug2"),
            ("1003", "Minimalist White Ceramic Mug Set of 2 — Gift Box",
             34.00, 256, "NordicClay", "mug3"),
            ("1004", "Blue Reactive Glaze Stoneware Mug — Hand Thrown",
             27.95, 301, "ClayAndCo", "mug4"),
            ("1005", "Personalized Initial Ceramic Mug — Wedding Gift",
             22.00, 189, "GiftedHands", "mug5"),
        ],
    },
    {
        "keyword": "macrame wall hanging",
        "opportunity_score": 1.18,
        "demand_score": 69.1,
        "competition_score": 57.6,
        "trend_avg_interest": 58,
        "trend_rising": ["macrame wall hanging large", "boho wall decor"],
        "total_results": 31200,
        "avg_price": 42.5,
        "in_price_band": 5,
        "ebay_total_sold": 640,
        "ebay_sell_through": 0.21,
        "ebay_avg_sold_price": 38.4,
        "ebay_demand_score": 49.2,
        "listings": [
            ("2001", "Large Boho Macrame Wall Hanging — Cotton, 36 inch",
             49.99, 520, "BohoNest", "mac1"),
            ("2002", "Macrame Wall Decor with Wooden Dowel — Handmade",
             36.50, 274, "KnotAndLoop", "mac2"),
            ("2003", "Mini Macrame Wall Hanging Set of 3 — Nursery Decor",
             28.00, 198, "BohoNest", "mac3"),
        ],
    },
    {
        "keyword": "wooden candle holder",
        "opportunity_score": 0.94,
        "demand_score": 61.3,
        "competition_score": 64.1,
        "trend_avg_interest": 51,
        "trend_rising": ["wooden candle holder set"],
        "total_results": 27800,
        "avg_price": 24.7,
        "in_price_band": 4,
        "ebay_total_sold": 430,
        "ebay_sell_through": 0.18,
        "ebay_avg_sold_price": 22.9,
        "ebay_demand_score": 44.7,
        "listings": [
            ("3001", "Set of 3 Acacia Wood Candle Holders — Pillar Candles",
             32.99, 233, "TimberCraft", "cand1"),
            ("3002", "Rustic Log Candle Holder — Natural Wood, Handmade",
             19.99, 176, "ForestFinds", "cand2"),
        ],
    },
]


def fixture_run() -> list:
    """Seed DB + return ranked fixture results (no network)."""
    db.init_db()
    ranked = []
    seeded_rows = []
    for fx in _FIXTURES:
        kid = db.upsert_keyword("fixture: " + fx["keyword"])
        top = []
        for lid, title, price, favs, shop, seed in fx["listings"]:
            data = {
                "listing_id": lid,
                "title": title,
                "price": price,
                "currency": "USD",
                "favorites": favs,
                "shop_name": shop,
                "url": f"https://www.etsy.com/listing/{lid}",
                "image_url": IMG.format(seed),
                "is_digital": False,
            }
            row_id = db.save_listing(kid, data)
            data["row_id"] = row_id
            seeded_rows.append((lid, data))
            top.append({k: data.get(k) for k in (
                "listing_id", "title", "price", "currency",
                "favorites", "shop_name", "url", "image_url", "row_id")})
        ranked.append({
            "keyword": fx["keyword"],
            "opportunity_score": fx["opportunity_score"],
            "demand_score": fx["demand_score"],
            "competition_score": fx["competition_score"],
            "trend_avg_interest": fx["trend_avg_interest"],
            "trend_rising": fx["trend_rising"],
            "total_results": fx["total_results"],
            "avg_price": fx["avg_price"],
            "physical_sampled": len(fx["listings"]),
            "in_price_band": fx["in_price_band"],
            "ebay_total_sold": fx["ebay_total_sold"],
            "ebay_sell_through": fx["ebay_sell_through"],
            "ebay_avg_sold_price": fx["ebay_avg_sold_price"],
            "ebay_demand_score": fx["ebay_demand_score"],
            "ebay_error": None,
            "top_listings": top,
            "hero_image_url": top[0]["image_url"],
            "source": "fixture",
        })

    # seed watchlist with 2 items + snapshot history for the sparkline UI
    import time
    conn = db.get_conn()
    c = conn.cursor()
    for lid, data in [seeded_rows[0], seeded_rows[6]]:
        row_id = data["row_id"]
        c.execute(
            "INSERT OR IGNORE INTO watchlist (listing_row_id, note, added_at) VALUES (?, ?, ?)",
            (row_id, "fixture watch", int(time.time())))
        base_price, base_favs = data["price"], data["favorites"]
        for i, (dp, df) in enumerate([(0.0, 0), (1.5, 12), (-0.5, 28)]):
            c.execute(
                "INSERT INTO snapshots (listing_id, price, favorites, taken_at) VALUES (?, ?, ?, ?)",
                (lid, round(base_price + dp, 2), base_favs + df,
                 int(time.time()) - (3 - i) * 86400))
    conn.commit()
    conn.close()

    return sorted(ranked, key=lambda r: r["opportunity_score"], reverse=True)


if __name__ == "__main__":
    import json
    print(json.dumps(fixture_run(), indent=2)[:2000])
