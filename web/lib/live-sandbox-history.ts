import { readFile, stat } from "node:fs/promises";
import path from "node:path";

import type {
  LiveSandboxEquityPoint,
  LiveSandboxHistoryResponse,
} from "@/lib/types";

// Each live-sandbox trading cycle appends one record with the marked-to-market
// sandbox equity (plus deployed capital and cash). We read the whole file and
// pivot it into a single equity time series for the live dashboard chart — the
// same shape the client accumulates from snapshots, so the two merge cleanly.
const DEFAULT_JOURNAL_PATH = path.join(
  /*turbopackIgnore: true*/ process.cwd(),
  "data",
  "runtime",
  "journal",
  "live-sandbox-cycles.jsonl",
);

export function liveSandboxJournalPath(): string {
  const configured = process.env.TRADING_APP_LIVE_SANDBOX_JOURNAL?.trim();
  if (configured) {
    return path.isAbsolute(configured)
      ? configured
      : path.join(/*turbopackIgnore: true*/ process.cwd(), configured);
  }
  return DEFAULT_JOURNAL_PATH;
}

type RawCycle = {
  as_of?: string;
  sandbox_equity?: string | number;
  cap_deployed?: string | number;
  sandbox_cash?: string | number;
};

export async function loadLiveSandboxHistory(): Promise<LiveSandboxHistoryResponse> {
  const filePath = liveSandboxJournalPath();
  let raw = "";
  try {
    await stat(/*turbopackIgnore: true*/ filePath);
    raw = await readFile(/*turbopackIgnore: true*/ filePath, "utf8");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return { generated_at: new Date().toISOString(), source: filePath, points: [] };
    }
    throw error;
  }

  // Keep the last record per timestamp so re-runs of a cycle don't duplicate a
  // point, then sort ascending by time.
  const byTimestamp = new Map<number, LiveSandboxEquityPoint>();

  for (const line of raw.split("\n")) {
    if (!line.trim()) continue;
    let row: RawCycle;
    try {
      row = JSON.parse(line) as RawCycle;
    } catch {
      // Skip malformed lines rather than fail the whole request — the journal
      // grows continuously and a partial write should not blank the chart.
      continue;
    }
    const asOf = row.as_of;
    const equity = Number(row.sandbox_equity);
    if (!asOf || !Number.isFinite(equity)) continue;
    const timestamp = Date.parse(asOf);
    if (!Number.isFinite(timestamp)) continue;
    const deployed = Number(row.cap_deployed);
    const cash = Number(row.sandbox_cash);
    byTimestamp.set(timestamp, {
      as_of: asOf,
      equity,
      deployed: Number.isFinite(deployed) ? deployed : 0,
      cash: Number.isFinite(cash) ? cash : 0,
    });
  }

  const points = Array.from(byTimestamp.values()).sort(
    (a, b) => Date.parse(a.as_of) - Date.parse(b.as_of),
  );

  return {
    generated_at: new Date().toISOString(),
    source: filePath,
    points,
  };
}
