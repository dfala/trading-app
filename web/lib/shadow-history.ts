import { readFile, stat } from "node:fs/promises";
import path from "node:path";

import type {
  ShadowHistoryResponse,
  ShadowModelSeries,
} from "@/lib/types";

// Each shadow trading cycle appends one ShadowChallengerObservation per
// candidate model to this journal. We read the whole file and pivot it into
// per-model time series for the dashboard chart.
const DEFAULT_JOURNAL_PATH = path.join(
  /*turbopackIgnore: true*/ process.cwd(),
  "data",
  "runtime",
  "journal",
  "shadow-challenger-observations.jsonl",
);

export function shadowJournalPath(): string {
  const configured = process.env.TRADING_APP_SHADOW_JOURNAL?.trim();
  if (configured) {
    return path.isAbsolute(configured)
      ? configured
      : path.join(/*turbopackIgnore: true*/ process.cwd(), configured);
  }
  return DEFAULT_JOURNAL_PATH;
}

type RawObservation = {
  as_of?: string;
  model_key?: string;
  strategy_id?: string;
  version?: string;
  estimated_equity?: string | number;
};

export async function loadShadowHistory(): Promise<ShadowHistoryResponse> {
  const filePath = shadowJournalPath();
  let raw = "";
  try {
    await stat(/*turbopackIgnore: true*/ filePath);
    raw = await readFile(/*turbopackIgnore: true*/ filePath, "utf8");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") {
      return { generated_at: new Date().toISOString(), source: filePath, models: [] };
    }
    throw error;
  }

  const byModel = new Map<string, ShadowModelSeries>();

  for (const line of raw.split("\n")) {
    if (!line.trim()) continue;
    let row: RawObservation;
    try {
      row = JSON.parse(line) as RawObservation;
    } catch {
      // Skip malformed lines rather than fail the whole request — the journal
      // grows continuously and a partial write should not blank the chart.
      continue;
    }
    const key = row.model_key;
    const asOf = row.as_of;
    const equity = Number(row.estimated_equity);
    if (!key || !asOf || !Number.isFinite(equity)) continue;

    let series = byModel.get(key);
    if (!series) {
      series = {
        model_key: key,
        strategy_id: row.strategy_id,
        version: row.version,
        starting_equity: equity,
        latest_equity: equity,
        total_return: 0,
        points: [],
      };
      byModel.set(key, series);
    }
    series.points.push({ as_of: asOf, equity });
  }

  const models: ShadowModelSeries[] = [];
  for (const series of byModel.values()) {
    series.points.sort(
      (a, b) => Date.parse(a.as_of) - Date.parse(b.as_of),
    );
    if (series.points.length === 0) continue;
    series.starting_equity = series.points[0].equity;
    series.latest_equity = series.points[series.points.length - 1].equity;
    series.total_return =
      series.starting_equity > 0
        ? series.latest_equity / series.starting_equity - 1
        : 0;
    models.push(series);
  }

  // Sort with the strongest performer on top so the legend reads ranked.
  models.sort((a, b) => b.total_return - a.total_return);

  return {
    generated_at: new Date().toISOString(),
    source: filePath,
    models,
  };
}
