# Deploying Etsy Product Hunter on Render (free)

No coding needed — just clicks. You will do the Render signup yourself.

## What you need before you start

1. A **GitHub account** (free).
2. This project pushed to a GitHub repo (see "Put the code on GitHub" below).
3. Your **Etsy API key** (optional — paste as `keystring:shared_secret`) and/or
   **eBay App ID** (optional). The app works without them but shows
   degraded data sources (scraper fallback instead of the Etsy API).

## 1. Put the code on GitHub

On your computer, inside the `etsy_hunter` folder:

```bash
git init
git add .
git commit -m "Etsy Product Hunter"
```

Then on github.com: **New repository** → name it `etsy-product-hunter` →
**Create**, and follow the "push an existing repository" commands it shows.

## 2. Create the free web service on Render

1. Go to **render.com** and sign up (the free tier is enough).
2. Dashboard → **New +** → **Web Service**.
3. **Connect** your GitHub account and select the `etsy-product-hunter` repo.
4. Render reads `render.yaml` automatically. Check the settings look like this:
   - **Runtime:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
   - **Plan:** Free
5. Under **Environment Variables**, add (optional, can be added later too):
   - `ETSY_API_KEY` = your key as `keystring:shared_secret`
   - `EBAY_APP_ID` = your eBay Production App ID
6. Click **Create Web Service**. First deploy takes ~3–5 minutes.
7. Open the URL Render gives you (like
   `https://etsy-product-hunter-xxxx.onrender.com`) — the dashboard loads.

## 3. Things to know about the free tier

- **Sleep:** free services sleep after ~15 minutes of no traffic. The first
  visit after sleep takes 30–60 seconds to wake up. This is normal.
- **Ephemeral disk:** the sqlite database resets when Render redeploys or
  restarts the service. Runs and watchlists are for the current session —
  export anything important. (A persistent disk is a paid feature.)
- **750 hours/month** free — one always-on service fits comfortably.

## 4. Updating later

Push new commits to GitHub → Render redeploys automatically.

## Local test

```bash
cd etsy_hunter && source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8787
# open http://localhost:8787

# UI fixture test (no keys, no network for data):
HUNTER_FIXTURE=1 uvicorn main:app --host 0.0.0.0 --port 8787
# then POST {"keywords": "fixture"} to /api/run
```
