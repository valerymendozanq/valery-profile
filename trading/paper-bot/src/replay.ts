// Replay engine. Builds the strategy's real trade-by-trade history from historical
// MNQ candles and prints an honest baseline (replay:raw) or a memory-gated pass
// (replay:memory).

import type { Candle, Trade, ReplaySummary } from "./types.js";
import { config } from "./config.js";
import { fetchCandles } from "./market.js";
import { ema } from "./strategy.js";
import { isoDate, usd, pct, stamp } from "./util.js";
import {
  ensureLedger,
  ensureLearnings,
  appendLedgerRow,
  appendLearning,
  readLedger,
  readLearnings,
} from "./memory.js";

// Walk the closes, enter long on a bullish 9/21 EMA cross, exit on the bearish
// cross. Each completed entry->exit pair is one trade. Long-only.
export function buildTrades(candles: Candle[]): Trade[] {
  const closes = candles.map((c) => c.close);
  const fast = ema(closes, config.fastPeriod);
  const slow = ema(closes, config.slowPeriod);
  const mult = config.contractMultiplier * config.quantity;

  const trades: Trade[] = [];
  let inPos = false;
  let entryIdx = -1;

  for (let i = 1; i < candles.length; i++) {
    if ([fast[i], slow[i], fast[i - 1], slow[i - 1]].some((x) => Number.isNaN(x))) continue;
    const crossedUp = fast[i - 1] <= slow[i - 1] && fast[i] > slow[i];
    const crossedDown = fast[i - 1] >= slow[i - 1] && fast[i] < slow[i];

    if (!inPos && crossedUp) {
      inPos = true;
      entryIdx = i;
    } else if (inPos && crossedDown) {
      const entry = candles[entryIdx];
      const exit = candles[i];
      const points = exit.close - entry.close;
      const pnl = points * mult;
      trades.push({
        entryTime: entry.time,
        exitTime: exit.time,
        entryPrice: entry.close,
        exitPrice: exit.close,
        points,
        pnl,
        outcome: points > 0 ? "WIN" : points < 0 ? "LOSS" : "FLAT",
      });
      inPos = false;
      entryIdx = -1;
    }
  }
  return trades;
}

export function summarize(trades: Trade[]): ReplaySummary {
  const wins = trades.filter((t) => t.outcome === "WIN").length;
  const losses = trades.filter((t) => t.outcome === "LOSS").length;
  const flats = trades.filter((t) => t.outcome === "FLAT").length;
  const pnls = trades.map((t) => t.pnl);
  const totalPnl = pnls.reduce((a, b) => a + b, 0);

  // Max drawdown on the cumulative equity curve.
  let peak = 0;
  let equity = 0;
  let maxDd = 0;
  for (const p of pnls) {
    equity += p;
    if (equity > peak) peak = equity;
    const dd = peak - equity;
    if (dd > maxDd) maxDd = dd;
  }

  return {
    totalSetups: trades.length,
    wins,
    losses,
    flats,
    winRate: trades.length ? wins / trades.length : 0,
    avgPnl: trades.length ? totalPnl / trades.length : 0,
    bestTrade: pnls.length ? Math.max(...pnls) : 0,
    worstTrade: pnls.length ? Math.min(...pnls) : 0,
    totalPnl,
    maxDrawdown: maxDd,
  };
}

function printTable(trades: Trade[]): void {
  console.log("\n  #  entry        exit         entry px   exit px    points     pnl        outcome");
  console.log("  -- ------------ ------------ ---------- ---------- ---------- ---------- -------");
  trades.forEach((t, i) => {
    console.log(
      `  ${String(i + 1).padStart(2)} ${isoDate(t.entryTime)}   ${isoDate(t.exitTime)}   ` +
        `${t.entryPrice.toFixed(2).padStart(9)}  ${t.exitPrice.toFixed(2).padStart(9)}  ` +
        `${t.points.toFixed(1).padStart(9)}  ${usd(t.pnl).padStart(9)}  ${t.outcome}`,
    );
  });
}

function printSummary(s: ReplaySummary): void {
  console.log("\n  Summary");
  console.log(`    Total setups : ${s.totalSetups}`);
  console.log(`    Wins/Losses  : ${s.wins} / ${s.losses}${s.flats ? ` (${s.flats} flat)` : ""}`);
  console.log(`    Win rate     : ${pct(s.winRate)}`);
  console.log(`    Avg PnL      : ${usd(s.avgPnl)}`);
  console.log(`    Best / Worst : ${usd(s.bestTrade)} / ${usd(s.worstTrade)}`);
  console.log(`    Total PnL    : ${usd(s.totalPnl)}`);
  console.log(`    Max drawdown : ${usd(s.maxDrawdown)}`);
}

// ---- replay:raw -------------------------------------------------------------
// Honest baseline. No memory is consulted. Real outcomes are appended to the
// ledger, and a plain-English lesson is written ONLY if a real losing setup exists.
export async function replayRaw(): Promise<void> {
  console.log(`${stamp()} [replay:raw] Scanner started for ${config.symbol} on ${config.interval}`);
  const candles = await fetchCandles();
  console.log(`${stamp()} [replay:raw] Loaded ${candles.length} real historical candles ` +
    `(${isoDate(candles[0].time)} -> ${isoDate(candles[candles.length - 1].time)})`);

  const trades = buildTrades(candles);
  if (trades.length === 0) {
    console.log(`${stamp()} [replay:raw] No completed EMA ${config.fastPeriod}/${config.slowPeriod} ` +
      `crossover setups in this window — not enough setups to judge.`);
    return;
  }

  printTable(trades);
  const summary = summarize(trades);
  printSummary(summary);

  if (summary.totalSetups < 20) {
    console.log(`\n  Note: only ${summary.totalSetups} setups — that's an anecdote, not evidence. ` +
      `20+ trades is the bar before trusting the edge.`);
  }

  // Record real outcomes to the ledger (memory may exist by now).
  ensureLedger();
  ensureLearnings();
  for (const t of trades) {
    appendLedgerRow({
      timestamp: isoDate(t.exitTime),
      symbol: config.symbol,
      action: "SELL", // trade closed on the bearish cross
      price: t.exitPrice,
      quantity: config.quantity,
      reason: `EMA ${config.fastPeriod}/${config.slowPeriod} swing closed`,
      mode: "replay",
      outcome: t.outcome,
      pnl: Number(t.pnl.toFixed(2)),
    });
  }

  // Write a lesson ONLY from real losing setups.
  const losers = trades.filter((t) => t.outcome === "LOSS");
  if (losers.length > 0) {
    const worst = losers.reduce((a, b) => (b.pnl < a.pnl ? b : a));
    appendLearning(
      `${config.symbol} BUY on EMA ${config.fastPeriod}/${config.slowPeriod} crossover has real ` +
        `losing setups (${losers.length}/${trades.length}). Worst: entry ${isoDate(worst.entryTime)} ` +
        `-> exit ${isoDate(worst.exitTime)}, ${usd(worst.pnl)}. Treat repeat long entries with caution.`,
    );
    console.log(`\n${stamp()} [replay:raw] Wrote a real lesson to ${config.learningsPath} ` +
      `(${losers.length} losing setups found).`);
  } else {
    console.log(`\n${stamp()} [replay:raw] No losing setups in this window — nothing seeded to learnings.`);
  }
}

// ---- replay:memory ----------------------------------------------------------
// Same strategy, but consults the ledger + learnings before allowing the latest
// signal. Skips only with a real prior warning; otherwise HOLD.
export async function replayMemory(): Promise<void> {
  console.log(`${stamp()} [replay:memory] Scanner started for ${config.symbol} on ${config.interval}`);
  const candles = await fetchCandles();
  console.log(`${stamp()} [replay:memory] Loaded ${candles.length} real historical candles`);

  const ledger = readLedger();
  const learnings = readLearnings();
  console.log(`${stamp()} [replay:memory] Loaded ${config.ledgerPath} (${ledger.length} rows)`);
  console.log(`${stamp()} [replay:memory] Loaded ${config.learningsPath}`);

  if (ledger.length === 0) {
    console.log(`\n  No memory yet. Run \`npm run replay:raw\` first to build a real ledger, ` +
      `then re-run replay:memory.`);
    return;
  }

  // Look at the most recent completed trade as "the setup we're about to repeat".
  const trades = buildTrades(candles);
  const last = trades[trades.length - 1];
  const priorLoss = ledger.find(
    (r) => r.symbol === config.symbol && r.outcome === "LOSS" && typeof r.pnl === "number" && r.pnl < 0,
  );
  const learningWarns = learnings.toLowerCase().includes(`${config.symbol.toLowerCase()} buy`);

  console.log(`${stamp()} [replay:memory] Detected latest EMA crossover trade ` +
    `${last ? `(closed ${isoDate(last.exitTime)}, ${usd(last.pnl)})` : "(none)"}`);
  console.log(`${stamp()} [replay:memory] Prior ${config.symbol} loss on record: ` +
    `${priorLoss ? `yes (${priorLoss.timestamp}, ${priorLoss.pnl})` : "none yet"}`);
  console.log(`${stamp()} [replay:memory] Matching learnings warning: ${learningWarns ? "yes" : "none yet"}`);

  if (priorLoss) {
    const reason = `Memory blocks a fresh BUY: ${config.symbol} has a real prior losing ` +
      `EMA crossover (${priorLoss.timestamp}, pnl ${priorLoss.pnl})` +
      (learningWarns ? ", and learnings.md warns about it" : "") + ". Decision: SKIP.";
    console.log(`\n  Decision: SKIP`);
    console.log(`  Reason : ${reason}`);
    console.log(`  No paper order was sent.`);
    appendLedgerRow({
      timestamp: isoDate(candles[candles.length - 1].time),
      symbol: config.symbol,
      action: "SKIP",
      price: candles[candles.length - 1].close,
      quantity: 0,
      reason,
      mode: "memory",
      outcome: "SKIPPED",
      pnl: "",
    });
    console.log(`  Logged a SKIP row to ${config.ledgerPath}.`);
  } else {
    console.log(`\n  Decision: HOLD`);
    console.log(`  Reason : No real prior loss to justify a SKIP yet — keep paper testing.`);
    console.log(`  No paper order was sent.`);
  }
}
