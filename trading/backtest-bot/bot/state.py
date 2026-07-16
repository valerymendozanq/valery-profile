"""SQLite state so restarts never double-enter. Tracks the open position and a log
of every action the bot has taken."""
from __future__ import annotations

import os
import sqlite3
from typing import Optional


class State:
    def __init__(self, db_path: str) -> None:
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init()

    def _init(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS position (
                symbol TEXT PRIMARY KEY,
                is_open INTEGER NOT NULL DEFAULT 0,
                entry_price REAL,
                quantity INTEGER,
                entry_time INTEGER
            );
            CREATE TABLE IF NOT EXISTS trade_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                price REAL,
                quantity INTEGER,
                mode TEXT,
                reason TEXT
            );
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )
        self.conn.commit()

    # --- position ---
    def get_position(self, symbol: str) -> Optional[sqlite3.Row]:
        cur = self.conn.execute(
            "SELECT * FROM position WHERE symbol=? AND is_open=1", (symbol,)
        )
        return cur.fetchone()

    def open_position(self, symbol: str, price: float, qty: int, ts: int) -> None:
        self.conn.execute(
            "INSERT INTO position(symbol,is_open,entry_price,quantity,entry_time) "
            "VALUES(?,?,?,?,?) ON CONFLICT(symbol) DO UPDATE SET "
            "is_open=1, entry_price=excluded.entry_price, quantity=excluded.quantity, "
            "entry_time=excluded.entry_time",
            (symbol, 1, price, qty, ts),
        )
        self.conn.commit()

    def close_position(self, symbol: str) -> None:
        self.conn.execute("UPDATE position SET is_open=0 WHERE symbol=?", (symbol,))
        self.conn.commit()

    # --- log ---
    def log_action(self, ts, symbol, action, price, qty, mode, reason) -> None:
        self.conn.execute(
            "INSERT INTO trade_log(ts,symbol,action,price,quantity,mode,reason) "
            "VALUES(?,?,?,?,?,?,?)",
            (ts, symbol, action, price, qty, mode, reason),
        )
        self.conn.commit()

    def last_processed_time(self, symbol: str) -> Optional[int]:
        cur = self.conn.execute(
            "SELECT value FROM meta WHERE key=?", (f"last_ts::{symbol}",)
        )
        row = cur.fetchone()
        return int(row["value"]) if row else None

    def set_last_processed_time(self, symbol: str, ts: int) -> None:
        self.conn.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (f"last_ts::{symbol}", str(ts)),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
