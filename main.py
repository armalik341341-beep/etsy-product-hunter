"""Etsy Product Hunter — FastAPI dashboard.

Run locally:  cd ~/workspace/etsy_hunter && source .venv/bin/activate && \
              uvicorn main:app --host 0.0.0.0 --port 8787
Then open http://localhost:8787

Deploy: see DEPLOY.md (Render free tier).

API surface (backward compatible — fields only ever added, never
renamed/removed):
  GET  /api/health          -> {"ok": true, "service": "etsy-hunter"}
  GET  /api/status          -> source availability (etsy api / ebay / fixture)
  POST /api/run             -> {keywords, geo, price_lo, price_hi,
                                max_cards, include_digital}
  GET  /api/run/status      -> job state
  GET  /api/results         -> latest ranked run (keyword dicts carry
                                hero_image_url; top_listings carry image_url)
  GET/POST/DELETE /api/watchlist, POST /api/snapshot
  GET  /                    -> the dashboard SPA (static/app.html)
"""
import json
import os
import threading
import time
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))

import db
from pipeline import run_pipeline, latest_run
from tracker.snapshots import (add_to_watchlist, remove_from_watchlist,
                               get_watchlist, snapshot_watchlist)

db.init_db()

app = FastAPI(title="Etsy Product Hunter")
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")),
          name="static")

JOB = {"status": "idle", "detail": "", "finished_at": None}


class RunRequest(BaseModel):
    keywords: str  # comma separated
    geo: str = "US"
    price_lo: float = 15.0
    price_hi: float = 60.0
    max_cards: int = 24
    include_digital: bool = False  # additive; default preserves old behavior


class WatchAdd(BaseModel):
    row_id: int
    note: str = ""


def _fixture_ranked(kws):
    """Local-test fixture path (HUNTER_FIXTURE=1, keywords == 'fixture').

    Seeds the local DB and returns ranked results with working image URLs.
    Never active on Render (env var not set there).
    """
    import fixtures
    ranked = fixtures.fixture_run()
    conn = db.get_conn()
    conn.execute(
        "INSERT INTO runs (keywords_json, result_json, ran_at) VALUES (?, ?, ?)",
        (json.dumps(kws), json.dumps(ranked), db.now()),
    )
    conn.commit()
    conn.close()
    return ranked


def _job_runner(req: RunRequest):
    JOB["status"] = "running"
    JOB["detail"] = "fetching trends + etsy data (this takes a few minutes)..."
    try:
        kws = [k.strip() for k in req.keywords.split(",")]
        if os.environ.get("HUNTER_FIXTURE") == "1" and kws == ["fixture"]:
            res = _fixture_ranked(kws)
        else:
            res = run_pipeline(kws, geo=req.geo,
                               price_band=(req.price_lo, req.price_hi),
                               max_cards=req.max_cards,
                               include_digital=req.include_digital)
        JOB["status"] = "done"
        JOB["detail"] = f"ranked {len(res)} keywords"
    except Exception as e:
        JOB["status"] = "error"
        JOB["detail"] = f"{type(e).__name__}: {e}"
    JOB["finished_at"] = int(time.time())


@app.get("/api/health")
def health():
    return {"ok": True, "service": "etsy-hunter"}


@app.get("/api/status")
def status():
    """Which data sources are live right now (additive helper for the UI)."""
    return {
        "etsy_api": bool(os.environ.get("ETSY_API_KEY", "").strip()),
        "ebay": bool(os.environ.get("EBAY_APP_ID", "").strip()),
        "fixture": os.environ.get("HUNTER_FIXTURE") == "1",
        "service": "etsy-hunter",
    }


@app.post("/api/run")
def start_run(req: RunRequest):
    if JOB["status"] == "running":
        return {"error": "a run is already in progress"}
    t = threading.Thread(target=_job_runner, args=(req,), daemon=True)
    t.start()
    return {"ok": True, "status": "started"}


@app.get("/api/run/status")
def run_status():
    return JOB


@app.get("/api/results")
def results():
    lr = latest_run()
    return lr or {"results": [], "keywords": [], "ran_at": None}


@app.post("/api/watchlist")
def watch_add(body: WatchAdd):
    return add_to_watchlist(body.row_id, body.note)


@app.delete("/api/watchlist/{row_id}")
def watch_del(row_id: int):
    return remove_from_watchlist(row_id)


@app.get("/api/watchlist")
def watch_list():
    return {"items": get_watchlist()}


@app.post("/api/snapshot")
def snapshot():
    return snapshot_watchlist()


@app.get("/", response_class=HTMLResponse)
def index():
    page = Path(__file__).resolve().parent / "static" / "app.html"
    if page.exists():
        return FileResponse(page)
    return HTMLResponse("<h1>Etsy Product Hunter</h1><p>static/app.html missing</p>",
                        status_code=500)
