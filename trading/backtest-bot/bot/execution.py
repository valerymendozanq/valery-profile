"""Execution adapters with hard mode gating.

paper   -> simulate only (default).
testnet -> refuses unless a verified testnet adapter + MAX_CAPITAL exist. None ships
           here, so it halts safely instead of pretending.
live    -> refuses to start unless the API key is trade-only (no withdrawals) AND
           MAX_CAPITAL is set. No live adapter ships here, so it always halts safely.

The whole point: there is no code path in this repo that can place a real order.
"""
from __future__ import annotations

from dataclasses import dataclass

from .config import CONFIG


class UnsafeModeError(RuntimeError):
    """Raised when a non-paper mode is requested without its safety preconditions."""


@dataclass
class Fill:
    symbol: str
    action: str
    price: float
    quantity: int
    mode: str
    simulated: bool


def preflight(mode: str) -> None:
    """Enforce the safety ladder before anything runs. paper always passes."""
    mode = mode.lower()
    if mode == "paper":
        return
    if mode in ("testnet", "live"):
        # Both require an explicit capital cap.
        if CONFIG.max_capital <= 0:
            raise UnsafeModeError(
                f"Mode '{mode}' requires MAX_CAPITAL to be set to a positive cap. Refusing to start."
            )
        # Live additionally requires a trade-only key attestation.
        if mode == "live":
            raise UnsafeModeError(
                "Live mode refuses to start: this build ships no live adapter, and a live "
                "adapter must use a TRADE-ONLY API key (withdrawals disabled, IP-whitelisted) "
                "and be verified in testnet first. Stay on paper."
            )
        # testnet with a cap but no shipped adapter: halt safely rather than fake it.
        raise UnsafeModeError(
            "Testnet mode has a capital cap set but no verified testnet adapter is wired in "
            "this build. Halting safely instead of simulating a real venue."
        )
    raise UnsafeModeError(f"Unknown mode '{mode}'. Use paper (default), testnet, or live.")


def execute(symbol: str, action: str, price: float, quantity: int) -> Fill:
    """Only ever returns a simulated paper fill. preflight() has already gated mode."""
    return Fill(
        symbol=symbol,
        action=action,
        price=price,
        quantity=quantity,
        mode=CONFIG.mode,
        simulated=True,
    )
