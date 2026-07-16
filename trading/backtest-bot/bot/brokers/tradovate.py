"""Tradovate **DEMO** broker adapter (stdlib urllib only).

Real futures API, real MNQ contracts, fake money. Safety design mirrors the Alpaca
adapter:
- HARD-refuses any base URL that is not the Tradovate demo host. There is no way to
  point this at the live trading API.
- Credentials come from the environment; they never touch source or logs.
- `check()` authenticates and reads the account; the demo host guarantees it's paper.

Unlike stocks, Tradovate trades a specific contract (e.g. MNQM5). Set TRADOVATE_SYMBOL
to the exact contract, or leave it "MNQ" to let the adapter resolve a front-month
contract via /contract/suggest.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Optional
from urllib.parse import urlparse, quote

from ..config import CONFIG
from .base import Account, Broker, BrokerError, BrokerPosition, OrderResult

DEMO_HOST = "demo.tradovateapi.com"
_MONTH_CODE = re.compile(r"[FGHJKMNQUVXZ]\d{1,2}$")


class TradovateDemoBroker(Broker):
    name = "tradovate_demo"

    def __init__(self) -> None:
        self.base_url = CONFIG.tradovate_base_url.rstrip("/")
        host = urlparse(self.base_url).hostname or ""
        if host != DEMO_HOST:
            raise BrokerError(
                f"Refusing to use Tradovate host '{host}'. This adapter is demo-only and "
                f"accepts exactly https://{DEMO_HOST}/v1. (No live trading path exists here.)"
            )
        missing = [k for k, v in (
            ("TRADOVATE_USERNAME", CONFIG.tradovate_username),
            ("TRADOVATE_PASSWORD", CONFIG.tradovate_password),
            ("TRADOVATE_CID", CONFIG.tradovate_cid),
            ("TRADOVATE_SEC", CONFIG.tradovate_sec),
        ) if not v]
        if missing:
            raise BrokerError(
                "Tradovate demo mode needs " + ", ".join(missing) +
                " in the environment (get them from the Tradovate API Access page). "
                "Never put them in source."
            )
        self._token: Optional[str] = None
        self._account_id: Optional[int] = None
        self._account_spec: Optional[str] = None

    # --- HTTP ---
    def _request(self, method: str, path: str, body: Optional[dict] = None,
                 auth: bool = True) -> tuple[int, object]:
        url = f"{self.base_url}{path}"
        headers = {"Content-Type": "application/json"}
        if auth:
            if not self._token:
                self._authenticate()
            headers["Authorization"] = f"Bearer {self._token}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=25) as resp:
                raw = resp.read().decode("utf-8") or "null"
                return resp.status, json.loads(raw)
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8") if e.fp else ""
            try:
                parsed = json.loads(raw) if raw else {}
            except ValueError:
                parsed = {"errorText": raw}
            return e.code, parsed
        except urllib.error.URLError as e:
            raise BrokerError(f"Tradovate network error: {e}") from e

    def _authenticate(self) -> None:
        body = {
            "name": CONFIG.tradovate_username,
            "password": CONFIG.tradovate_password,
            "appId": CONFIG.tradovate_app_id,
            "appVersion": CONFIG.tradovate_app_version,
            "cid": int(CONFIG.tradovate_cid) if str(CONFIG.tradovate_cid).isdigit() else CONFIG.tradovate_cid,
            "sec": CONFIG.tradovate_sec,
        }
        status, data = self._request("POST", "/auth/accesstokenrequest", body, auth=False)
        if status != 200 or not isinstance(data, dict):
            raise BrokerError(f"Tradovate auth failed ({status}): {data}")
        if data.get("errorText"):
            raise BrokerError(f"Tradovate auth rejected: {data['errorText']}")
        if data.get("p-ticket"):
            raise BrokerError("Tradovate returned a captcha/penalty ticket — log in via the app "
                              "once, then retry (too many attempts).")
        token = data.get("accessToken")
        if not token:
            raise BrokerError(f"Tradovate auth returned no accessToken: {data}")
        self._token = token

    # --- accounts ---
    def _ensure_account(self) -> None:
        if self._account_id is not None:
            return
        status, accts = self._request("GET", "/account/list")
        if status != 200 or not isinstance(accts, list) or not accts:
            raise BrokerError(f"Tradovate /account/list returned {status}: {accts}")
        chosen = None
        if CONFIG.tradovate_account_spec:
            chosen = next((a for a in accts if a.get("name") == CONFIG.tradovate_account_spec), None)
            if chosen is None:
                raise BrokerError(f"Tradovate account '{CONFIG.tradovate_account_spec}' not found.")
        else:
            chosen = accts[0]
        self._account_id = chosen["id"]
        self._account_spec = chosen["name"]

    def check(self) -> Account:
        self._authenticate()
        self._ensure_account()
        cash = 0.0
        status, snap = self._request("POST", "/cashBalance/getcashbalancesnapshot",
                                     {"accountId": self._account_id})
        if status == 200 and isinstance(snap, dict):
            cash = float(snap.get("totalCashValue", 0) or 0)
        return Account(
            is_paper=True,  # guaranteed: constructor allows only the demo host
            status=f"DEMO account '{self._account_spec}' (id {self._account_id})",
            cash=cash,
            raw={"account_id": self._account_id, "account_spec": self._account_spec},
        )

    # --- contracts ---
    def _resolve_contract(self, symbol: str) -> tuple[int, str]:
        sym = symbol.upper()
        if _MONTH_CODE.search(sym):  # explicit contract like MNQM5
            status, data = self._request("GET", f"/contract/find?name={quote(sym)}")
            if status == 200 and isinstance(data, dict) and data.get("id"):
                return data["id"], data["name"]
        # otherwise resolve a front-month contract by product symbol
        status, data = self._request("GET", f"/contract/suggest?t={quote(sym)}&l=10")
        if status == 200 and isinstance(data, list) and data:
            return data[0]["id"], data[0]["name"]
        raise BrokerError(f"Tradovate could not resolve a contract for '{symbol}'. "
                          f"Set TRADOVATE_SYMBOL to an exact contract like MNQM5.")

    def get_position(self, symbol: str) -> Optional[BrokerPosition]:
        self._ensure_account()
        contract_id, name = self._resolve_contract(symbol)
        status, positions = self._request("GET", "/position/list")
        if status != 200 or not isinstance(positions, list):
            raise BrokerError(f"Tradovate /position/list returned {status}: {positions}")
        for p in positions:
            if p.get("contractId") == contract_id and p.get("netPos"):
                net = p["netPos"]
                return BrokerPosition(symbol=name, qty=abs(net), avg_price=float(p.get("netPrice") or 0))
        return None

    def submit(self, symbol: str, action: str, qty: int, price: float) -> OrderResult:
        self._ensure_account()
        contract_id, name = self._resolve_contract(symbol)
        body = {
            "accountSpec": self._account_spec,
            "accountId": self._account_id,
            "action": "Buy" if action == "BUY" else "Sell",
            "symbol": name,
            "orderQty": int(qty),
            "orderType": "Market",
            "isAutomated": True,  # Tradovate requires flagging automated orders
        }
        status, order = self._request("POST", "/order/placeorder", body)
        if status not in (200, 201) or (isinstance(order, dict) and order.get("failureReason")):
            detail = order.get("failureText") or order.get("errorText") or order if isinstance(order, dict) else order
            return OrderResult(ok=False, order_id="", symbol=name, action=action, qty=qty,
                               price=price, simulated=False, detail=f"Tradovate order rejected: {detail}")
        oid = str(order.get("orderId", "")) if isinstance(order, dict) else ""
        return OrderResult(ok=True, order_id=oid, symbol=name, action=action, qty=qty, price=price,
                           simulated=False, detail="Tradovate DEMO order accepted (fake money).")
