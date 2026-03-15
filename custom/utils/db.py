"""Database initialization and helpers.

See docs/sub-specs/SS-01.md §14
"""

import logging
import os
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)

# Valid tables for insert_row() — prevents SQL injection
_VALID_TABLES: set[str] = {
    "spot_price",
    "spot_cvd",
    "spot_orderbook",
    "spot_whale_trades",
    "spot_technicals",
    "futures_snapshot",
    "futures_liquidations",
    "futures_oi_price",
    "options_oi",
    "gex_data",
    "options_large_trades",
    "daily_snapshot",
    "signals",
    "trades",
    "macro_events",
    "ai_analysis_log",
    "level_outcomes",
    "subscribers",
    "news_rss_seen",
}

# Valid columns for ORDER BY in get_latest() — prevents SQL injection
_VALID_ORDER_COLS: set[str] = {"timestamp", "date", "id", "entry_timestamp", "exit_timestamp"}

_SCHEMA: str = """
CREATE TABLE IF NOT EXISTS spot_price (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL,
    volume REAL, quote_volume REAL, num_trades INTEGER
);

CREATE TABLE IF NOT EXISTS spot_cvd (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    cvd_1h REAL, cvd_4h REAL, cvd_24h REAL,
    buy_volume REAL, sell_volume REAL
);

CREATE TABLE IF NOT EXISTS spot_orderbook (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    bid_depth_usd REAL, ask_depth_usd REAL,
    imbalance REAL, spread_bps REAL
);

CREATE TABLE IF NOT EXISTS spot_whale_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    side TEXT, price REAL, quantity REAL, value_usd REAL
);

CREATE TABLE IF NOT EXISTS spot_technicals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    rsi_14 REAL, ema_21 REAL, ema_55 REAL, ema_200 REAL,
    vwap REAL, bb_upper REAL, bb_lower REAL, bb_width REAL,
    adx_14 REAL, volume_sma_20 REAL, volume_ratio REAL
);

CREATE TABLE IF NOT EXISTS futures_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    funding_binance REAL, funding_bybit REAL, funding_okx REAL,
    funding_weighted_avg REAL,
    oi_binance_usd REAL, oi_bybit_usd REAL, oi_okx_usd REAL,
    oi_total_usd REAL,
    oi_change_1h_pct REAL, oi_change_4h_pct REAL, oi_change_24h_pct REAL,
    futures_price REAL, spot_price REAL,
    basis_pct REAL, annualized_premium_pct REAL,
    top_trader_ls_ratio REAL, account_ls_ratio REAL, global_ls_ratio REAL,
    taker_buy_sell_ratio REAL,
    taker_buy_volume REAL, taker_sell_volume REAL
);

CREATE TABLE IF NOT EXISTS futures_liquidations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    long_liq_usd REAL, short_liq_usd REAL,
    total_liq_usd REAL, liq_ratio REAL
);

CREATE TABLE IF NOT EXISTS futures_oi_price (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    price REAL, total_oi REAL,
    oi_change_pct REAL, price_change_pct REAL,
    regime TEXT
);

CREATE TABLE IF NOT EXISTS options_oi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    expiry TEXT NOT NULL, strike REAL NOT NULL,
    call_oi REAL, put_oi REAL,
    call_iv REAL, put_iv REAL,
    call_volume REAL, put_volume REAL
);

CREATE TABLE IF NOT EXISTS gex_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    strike REAL NOT NULL,
    call_gex REAL, put_gex REAL, net_gex REAL,
    gamma_flip_price REAL
);

CREATE TABLE IF NOT EXISTS options_large_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    instrument TEXT, direction TEXT,
    amount REAL, price REAL, iv REAL, value_usd REAL
);

CREATE TABLE IF NOT EXISTS daily_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL UNIQUE,
    btc_price REAL, fear_greed INTEGER, dvol REAL,
    put_call_ratio_oi REAL, put_call_ratio_volume REAL,
    regime TEXT, adx REAL, bb_width_percentile REAL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    final_score REAL, bias TEXT, strength TEXT, confidence TEXT,
    regime TEXT, event_risk REAL, consensus TEXT,
    spot_flow REAL, leverage_pos REAL, options_struct REAL, mean_reversion REAL,
    weights_json TEXT,
    btc_price_at_signal REAL,
    btc_price_4h_later REAL, btc_price_12h_later REAL,
    btc_price_24h_later REAL, btc_price_48h_later REAL,
    correct INTEGER,
    magnitude_24h_pct REAL
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    signal_id INTEGER REFERENCES signals(id),
    entry_timestamp TEXT, exit_timestamp TEXT,
    direction TEXT, entry_price REAL, exit_price REAL,
    stop_loss REAL, tp1 REAL, tp2 REAL, tp3 REAL,
    position_size_usd REAL, risk_pct REAL,
    pnl_usd REAL, pnl_pct REAL, r_multiple REAL,
    exit_reason TEXT
);

CREATE TABLE IF NOT EXISTS macro_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL, time_utc TEXT NOT NULL,
    event TEXT NOT NULL, tier INTEGER NOT NULL,
    forecast REAL, actual REAL, previous REAL,
    surprise REAL, impact TEXT,
    source TEXT DEFAULT 'static'
);

CREATE TABLE IF NOT EXISTS ai_analysis_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    prompt_type TEXT NOT NULL,
    prompt_tokens INTEGER,
    response_tokens INTEGER,
    response_text TEXT,
    ai_bias TEXT,
    ai_confidence TEXT,
    ai_key_factor TEXT,
    ai_recommended_action TEXT,
    btc_price_at_analysis REAL,
    btc_price_24h_later REAL,
    ai_direction_correct INTEGER,
    quant_score_at_time REAL,
    quant_bias_at_time TEXT,
    ai_agreed_with_quant INTEGER,
    agreement_correct INTEGER,
    disagreement_who_right TEXT
);

CREATE TABLE IF NOT EXISTS level_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    level_price REAL NOT NULL,
    level_type TEXT NOT NULL,
    strength INTEGER NOT NULL,
    components TEXT,
    price_reached_zone INTEGER,
    zone_held INTEGER,
    price_at_test REAL,
    bounce_magnitude_pct REAL,
    break_magnitude_pct REAL
);

CREATE TABLE IF NOT EXISTS subscribers (
    chat_id TEXT UNIQUE NOT NULL,
    added_by TEXT NOT NULL,
    added_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS news_rss_seen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guid TEXT UNIQUE NOT NULL,
    title TEXT,
    seen_at TEXT NOT NULL
);
"""


def _migrate(conn: sqlite3.Connection) -> None:
    """Run idempotent schema migrations for existing databases.

    See docs/sub-specs/SS-24.md §5
    """
    # Add 'source' column to macro_events (for pre-SS-24 databases)
    try:
        conn.execute("ALTER TABLE macro_events ADD COLUMN source TEXT DEFAULT 'static'")
        conn.commit()
        logger.info("Migration: added 'source' column to macro_events")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Add 'tp1_hit' column to trades (for trade lifecycle tracking)
    try:
        conn.execute("ALTER TABLE trades ADD COLUMN tp1_hit INTEGER DEFAULT 0")
        conn.commit()
        logger.info("Migration: added 'tp1_hit' column to trades")
    except sqlite3.OperationalError:
        pass  # Column already exists


def init_db(db_path: str = "data/signals.db") -> None:
    """Create all tables. Idempotent via CREATE TABLE IF NOT EXISTS.

    See docs/sub-specs/SS-01.md §14
    """
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(_SCHEMA)
        _migrate(conn)
        conn.commit()
        logger.info("Database initialized at %s", db_path)
    finally:
        conn.close()


def get_db(db_path: str = "data/signals.db") -> sqlite3.Connection:
    """Return a connection with row_factory=sqlite3.Row.

    See docs/sub-specs/SS-01.md §14
    """
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def insert_row(db_path: str, table: str, data: dict[str, Any]) -> int:
    """Insert a row into table from dict. Returns the new row ID.

    See docs/sub-specs/SS-01.md §14

    Args:
        db_path: Path to SQLite database file.
        table: Table name (must be in _VALID_TABLES).
        data: Column name → value mapping.

    Returns:
        The rowid of the inserted row.

    Raises:
        ValueError: If table name is not in the allowed set.
    """
    if table not in _VALID_TABLES:
        raise ValueError(f"Invalid table name: {table!r}")
    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
    conn = get_db(db_path)
    try:
        cursor = conn.execute(sql, tuple(data.values()))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_row(
    db_path: str, table: str, data: dict[str, Any], where: str, params: tuple,
) -> int:
    """Update rows in table. Returns number of rows affected.

    Args:
        db_path: Path to SQLite database file.
        table: Table name (must be in _VALID_TABLES).
        data: Column name → value mapping for SET clause.
        where: WHERE clause (e.g. "id = ?").
        params: Parameters for the WHERE clause.

    Returns:
        Number of rows updated.
    """
    if table not in _VALID_TABLES:
        raise ValueError(f"Invalid table name: {table!r}")
    set_clause = ", ".join(f"{col} = ?" for col in data.keys())
    sql = f"UPDATE {table} SET {set_clause} WHERE {where}"
    conn = get_db(db_path)
    try:
        cursor = conn.execute(sql, (*data.values(), *params))
        conn.commit()
        return cursor.rowcount
    finally:
        conn.close()


def query(db_path: str, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """Execute a SELECT query and return results as list of dicts.

    See docs/sub-specs/SS-01.md §14
    """
    conn = get_db(db_path)
    try:
        cursor = conn.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_latest(
    db_path: str,
    table: str,
    n: int = 10,
    order_col: str = "timestamp",
) -> list[dict[str, Any]]:
    """Return N most recent rows from table, ordered by order_col DESC.

    See docs/sub-specs/SS-01.md §14

    Raises:
        ValueError: If table or order_col is not in the allowed set.
    """
    if table not in _VALID_TABLES:
        raise ValueError(f"Invalid table name: {table!r}")
    if order_col not in _VALID_ORDER_COLS:
        raise ValueError(f"Invalid order column: {order_col!r}")
    sql = f"SELECT * FROM {table} ORDER BY {order_col} DESC LIMIT ?"
    return query(db_path, sql, (n,))


def get_subscribers(db_path: str) -> list[str]:
    """Return list of active subscriber chat_id strings.

    See docs/sub-specs/SS-18.md §12

    Args:
        db_path: Path to SQLite database.

    Returns:
        List of chat_id strings for active subscribers.
    """
    rows = query(db_path, "SELECT chat_id FROM subscribers WHERE active = 1")
    return [row["chat_id"] for row in rows]


def upsert_subscriber(db_path: str, chat_id: str, added_by: str) -> bool:
    """Add or reactivate a subscriber. Returns True if new or reactivated.

    See docs/sub-specs/SS-18.md §12

    Args:
        db_path: Path to SQLite database.
        chat_id: Telegram chat ID string.
        added_by: Who added this subscriber.

    Returns:
        True if subscriber was newly added or reactivated, False if already active.
    """
    from datetime import datetime, timezone

    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            "SELECT active FROM subscribers WHERE chat_id = ?", (chat_id,)
        )
        row = cursor.fetchone()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        if row is None:
            conn.execute(
                "INSERT INTO subscribers (chat_id, added_by, added_at, active) VALUES (?, ?, ?, 1)",
                (chat_id, added_by, now),
            )
            conn.commit()
            return True
        elif row["active"] == 0:
            conn.execute(
                "UPDATE subscribers SET active = 1, added_by = ?, added_at = ? WHERE chat_id = ?",
                (added_by, now, chat_id),
            )
            conn.commit()
            return True
        else:
            return False
    finally:
        conn.close()


def remove_subscriber(db_path: str, chat_id: str) -> bool:
    """Deactivate a subscriber. Returns True if was active.

    See docs/sub-specs/SS-18.md §12

    Args:
        db_path: Path to SQLite database.
        chat_id: Telegram chat ID string.

    Returns:
        True if subscriber was active and is now deactivated, False otherwise.
    """
    conn = get_db(db_path)
    try:
        cursor = conn.execute(
            "SELECT active FROM subscribers WHERE chat_id = ?", (chat_id,)
        )
        row = cursor.fetchone()
        if row is None or row["active"] == 0:
            return False
        conn.execute(
            "UPDATE subscribers SET active = 0 WHERE chat_id = ?", (chat_id,)
        )
        conn.commit()
        return True
    finally:
        conn.close()
