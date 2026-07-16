// Two-file memory layer: data/ledger.csv + data/learnings.md.
// Only real replay/paper outcomes are ever written here. No seeded fake losses.

import { existsSync, mkdirSync, readFileSync, writeFileSync, appendFileSync } from "node:fs";
import { dirname } from "node:path";
import type { LedgerRow } from "./types.js";
import { config } from "./config.js";

const LEDGER_HEADER = "timestamp,symbol,action,price,quantity,reason,mode,outcome,pnl";

function ensureDir(path: string): void {
  const dir = dirname(path);
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
}

export function ensureLedger(): void {
  ensureDir(config.ledgerPath);
  if (!existsSync(config.ledgerPath)) {
    writeFileSync(config.ledgerPath, LEDGER_HEADER + "\n");
  }
}

export function ensureLearnings(): void {
  ensureDir(config.learningsPath);
  if (!existsSync(config.learningsPath)) {
    writeFileSync(
      config.learningsPath,
      `# Learnings\n\nPlain-English lessons distilled from **real** closed trades only.\n` +
        `Nothing here is seeded or invented.\n\n`,
    );
  }
}

// CSV-escape a field that may contain commas/quotes (the reason text does).
function esc(field: string): string {
  if (/[",\n]/.test(field)) return `"${field.replace(/"/g, '""')}"`;
  return field;
}

export function appendLedgerRow(row: LedgerRow): void {
  ensureLedger();
  const line = [
    row.timestamp,
    row.symbol,
    row.action,
    row.price,
    row.quantity,
    esc(row.reason),
    row.mode,
    row.outcome,
    row.pnl === "" ? "" : row.pnl,
  ].join(",");
  appendFileSync(config.ledgerPath, line + "\n");
}

export function readLedger(): LedgerRow[] {
  if (!existsSync(config.ledgerPath)) return [];
  const lines = readFileSync(config.ledgerPath, "utf8").trim().split("\n");
  const rows: LedgerRow[] = [];
  for (let i = 1; i < lines.length; i++) {
    const cols = splitCsv(lines[i]);
    if (cols.length < 9) continue;
    rows.push({
      timestamp: cols[0],
      symbol: cols[1],
      action: cols[2] as LedgerRow["action"],
      price: Number(cols[3]),
      quantity: Number(cols[4]),
      reason: cols[5],
      mode: cols[6],
      outcome: cols[7],
      pnl: cols[8] === "" ? "" : Number(cols[8]),
    });
  }
  return rows;
}

// Minimal CSV splitter that respects double-quoted fields.
function splitCsv(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let inQ = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQ) {
      if (ch === '"' && line[i + 1] === '"') { cur += '"'; i++; }
      else if (ch === '"') inQ = false;
      else cur += ch;
    } else {
      if (ch === '"') inQ = true;
      else if (ch === ",") { out.push(cur); cur = ""; }
      else cur += ch;
    }
  }
  out.push(cur);
  return out;
}

export function appendLearning(text: string): void {
  ensureLearnings();
  appendFileSync(config.learningsPath, `- ${text}\n`);
}

export function readLearnings(): string {
  if (!existsSync(config.learningsPath)) return "";
  return readFileSync(config.learningsPath, "utf8");
}

export function resetMemory(): void {
  ensureDir(config.ledgerPath);
  writeFileSync(config.ledgerPath, LEDGER_HEADER + "\n");
  writeFileSync(
    config.learningsPath,
    `# Learnings\n\nPlain-English lessons distilled from **real** closed trades only.\n` +
      `Nothing here is seeded or invented.\n\n`,
  );
}
