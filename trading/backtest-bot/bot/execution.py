"""Execution gating + broker factory.

Two independent safety layers:

1. MODE gate (`preflight`): paper (default) runs; testnet/live REFUSE to start. This
   build ships no live venue.
2. BROKER selection (`get_broker`): sim (local simulation, default) or alpaca_paper.
   The Alpaca adapter is itself paper-only and refuses any non-paper host.

Because non-paper MODEs are refused before a broker is ever built, a real broker only
runs under MODE=paper — and even then only against Alpaca's PAPER account (fake money).
There is no code path in this repo that can place a live, real-money order.
"""
from __future__ import annotations

from .config import CONFIG
from .brokers.base import Broker, BrokerError
from .brokers.sim import SimBroker
from .brokers.alpaca import AlpacaPaperBroker


class UnsafeModeError(RuntimeError):
    """Raised when a non-paper mode is requested without its safety preconditions."""


def preflight(mode: str) -> None:
    """Enforce the safety ladder before anything runs. paper always passes."""
    mode = mode.lower()
    if mode == "paper":
        return
    if mode in ("testnet", "live"):
        if CONFIG.max_capital <= 0:
            raise UnsafeModeError(
                f"Mode '{mode}' requires MAX_CAPITAL to be set to a positive cap. Refusing to start."
            )
        if mode == "live":
            raise UnsafeModeError(
                "Live mode refuses to start: this build ships no live adapter, and a live "
                "adapter must use a TRADE-ONLY API key (withdrawals disabled, IP-whitelisted) "
                "and be verified in testnet first. Stay on paper."
            )
        raise UnsafeModeError(
            "Testnet mode has a capital cap set but no verified testnet adapter is wired in "
            "this build. Halting safely instead of simulating a real venue."
        )
    raise UnsafeModeError(f"Unknown mode '{mode}'. Use paper (default), testnet, or live.")


def get_broker() -> Broker:
    """Build the configured broker. Raises BrokerError on unsafe/incomplete config."""
    choice = CONFIG.broker.lower()
    if choice == "sim":
        return SimBroker()
    if choice == "alpaca_paper":
        return AlpacaPaperBroker()  # ctor enforces paper host + key presence
    raise BrokerError(f"Unknown BROKER '{CONFIG.broker}'. Use 'sim' or 'alpaca_paper'.")


def execution_symbol() -> str:
    """The symbol orders are actually placed against. For a real broker with no futures,
    that's the ETF proxy; for sim it's whatever SYMBOL the strategy runs on."""
    return CONFIG.alpaca_symbol if CONFIG.broker.lower() == "alpaca_paper" else CONFIG.symbol
