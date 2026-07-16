// Central config. Everything here is overridable via environment variables so the
// bot is easy to experiment with. Paper/local only — no secrets belong in here.

function num(name: string, fallback: number): number {
  const v = process.env[name];
  if (v === undefined || v.trim() === "") return fallback;
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function str(name: string, fallback: string): string {
  const v = process.env[name];
  return v === undefined || v.trim() === "" ? fallback : v;
}

export const config = {
  // Market
  symbol: str("SYMBOL", "MNQ=F"), // Micro E-mini Nasdaq-100 futures
  interval: str("INTERVAL", "1d"), // daily only for this strategy
  range: str("RANGE", "5y"), // how much history to pull for replay

  // Strategy
  fastPeriod: num("FAST_PERIOD", 9),
  slowPeriod: num("SLOW_PERIOD", 21),

  // Risk / sizing (MNQ contracts; multiplier is $2 per index point)
  quantity: num("QUANTITY", 1), // contracts per entry
  maxPosition: num("MAX_POSITION", 3), // max contracts allowed
  contractMultiplier: num("CONTRACT_MULTIPLIER", 2), // $ per index point (MNQ = $2)

  // Files
  ledgerPath: "data/ledger.csv",
  learningsPath: "data/learnings.md",
} as const;

export type Config = typeof config;
