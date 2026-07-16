// scan: fetch recent real candles, compute the signal on the latest closed candle,
// run the risk check, apply memory (if the memory path is requested), and simulate a
// paper order only when an action passes. Prints timestamped logs throughout.

import { config } from "./config.js";
import { fetchCandles } from "./market.js";
import { evaluateAt } from "./strategy.js";
import { assessRisk } from "./risk.js";
import { applyMemory } from "./adaptiveFilter.js";
import { simulatePaperOrder } from "./execution.js";
import { isoDate, stamp } from "./util.js";
import type { Decision } from "./types.js";

export async function scan(useMemory = false): Promise<void> {
  console.log(`${stamp()} [scan] Fetching real ${config.symbol} ${config.interval} candles...`);
  const candles = await fetchCandles();
  const iLast = candles.length - 1; // latest CLOSED candle
  const c = candles[iLast];
  console.log(`${stamp()} [scan] Latest closed candle ${isoDate(c.time)} close=${c.close.toFixed(2)}`);

  const strat = evaluateAt(candles, iLast);
  console.log(`${stamp()} [scan] Signal: ${strat.signal} — ${strat.reason}`);

  const risk = assessRisk(strat.signal);
  console.log(`${stamp()} [scan] Risk: ${risk.action} — ${risk.reason}`);

  let action = risk.action;
  let reason = risk.reason;

  if (useMemory) {
    const mem = applyMemory(config.symbol, strat.signal, risk);
    action = mem.action;
    reason = mem.reason;
    console.log(`${stamp()} [scan] Memory: ${action} — ${reason}`);
  }

  const decision: Decision = {
    time: c.time,
    symbol: config.symbol,
    action,
    price: c.close,
    quantity: risk.quantity,
    reason,
    mode: "paper",
  };

  if (action === "BUY" || action === "SELL") {
    simulatePaperOrder(decision);
  } else {
    console.log(`${stamp()} [scan] Final decision: ${action} — no paper order simulated.`);
  }
}
