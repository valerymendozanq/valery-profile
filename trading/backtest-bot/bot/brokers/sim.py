"""Local simulation broker. The default. Never touches a network venue — it just
returns a simulated fill so the rest of the bot has a uniform broker interface."""
from __future__ import annotations

from typing import Optional

from ..config import CONFIG
from .base import Account, Broker, BrokerPosition, OrderResult


class SimBroker(Broker):
    name = "sim"

    def check(self) -> Account:
        cash = CONFIG.max_capital if CONFIG.max_capital > 0 else 100_000.0
        return Account(is_paper=True, status="SIM_LOCAL", cash=cash, raw={})

    def get_position(self, symbol: str) -> Optional[BrokerPosition]:
        # The SQLite state layer owns position truth for the sim broker; the caller
        # consults it directly, so we report None here.
        return None

    def submit(self, symbol: str, action: str, qty: int, price: float) -> OrderResult:
        return OrderResult(
            ok=True,
            order_id="sim-local",
            symbol=symbol,
            action=action,
            qty=qty,
            price=price,
            simulated=True,
            detail="Local paper simulation — no order left this process.",
        )
