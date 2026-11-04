# Etsy Product Hunter

Free, web-based Etsy physical-product hunting system. Professional dark-theme
dashboard with product images, score breakdowns and a price-tracking watchlist.
Deployable free on Render — see **DEPLOY.md**.

| # | Module | What it does |
|---|--------|--------------|
| 1 | `trends/` | Google Trends intake via `pytrends` (free, cached 24h in sqlite) |
| 2 | `etsy_miner/` | Demand miner — **(a)** official Etsy API v3 when `ETSY_API_KEY` is set (legit path), **(b)** polite public-search scraping fallback via `curl_cffi` (Chrome impersonation). Both carry `image_url` per listing (API: listing-images endpoint 570xN rendition, lazily fetched for top listings only; scraper: card `<img>`). |
| 3 | `competition/` | Competition analyzer: listing pressure, price bands, shop concentration → 0–100 score |
| 4 | `hunter/` | Scoring engine: `opportunity = demand / (competition + 1)`; filters digital out, $15–60 price band default; blends eBay real-sales demand 50/50 when available. Emits `hero_image_url` per keyword. |
| 5 | `tracker/` | sqlite watchlist + snapshots (price / favorites deltas over time) |
| 6 | `main.py` + `static/` | FastAPI + professional SPA dashboard (card grid, listing modals, sparkline watchlist) |
| 7 | `ebay/` | **Real sales data** — eBay Finding API `findCompletedItems` (sold listings: count, avg/min/max price, sell-through) + active listing count. Key-only auth, no OAuth, works from cloud IPs. Also exposes a `sample_image_url` (first active item's galleryURL) as a keyword-image fallback. |

## eBay key (free, instant — recommended)

eBay demand data is the system's most honest signal: it uses **completed
SOLD listings** (real sales), not proxies like favorites.

1. Go to https://developer.ebay.com → sign in (free) → "Application Keys"
   (under your name → Application access keys).
2. Create an app (or use the default one) and copy the **App ID (Client ID)**
   — issued instantly, no approval wait.
3. Set it before running the pipeline:

```bash
export EBAY_APP_ID="your_app_id_here"
```

Without the key the module skips gracefully (`"eBay key not configured"`);
everything else keeps working. **What the eBay signal means:**
`total_sold` = how many units actually sold (recent completed items),
`sell_through` = sold ÷ active listings (velocity, capped at 1.0),
`sold_avg_price` = real market price. eBay `demand_score` (60% sold volume,
40% sell-through) makes up **half of the final demand score** — real sales
weigh more than any proxy.

## Setup

```bash
cd ~/workspace/etsy_hunter
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional (legit Etsy path — free developer key from
https://www.etsy.com/developers/your-apps):

```bash
export ETSY_API_KEY="your_key_here"
```

## Run

```bash
uvicorn main:app --host 0.0.0.0 --port 8787
```

Open http://localhost:8787 — paste keywords, Run pipeline, watch the ranked table.

CLI smoke tests:

```bash
python3 -m trends.trends                 # Google Trends on 2 keywords
python3 -m etsy_miner.miner              # scraper on "ceramic mug"
python3 ebay/fixture_test.py             # ebay parser/scorer fixture (no key needed)
python3 pipeline.py "ceramic mug" "wooden candle holder"
```

## Notes / honesty

- Etsy does **not** publish exact sales numbers. Demand is estimated from
  Google Trends interest + listing result counts + favorites — directionally
  right, not a sales guarantee. **eBay's sold-items data IS real sales** and
  is the strongest demand signal in the system when `EBAY_APP_ID` is set.
- The scraper path is polite (2.5–5s between requests, small batches) but
  Etsy rate-limits aggressively; the API key path is the reliable one.
- Digital products (printables, SVG, downloads) are filtered out automatically.
- Secrets only via env vars — no keys in code or the database.
