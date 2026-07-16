"""Alpaca **paper** broker adapter (stdlib urllib only).

Safety design:
- HARD-refuses any base URL that is not the Alpaca paper host. There is no way to point
  this adapter at the live trading API.
- Requires API key + secret from the environment; they never touch source or logs.
- `check()` reads the account and reports it as paper (guaranteed by the paper host) and
  surfaces any Alpaca-side block flags.

Alpaca has no futures, so MNQ can't trade here. Use QQQ (tracks the Nasdaq-100) as the
executable proxy — set ALPACA_SYMBOL / SYMBOL accordingly.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional
from urllib.parse import urlparse

from ..config import CONFIG
from .base import Account, Broker, BrokerError, BrokerPosition, OrderResult

PAPER_HOST = "paper-api.alpaca.markets"


class AlpacaPaperBroker(Broker):
    name = "alpaca_paper"

    def __init__(self) -> None:
        self.base_url = CONFIG.alpaca_base_url.rstrip("/")
        host = urlparse(self.base_url).hostname or ""
        if host != PAPER_HOST:
            raise BrokerError(
                f"Refusing to use Alpaca host '{host}'. This adapter is paper-only and "
                f"accepts exactly https://{PAPER_HOST}. (No live trading path exists here.)"
            )
        if not (CONFIG.alpaca_key and CONFIG.alpaca_secret):
            raise BrokerError(
                "Alpaca paper mode needs ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY "
                "(paper keys). Set them in the environment — never in source."
            )
        self._headers = {
            "APCA-API-KEY-ID": CONFIG.alpaca_key,
            "APCA-API-SECRET-KEY": CONFIG.alpaca_secret,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, body: Optional[dict] = None) -> tuple[int, dict]:
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=self._headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8") or "{}"
                return resp.status, json.loads(raw)
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8") if e.fp else ""
            try:
                parsed = json.loads(raw) if raw else {}
            except ValueError:
                parsed = {"message": raw}
            return e.code, parsed
        except urllib.error.URLError as e:
            raise BrokerError(f"Alpaca network error: {e}") from e

    def check(self) -> Account:
        status, acct = self._request("GET", "/v2/account")
        if status == 401:
            raise BrokerError("Alpaca rejected the credentials (401). Check your paper keys.")
        if status != 200:
            raise BrokerError(f"Alpaca /v2/account returned {status}: {acct.get('message', acct)}")
        blocks = [k for k in ("trading_blocked", "account_blocked", "transfers_blocked") if acct.get(k)]
        acct_status = acct.get("status", "UNKNOWN")
        if blocks:
            acct_status += " (" + ", ".join(blocks) + ")"
        return Account(
            is_paper=True,  # guaranteed: constructor allows only the paper host
            status=acct_status,
            cash=float(acct.get("cash", 0) or 0),
            raw=acct,
        )

    def get_position(self, symbol: str) -> Optional[BrokerPosition]:
        status, pos = self._request("GET", f"/v2/positions/{symbol}")
        if status == 404:
            return None
        if status != 200:
            raise BrokerError(f"Alpaca /v2/positions/{symbol} returned {status}: {pos.get('message', pos)}")
        return BrokerPosition(
            symbol=pos["symbol"],
            qty=float(pos["qty"]),
            avg_price=float(pos["avg_entry_price"]),
        )

    def submit(self, symbol: str, action: str, qty: int, price: float) -> OrderResult:
        side = "buy" if action == "BUY" else "sell"
        body = {
            "symbol": symbol,
            "qty": str(qty),
            "side": side,
            "type": "market",
            "time_in_force": "day",
        }
        status, order = self._request("POST", "/v2/orders", body)
        if status not in (200, 201):
            return OrderResult(
                ok=False, order_id="", symbol=symbol, action=action, qty=qty, price=price,
                simulated=False, detail=f"Alpaca order rejected ({status}): {order.get('message', order)}",
            )
        return OrderResult(
            ok=True,
            order_id=str(order.get("id", "")),
            symbol=symbol,
            action=action,
            qty=qty,
            price=price,
            simulated=False,  # a real order on the PAPER account (fake money)
            detail=f"Alpaca paper order accepted (status={order.get('status')}).",
        )
