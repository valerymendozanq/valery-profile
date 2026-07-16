// Shared types for the MNQ paper-trading bot.

export interface Candle {
  time: number; // unix seconds of the candle open
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export type Signal = "BUY" | "SELL" | "HOLD";
export type FinalAction = "BUY" | "SELL" | "HOLD" | "SKIP";
export type Mode = "paper" | "replay";

export interface StrategyResult {
  signal: Signal;
  reason: string;
  fastEMA: number;
  slowEMA: number;
}

export interface RiskDecision {
  action: FinalAction;
  approved: boolean;
  reason: string;
  quantity: number;
}

export interface Decision {
  time: number;
  symbol: string;
  action: FinalAction;
  price: number;
  quantity: number;
  reason: string;
  mode: Mode;
}

// One completed replay trade (entry crossover -> exit crossover).
export interface Trade {
  entryTime: number;
  exitTime: number;
  entryPrice: number;
  exitPrice: number;
  points: number; // exitPrice - entryPrice, in index points
  pnl: number; // dollars, points * multiplier * quantity
  outcome: "WIN" | "LOSS" | "FLAT";
}

export interface ReplaySummary {
  totalSetups: number;
  wins: number;
  losses: number;
  flats: number;
  winRate: number;
  avgPnl: number;
  bestTrade: number;
  worstTrade: number;
  totalPnl: number;
  maxDrawdown: number;
}

// A row in data/ledger.csv
export interface LedgerRow {
  timestamp: string;
  symbol: string;
  action: FinalAction;
  price: number;
  quantity: number;
  reason: string;
  mode: string;
  outcome: string;
  pnl: number | "";
}
