"""Configuration for the MNQ EMA 9/21 bot. Env-overridable. No secrets in source."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _get(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


def _getf(name: str, default: float) -> float:
    try:
        return float(_get(name, str(default)))
    except ValueError:
        return default


def _geti(name: str, default: int) -> int:
    try:
        return int(float(_get(name, str(default))))
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    # Market
    symbol: str = _get("SYMBOL", "MNQ=F")          # Micro E-mini Nasdaq-100 futures
    interval: str = _get("INTERVAL", "1d")          # daily only
    # Strategy
    fast_period: int = _geti("FAST_PERIOD", 9)
    slow_period: int = _geti("SLOW_PERIOD", 21)
    # Sizing (MNQ contracts; $2 per index point)
    quantity: int = _geti("QUANTITY", 1)
    max_position: int = _geti("MAX_POSITION", 3)
    contract_multiplier: float = _getf("CONTRACT_MULTIPLIER", 2.0)
    # Costs applied in the backfill so results are honest (per side, in index points)
    commission_per_side: float = _getf("COMMISSION_PER_SIDE", 0.75)  # ~$0.75 MNQ typical
    slippage_points: float = _getf("SLIPPAGE_POINTS", 0.5)
    # Mode: paper (default) / testnet / live
    mode: str = _get("MODE", "paper")
    # Capital cap (required for any non-paper mode)
    max_capital: float = _getf("MAX_CAPITAL", 0.0)
    # Broker: sim (default) / alpaca_paper / tradovate_demo
    broker: str = _get("BROKER", "sim")
    # Alpaca paper credentials + host. Paper host is the only accepted host.
    alpaca_key: str = _get("ALPACA_API_KEY_ID", "")
    alpaca_secret: str = _get("ALPACA_API_SECRET_KEY", "")
    alpaca_base_url: str = _get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    # Executable symbol for a real broker (Alpaca has no futures; QQQ tracks the NDX).
    alpaca_symbol: str = _get("ALPACA_SYMBOL", "QQQ")
    # Tradovate DEMO credentials + host. The demo host is the only accepted host.
    tradovate_base_url: str = _get("TRADOVATE_BASE_URL", "https://demo.tradovateapi.com/v1")
    tradovate_username: str = _get("TRADOVATE_USERNAME", "")
    tradovate_password: str = _get("TRADOVATE_PASSWORD", "")
    tradovate_app_id: str = _get("TRADOVATE_APP_ID", "MNQLearningBot")
    tradovate_app_version: str = _get("TRADOVATE_APP_VERSION", "1.0")
    tradovate_cid: str = _get("TRADOVATE_CID", "")
    tradovate_sec: str = _get("TRADOVATE_SEC", "")
    tradovate_account_spec: str = _get("TRADOVATE_ACCOUNT_SPEC", "")  # blank = first account
    # Tradovate trades a specific contract (e.g. MNQM5). "MNQ" = auto-resolve front month.
    tradovate_symbol: str = _get("TRADOVATE_SYMBOL", "MNQ")
    # Telegram (optional; alerts are logged if unset — never a hard dependency)
    telegram_token: str = _get("TELEGRAM_TOKEN", "")
    telegram_chat_id: str = _get("TELEGRAM_CHAT_ID", "")
    # Paths
    db_path: str = _get("DB_PATH", "data/state.db")


CONFIG = Config()
