"""Broker interface shared by every adapter."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


class BrokerError(RuntimeError):
    """Any broker-side failure (auth, network, unsafe config)."""


@dataclass
class Account:
    is_paper: bool
    status: str
    cash: float
    raw: dict = field(default_factory=dict)


@dataclass
class BrokerPosition:
    symbol: str
    qty: float
    avg_price: float


@dataclass
class OrderResult:
    ok: bool
    order_id: str
    symbol: str
    action: str
    qty: float
    price: float
    simulated: bool
    detail: str


class Broker:
    """Base class. Adapters implement check/get_position/submit."""

    name: str = "base"

    def check(self) -> Account:  # pragma: no cover - interface
        raise NotImplementedError

    def get_position(self, symbol: str) -> Optional[BrokerPosition]:  # pragma: no cover
        raise NotImplementedError

    def submit(self, symbol: str, action: str, qty: int, price: float) -> OrderResult:  # pragma: no cover
        raise NotImplementedError
