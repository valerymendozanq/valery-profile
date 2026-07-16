// Small shared helpers.

export function stamp(): string {
  return `[${new Date().toISOString()}]`;
}

// Format a unix-seconds timestamp as an ISO date (UTC) for logs/tables.
export function isoDate(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toISOString().slice(0, 10);
}

export function pct(n: number): string {
  return `${(n * 100).toFixed(1)}%`;
}

export function usd(n: number): string {
  const sign = n < 0 ? "-" : "";
  return `${sign}$${Math.abs(n).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}
