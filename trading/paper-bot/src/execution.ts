// Execution module. This ONLY ever simulates a paper order. There is deliberately
// no code path that reaches a real broker or exchange. If a paper broker/MCP adapter
// is added later it must be a verified future adapter behind this same interface.

import type { Decision } from "./types.js";
import { stamp } from "./util.js";

export function simulatePaperOrder(decision: Decision): void {
  const value = decision.price * decision.quantity * 2; // MNQ $2/point notional
  console.log(
    `${stamp()} [execution] PAPER ${decision.action} ${decision.quantity} ${decision.symbol} ` +
      `@ ${decision.price.toFixed(2)} (~$${value.toLocaleString()} notional). No real order sent.`,
  );
}
