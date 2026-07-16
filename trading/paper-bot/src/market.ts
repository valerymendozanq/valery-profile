// Real market data. Pulls daily OHLCV for MNQ=F (Micro E-mini Nasdaq-100) from the
// public Yahoo Finance chart endpoint. No API key. If data can't be fetched we throw
// loudly rather than inventing candles — honesty rule.

import type { Candle } from "./types.js";
import { config } from "./config.js";

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/125.0 Safari/537.36";

const HOSTS = [
  "https://query2.finance.yahoo.com",
  "https://query1.finance.yahoo.com",
];

export async function fetchCandles(
  symbol: string = config.symbol,
  interval: string = config.interval,
  range: string = config.range,
): Promise<Candle[]> {
  const enc = encodeURIComponent(symbol);
  let lastErr: unknown = null;

  for (const host of HOSTS) {
    const url = `${host}/v8/finance/chart/${enc}?range=${range}&interval=${interval}`;
    try {
      const res = await fetch(url, { headers: { "User-Agent": UA } });
      if (!res.ok) {
        lastErr = new Error(`HTTP ${res.status} from ${host}`);
        continue;
      }
      const json: any = await res.json();
      const result = json?.chart?.result?.[0];
      if (!result?.timestamp || !result?.indicators?.quote?.[0]) {
        lastErr = new Error(`Malformed chart payload from ${host}`);
        continue;
      }
      const ts: number[] = result.timestamp;
      const q = result.indicators.quote[0];
      const candles: Candle[] = [];
      for (let i = 0; i < ts.length; i++) {
        const o = q.open?.[i];
        const h = q.high?.[i];
        const l = q.low?.[i];
        const c = q.close?.[i];
        const v = q.volume?.[i];
        // Yahoo returns nulls for non-trading gaps; skip them, never fabricate.
        if (o == null || h == null || l == null || c == null) continue;
        candles.push({ time: ts[i], open: o, high: h, low: l, close: c, volume: v ?? 0 });
      }
      if (candles.length === 0) {
        lastErr = new Error(`No usable candles returned for ${symbol}`);
        continue;
      }
      return candles;
    } catch (err) {
      lastErr = err;
    }
  }
  throw new Error(
    `Could not fetch real market data for ${symbol} (${interval}, ${range}). ` +
      `Last error: ${String(lastErr)}`,
  );
}
