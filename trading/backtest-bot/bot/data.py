"""Market data. Daily OHLCV for MNQ=F from the public Yahoo Finance chart endpoint.

Standard library only (urllib). If real data can't be fetched we raise — we never
fabricate candles.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import List

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
)
_HOSTS = ["https://query2.finance.yahoo.com", "https://query1.finance.yahoo.com"]


@dataclass(frozen=True)
class Candle:
    time: int  # unix seconds (candle open)
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def date(self) -> str:
        import datetime as _dt

        return _dt.datetime.utcfromtimestamp(self.time).strftime("%Y-%m-%d")


def fetch_candles(symbol: str, interval: str = "1d", rng: str = "5y") -> List[Candle]:
    from urllib.parse import quote

    enc = quote(symbol, safe="")
    last_err: Exception | None = None
    for host in _HOSTS:
        url = f"{host}/v8/finance/chart/{enc}?range={rng}&interval={interval}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            result = (payload.get("chart") or {}).get("result") or []
            if not result:
                last_err = RuntimeError(f"No result from {host}")
                continue
            r = result[0]
            ts = r.get("timestamp") or []
            quote_block = ((r.get("indicators") or {}).get("quote") or [{}])[0]
            candles: List[Candle] = []
            for i, t in enumerate(ts):
                o = quote_block.get("open", [None])[i]
                h = quote_block.get("high", [None])[i]
                lo = quote_block.get("low", [None])[i]
                c = quote_block.get("close", [None])[i]
                v = quote_block.get("volume", [None])[i]
                if None in (o, h, lo, c):  # skip gaps, never fabricate
                    continue
                candles.append(Candle(int(t), float(o), float(h), float(lo), float(c), float(v or 0)))
            if not candles:
                last_err = RuntimeError(f"No usable candles from {host}")
                continue
            return candles
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as e:
            last_err = e
    raise RuntimeError(
        f"Could not fetch real market data for {symbol} ({interval}, {rng}). Last error: {last_err}"
    )
