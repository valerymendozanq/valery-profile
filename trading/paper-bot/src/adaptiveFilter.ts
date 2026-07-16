// Adaptive filter: the memory path's gate. Before a BUY/SELL is allowed, it checks
// the ledger + learnings for a real prior loss on a similar setup and, if found,
// downgrades the action to SKIP. It never invents a reason to skip — a SKIP requires
// a real losing row in the ledger.

import type { RiskDecision, Signal } from "./types.js";
import { readLedger, readLearnings } from "./memory.js";

export interface FilterResult {
  action: RiskDecision["action"];
  skipped: boolean;
  reason: string;
}

// A "similar setup" here = same symbol + same signal direction that produced a real
// LOSS outcome in a prior replay/paper trade.
export function applyMemory(
  symbol: string,
  signal: Signal,
  risk: RiskDecision,
): FilterResult {
  if (!risk.approved || (signal !== "BUY" && signal !== "SELL")) {
    return { action: risk.action, skipped: false, reason: risk.reason };
  }

  const ledger = readLedger();
  const priorLoss = ledger.find(
    (r) =>
      r.symbol === symbol &&
      r.action === signal &&
      r.outcome === "LOSS" &&
      typeof r.pnl === "number" &&
      (r.pnl as number) < 0,
  );

  const learnings = readLearnings();
  const learningWarns = learnings
    .toLowerCase()
    .includes(`${symbol.toLowerCase()} ${signal.toLowerCase()}`);

  if (priorLoss) {
    return {
      action: "SKIP",
      skipped: true,
      reason:
        `Memory blocks this ${signal}: ${symbol} previously lost on the same setup ` +
        `(${priorLoss.timestamp}, pnl ${priorLoss.pnl}). ` +
        (learningWarns ? "learnings.md warns about it too. " : "") +
        "SKIP — no paper order.",
    };
  }

  // No real prior loss -> we do NOT skip. Let the risk-approved action stand.
  return {
    action: risk.action,
    skipped: false,
    reason:
      `Memory checked: no prior ${symbol} ${signal} loss on record. ` +
      "Proceeding with the raw-approved action.",
  };
}
