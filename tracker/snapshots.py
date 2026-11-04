"""Module 5 — watchlist + snapshot tracker.

Snapshots are taken every time a listing is (re-)saved, so history builds
automatically. snapshot_watchlist() re-fetches each watched listing's page
for a fresh price/favorites reading and stores the delta.
"""
import db
from etsy_miner.miner import _fetch_favorites, _fetch
import re


def add_to_watchlist(listing_row_id: int, note: str = "") -> dict:
    conn = db.get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM listings WHERE id = ?", (listing_row_id,))
    if not c.fetchone():
        conn.close()
        return {"error": f"listing row {listing_row_id} not found"}
    c.execute(
        "INSERT OR IGNORE INTO watchlist (listing_row_id, note, added_at) VALUES (?, ?, ?)",
        (listing_row_id, note, db.now()),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "listing_row_id": listing_row_id}


def remove_from_watchlist(listing_row_id: int) -> dict:
    conn = db.get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM watchlist WHERE listing_row_id = ?", (listing_row_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


def get_watchlist() -> list:
    conn = db.get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT w.id AS watch_id, w.note, w.added_at,
               l.id AS row_id, l.listing_id, l.title, l.price, l.currency,
               l.favorites, l.shop_name, l.url, l.image_url
        FROM watchlist w JOIN listings l ON l.id = w.listing_row_id
        ORDER BY w.added_at DESC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    for r in rows:
        r["history"] = history(r["listing_id"])
    return rows


def history(listing_id: str) -> list:
    conn = db.get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT price, favorites, taken_at FROM snapshots WHERE listing_id = ? ORDER BY taken_at",
        (listing_id,),
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def _read_listing_page(listing_id: str):
    """Re-read a listing page: current price + favorites. Best effort."""
    try:
        r = _fetch(f"https://www.etsy.com/listing/{listing_id}")
        if r.status_code != 200:
            return None, None
        m = re.search(r'"num_favorers"\s*:\s*(\d+)', r.text)
        favs = int(m.group(1)) if m else None
        price = None
        m = re.search(r'"price"\s*:\s*\{\s*"amount"\s*:\s*(\d+)', r.text)
        if m:
            # amount is in minor units; divisor usually 100
            d = re.search(r'"divisor"\s*:\s*(\d+)', r.text)
            divisor = int(d.group(1)) if d else 100
            price = int(m.group(1)) / divisor
        return price, favs
    except Exception:
        return None, None


def snapshot_watchlist() -> dict:
    """Re-check every watched listing; store snapshot; return deltas."""
    items = get_watchlist()
    out = []
    for it in items:
        price, favs = _read_listing_page(it["listing_id"])
        old_price, old_favs = it.get("price"), it.get("favorites")
        conn = db.get_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO snapshots (listing_id, price, favorites, taken_at) VALUES (?, ?, ?, ?)",
            (it["listing_id"],
             price if price is not None else old_price,
             favs if favs is not None else old_favs, db.now()),
        )
        c.execute(
            "UPDATE listings SET price = COALESCE(?, price), favorites = COALESCE(?, favorites) WHERE id = ?",
            (price, favs, it["row_id"]),
        )
        conn.commit()
        conn.close()
        out.append({
            "listing_id": it["listing_id"],
            "title": it["title"],
            "price": price if price is not None else old_price,
            "price_delta": (round(price - old_price, 2)
                            if price is not None and old_price else None),
            "favorites": favs if favs is not None else old_favs,
            "favorites_delta": ((favs - old_favs)
                                if favs is not None and old_favs is not None else None),
        })
    return {"snapshotted": len(out), "items": out}
