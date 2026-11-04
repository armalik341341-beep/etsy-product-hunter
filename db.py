"""SQLite storage for the Etsy hunter system."""
import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "etsy_hunter.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT UNIQUE NOT NULL,
            added_at INTEGER NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id TEXT NOT NULL,
            keyword_id INTEGER,
            title TEXT,
            price REAL,
            currency TEXT,
            favorites INTEGER,
            shop_name TEXT,
            url TEXT,
            is_digital INTEGER DEFAULT 0,
            first_seen INTEGER NOT NULL,
            UNIQUE(listing_id, keyword_id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id TEXT NOT NULL,
            price REAL,
            favorites INTEGER,
            taken_at INTEGER NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_row_id INTEGER NOT NULL UNIQUE,
            note TEXT DEFAULT '',
            added_at INTEGER NOT NULL
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS trends_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            geo TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            fetched_at INTEGER NOT NULL,
            UNIQUE(keyword, geo, timeframe)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keywords_json TEXT NOT NULL,
            result_json TEXT NOT NULL,
            ran_at INTEGER NOT NULL
        )
    """)
    conn.commit()
    # --- additive migrations for older DBs ---
    for stmt in (
        "ALTER TABLE listings ADD COLUMN image_url TEXT",
    ):
        try:
            c.execute(stmt)
        except sqlite3.OperationalError:
            pass  # column already exists
    conn.commit()
    conn.close()


def now() -> int:
    return int(time.time())


def upsert_keyword(keyword: str) -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT OR IGNORE INTO keywords (keyword, added_at) VALUES (?, ?)",
        (keyword, now()),
    )
    c.execute("SELECT id FROM keywords WHERE keyword = ?", (keyword,))
    kid = c.fetchone()["id"]
    conn.commit()
    conn.close()
    return kid


def save_listing(keyword_id: int, data: dict) -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """INSERT INTO listings
           (listing_id, keyword_id, title, price, currency, favorites,
            shop_name, url, image_url, is_digital, first_seen)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(listing_id, keyword_id) DO UPDATE SET
             title=excluded.title, price=excluded.price,
             currency=excluded.currency, favorites=excluded.favorites,
             shop_name=excluded.shop_name, url=excluded.url,
             image_url=COALESCE(excluded.image_url, image_url),
             is_digital=excluded.is_digital""",
        (
            data.get("listing_id"),
            keyword_id,
            data.get("title"),
            data.get("price"),
            data.get("currency"),
            data.get("favorites"),
            data.get("shop_name"),
            data.get("url"),
            data.get("image_url"),
            1 if data.get("is_digital") else 0,
            now(),
        ),
    )
    c.execute(
        "SELECT id FROM listings WHERE listing_id = ? AND keyword_id = ?",
        (data.get("listing_id"), keyword_id),
    )
    row_id = c.fetchone()["id"]
    c.execute(
        "INSERT INTO snapshots (listing_id, price, favorites, taken_at) VALUES (?, ?, ?, ?)",
        (data.get("listing_id"), data.get("price"), data.get("favorites"), now()),
    )
    conn.commit()
    conn.close()
    return row_id


def get_trends_cache(keyword: str, geo: str, timeframe: str, max_age_h: float = 24):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT payload_json, fetched_at FROM trends_cache WHERE keyword=? AND geo=? AND timeframe=?",
        (keyword, geo, timeframe),
    )
    row = c.fetchone()
    conn.close()
    if row and (now() - row["fetched_at"]) < max_age_h * 3600:
        return json.loads(row["payload_json"])
    return None


def set_trends_cache(keyword: str, geo: str, timeframe: str, payload: dict) -> None:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """INSERT INTO trends_cache (keyword, geo, timeframe, payload_json, fetched_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(keyword, geo, timeframe) DO UPDATE SET
             payload_json=excluded.payload_json, fetched_at=excluded.fetched_at""",
        (keyword, geo, timeframe, json.dumps(payload), now()),
    )
    conn.commit()
    conn.close()
