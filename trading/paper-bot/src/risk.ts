// Risk module. Approves or rejects a signal. Sizing is in MNQ contracts.
// The core rule from the instructions file: if quantity > max position -> SKIP.

import type { RiskDecision, Signal } from "./types.js";
import { config } from "./config.js";

export function assessRisk(signal: Signal, quantity: number = config.quantity): RiskDecision {
  // HOLD carries through untouched.
  if (signal === "HOLD") {
    return { action: "HOLD", approved: false, reason: "No fresh signal — nothing to size.", quantity: 0 };
  }

  if (quantity <= 0) {
    return {
      action: "SKIP",
      approved: false,
      reason: `Configured quantity is ${quantity} contracts — nothing to trade.`,
      quantity,
    };
  }

  if (quantity > config.maxPosition) {
    return {
      action: "SKIP",
      approved: false,
      reason: `Quantity ${quantity} exceeds max position ${config.maxPosition} contracts — SKIP.`,
      quantity,
    };
  }

  return {
    action: signal, // BUY or SELL
    approved: true,
    reason: `Risk OK: ${quantity} contract(s) within max ${config.maxPosition}.`,
    quantity,
  };
}
