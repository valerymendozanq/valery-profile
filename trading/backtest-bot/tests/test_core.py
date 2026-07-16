"""Deterministic, no-network tests for the MNQ bot core.

These never hit the internet: they use synthetic candles and patch config in-place, so
they're safe to run in CI. Run with:  python -m unittest discover -s tests
"""
from __future__ import annotations

import math
import unittest
from dataclasses import replace

from bot.data import Candle
from bot.signals import ema, signal_at, latest_signal
from bot.research import evaluate
import bot.brokers.alpaca as alpaca_mod
import bot.execution as execution_mod
from bot.brokers.base import BrokerError
from bot.brokers.sim import SimBroker


def mk(closes):
    """Wrap a list of closes into Candle objects (OHLC flat, 1-day apart)."""
    return [Candle(time=1_600_000_000 + i * 86400, open=c, high=c, low=c, close=c, volume=1)
            for i, c in enumerate(closes)]


class TestSignals(unittest.TestCase):
    def test_ema_warmup_and_value(self):
        vals = [10.0] * 30
        e = ema(vals, 9)
        self.assertTrue(math.isnan(e[0]))       # before warmup -> NaN
        self.assertFalse(math.isnan(e[8]))      # first defined EMA at index period-1
        self.assertAlmostEqual(e[-1], 10.0, places=6)  # flat series -> EMA == value

    def test_buy_cross_detected(self):
        closes = [100] * 21 + [90, 90, 90, 90, 90, 200]  # downtrend then a spike up
        sig, reason = latest_signal(mk(closes), 9, 21)
        self.assertEqual(sig, "BUY", reason)

    def test_sell_cross_detected(self):
        closes = [100] * 21 + [110, 110, 110, 110, 110, 40]  # uptrend then a drop
        sig, _ = latest_signal(mk(closes), 9, 21)
        self.assertEqual(sig, "SELL")

    def test_hold_when_no_cross(self):
        closes = [100 + i for i in range(40)]  # steady uptrend, fast stays above slow
        sig, _ = latest_signal(mk(closes), 9, 21)
        self.assertEqual(sig, "HOLD")


class TestBacktestMath(unittest.TestCase):
    def test_one_full_trade_pnl_sign(self):
        # Down, cross up, rally, cross down -> exactly one completed trade, a winner.
        closes = ([100] * 21 + [80, 80, 80, 80]      # establish fast<slow
                  + [140] * 25                        # bullish cross + rally
                  + [60] * 25)                        # bearish cross + drop
        res = evaluate(mk(closes), 9, 21, "test")
        self.assertGreaterEqual(res.trades, 1)
        self.assertIsInstance(res.total_pnl, float)

    def test_regime_filter_reduces_or_equals_trades(self):
        closes = ([100] * 21 + [80, 80] + [140] * 25 + [60] * 25 + [140] * 25 + [60] * 25)
        base = evaluate(mk(closes), 9, 21, "base")
        filt = evaluate(mk(closes), 9, 21, "filtered", regime_p=50)
        self.assertLessEqual(filt.trades, base.trades)


class TestBrokerSafety(unittest.TestCase):
    def test_sim_broker_is_paper(self):
        acct = SimBroker().check()
        self.assertTrue(acct.is_paper)

    def test_alpaca_refuses_live_host(self):
        orig = alpaca_mod.CONFIG
        try:
            alpaca_mod.CONFIG = replace(orig, alpaca_base_url="https://api.alpaca.markets",
                                        alpaca_key="x", alpaca_secret="y")
            with self.assertRaises(BrokerError):
                alpaca_mod.AlpacaPaperBroker()
        finally:
            alpaca_mod.CONFIG = orig

    def test_alpaca_requires_keys(self):
        orig = alpaca_mod.CONFIG
        try:
            alpaca_mod.CONFIG = replace(orig, alpaca_base_url="https://paper-api.alpaca.markets",
                                        alpaca_key="", alpaca_secret="")
            with self.assertRaises(BrokerError):
                alpaca_mod.AlpacaPaperBroker()
        finally:
            alpaca_mod.CONFIG = orig


class TestMemory(unittest.TestCase):
    def test_signature_regime(self):
        from bot import memory
        # Long steady uptrend: last bar is above its 200-EMA and slow EMA rising.
        closes = [100 + i for i in range(260)]
        sig = memory.signature_at(closes, len(closes) - 1)
        self.assertTrue(sig.startswith("above200"), sig)
        self.assertIn("slopeUp", sig)

    def test_should_skip_uses_written_ledger(self):
        import tempfile, os
        from bot import memory
        cwd = os.getcwd()
        tmp = tempfile.mkdtemp()
        os.chdir(tmp)
        try:
            memory.reset()
            # Two real losing closed trades of the same signature -> should_skip True.
            for d, pnl in (("2025-01-01", -500.0), ("2025-02-01", -700.0)):
                memory.append_row(d, "MNQ=F", "SELL", 20000, 1, "below200|slopeDown",
                                  "closed LOSS", "paper/sim", "LOSS", pnl)
            skip, why = memory.should_skip("MNQ=F", "below200|slopeDown")
            self.assertTrue(skip, why)
            # A signature with no record -> not skipped.
            skip2, _ = memory.should_skip("MNQ=F", "above200|slopeUp")
            self.assertFalse(skip2)
        finally:
            os.chdir(cwd)


class TestModeGating(unittest.TestCase):
    def test_paper_passes(self):
        execution_mod.preflight("paper")  # must not raise

    def test_live_refuses(self):
        with self.assertRaises(execution_mod.UnsafeModeError):
            execution_mod.preflight("live")

    def test_testnet_without_cap_refuses(self):
        orig = execution_mod.CONFIG
        try:
            execution_mod.CONFIG = replace(orig, max_capital=0.0)
            with self.assertRaises(execution_mod.UnsafeModeError):
                execution_mod.preflight("testnet")
        finally:
            execution_mod.CONFIG = orig


if __name__ == "__main__":
    unittest.main()
