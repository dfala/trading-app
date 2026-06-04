import { readdir, readFile, stat } from "node:fs/promises";
import path from "node:path";

import type {
  ReplayReportKind,
  ReplayReportMetricSnapshot,
  ReplayReportSummary,
} from "@/lib/types";

const DEFAULT_REPLAY_REPORT_ROOT = path.join(
  /*turbopackIgnore: true*/ process.cwd(),
  "data",
  "research",
  "replay",
);

export function replayReportRoot() {
  const configured = process.env.TRADING_APP_REPLAY_REPORT_DIR?.trim();
  if (configured) {
    return path.isAbsolute(configured)
      ? configured
      : path.join(/*turbopackIgnore: true*/ process.cwd(), "data", configured);
  }
  return DEFAULT_REPLAY_REPORT_ROOT;
}

export async function listReplayReports(): Promise<ReplayReportSummary[]> {
  const reports = (
    await Promise.all(
      replayReportRoots().map(async ({ root, prefix }) => {
        const markdownFiles = await findMarkdownFiles(root);
        return Promise.all(
          markdownFiles.map(async (filePath) => {
            const [contents, fileStat] = await Promise.all([
              readFile(/*turbopackIgnore: true*/ filePath, "utf8"),
              stat(/*turbopackIgnore: true*/ filePath),
            ]);
            const companionContents = await readCompanionComparisonReport(
              filePath,
            );
            const relativePath = prefixedReportId(
              prefix,
              toPosixPath(path.relative(root, filePath)),
            );
            return summarizeReport(
              relativePath,
              contents,
              fileStat,
              companionContents,
            );
          }),
        );
      }),
    )
  ).flat();

  return reports.sort(compareReplayReports);
}

export async function readReplayReport(id: string): Promise<string> {
  const matchingRoots = replayReportRoots().filter(({ prefix }) =>
    prefix ? id.startsWith(`${prefix}/`) : !id.startsWith("research/"),
  );
  for (const { root, prefix } of matchingRoots) {
    const localId = prefix ? id.slice(prefix.length + 1) : id;
    const filePath = resolveReportPath(root, localId);
    try {
      return await readFile(/*turbopackIgnore: true*/ filePath, "utf8");
    } catch (error) {
      if (
        !(error instanceof Error) ||
        !("code" in error) ||
        error.code !== "ENOENT"
      ) {
        throw error;
      }
    }
  }
  throw new Error("Replay report not found.");
}

export function chooseDefaultReplayReport(
  reports: ReplayReportSummary[],
): ReplayReportSummary | undefined {
  return (
    reports.find(
      (report) =>
        report.kind === "comparison" &&
        report.relativePath.includes("2016-2026") &&
        report.relativePath.includes("sip") &&
        !report.relativePath.includes("cost"),
    ) ??
    reports.find(
      (report) =>
        report.kind === "comparison" &&
        report.relativePath.includes("2016-2026") &&
        report.relativePath.includes("sip"),
    ) ??
    reports.find((report) => report.kind === "comparison") ??
    reports[0]
  );
}

async function findMarkdownFiles(root: string): Promise<string[]> {
  try {
    const rootStat = await stat(/*turbopackIgnore: true*/ root);
    if (!rootStat.isDirectory()) {
      return [];
    }
  } catch {
    return [];
  }

  const files: string[] = [];
  await walk(root, files);
  return files;
}

async function walk(directory: string, files: string[]) {
  const entries = await readdir(/*turbopackIgnore: true*/ directory, {
    withFileTypes: true,
  });
  for (const entry of entries) {
    if (entry.name.startsWith(".")) {
      continue;
    }
    const entryPath = path.join(
      /*turbopackIgnore: true*/ directory,
      entry.name,
    );
    if (entry.isDirectory()) {
      await walk(entryPath, files);
    } else if (entry.isFile() && entry.name.endsWith(".md")) {
      files.push(entryPath);
    }
  }
}

async function readCompanionComparisonReport(filePath: string) {
  if (!filePath.endsWith("-summary.md")) {
    return undefined;
  }
  const companionPath = filePath.replace(/-summary\.md$/, "-comparison.md");
  try {
    return await readFile(/*turbopackIgnore: true*/ companionPath, "utf8");
  } catch (error) {
    if (
      error instanceof Error &&
      "code" in error &&
      error.code === "ENOENT"
    ) {
      return undefined;
    }
    throw error;
  }
}

function resolveReportPath(root: string, id: string) {
  if (!id.endsWith(".md")) {
    throw new Error("Replay report ids must point to markdown files.");
  }

  const filePath = path.resolve(/*turbopackIgnore: true*/ root, id);
  const relative = path.relative(root, filePath);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error("Replay report path is outside the configured report root.");
  }
  return filePath;
}

function summarizeReport(
  relativePath: string,
  contents: string,
  fileStat: { mtime: Date; size: number },
  companionContents?: string,
): ReplayReportSummary {
  const fileName = path.posix.basename(relativePath);
  const kind = reportKind(relativePath);
  const metadata = parseSummaryMetadata(contents);
  const currentChampion = metadata.get("current champion");
  const rawChampion = metadata.get("champion") ?? metadata.get("champion by raw return");
  const championModelKey = rawChampion ?? currentChampion;
  const gateAlignedCandidate = metadata.get("gate-aligned research candidate");
  const ranking =
    gateAlignedCandidate && companionContents
      ? parseTopRanking(companionContents, championModelKey, gateAlignedCandidate) ??
        parseTopRanking(contents, championModelKey)
      : parseTopRanking(contents, championModelKey);
  const title = parseTitle(contents) ?? titleFromFileName(fileName);
  const range = metadata.get("range");
  const benchmark = metadata.get("benchmark") ?? ranking?.benchmark;
  const champion =
    metadata.get("champion") ??
    metadata.get("champion by raw return") ??
    currentChampion ??
    metadata.get("recommended challenger") ??
    metadata.get("policy") ??
    ranking?.strategy ??
    undefined;

  return {
    id: relativePath,
    title,
    fileName,
    relativePath,
    kind,
    updatedAt: fileStat.mtime.toISOString(),
    sizeBytes: fileStat.size,
    runId: metadata.get("run id"),
    range,
    benchmark,
    champion,
    policy: metadata.get("policy"),
    strategyCount: parseInteger(metadata.get("strategies compared")),
    skippedCount: parseInteger(metadata.get("strategies skipped")),
    summary: parseSummarySentence(contents),
    tags: buildTags(relativePath, kind, metadata, ranking),
    topMetric: ranking ?? metricsFromSummary(metadata),
  };
}

function compareReplayReports(
  left: ReplayReportSummary,
  right: ReplayReportSummary,
) {
  const kindScore = (report: ReplayReportSummary) =>
    report.kind === "comparison" ? 0 : report.kind === "strategy" ? 1 : 2;
  const kindDelta = kindScore(left) - kindScore(right);
  if (kindDelta !== 0) {
    return kindDelta;
  }
  return (
    new Date(right.updatedAt).getTime() - new Date(left.updatedAt).getTime() ||
    left.relativePath.localeCompare(right.relativePath)
  );
}

function reportKind(relativePath: string): ReplayReportKind {
  if (relativePath.startsWith("strategies/")) {
    return "strategy";
  }
  if (
    relativePath.endsWith("-comparison.md") ||
    relativePath.startsWith("learning-cycle-") ||
    relativePath.startsWith("replay-discovery-") ||
    relativePath.startsWith("replay-hypothesis-") ||
    relativePath.startsWith("research/hypothesis_") ||
    relativePath.startsWith("research/overnight_")
  ) {
    return "comparison";
  }
  return "other";
}

function replayReportRoots() {
  const primaryRoot = replayReportRoot();
  const roots = [{ root: primaryRoot, prefix: "" }];
  for (const researchRoot of researchReportRootCandidates(primaryRoot)) {
    if (!roots.some((candidate) => candidate.root === researchRoot)) {
      roots.push({ root: researchRoot, prefix: "research" });
    }
  }
  return roots;
}

function researchReportRootCandidates(primaryRoot: string) {
  const configured = process.env.TRADING_APP_RESEARCH_REPORT_DIR?.trim();
  if (configured) {
    return [
      path.isAbsolute(configured)
        ? configured
        : path.join(/*turbopackIgnore: true*/ process.cwd(), configured),
    ];
  }
  if (!isDefaultReplayDataRoot(primaryRoot)) {
    return [];
  }
  return Array.from(
    new Set([
      path.join(/*turbopackIgnore: true*/ process.cwd(), "research"),
      path.join(/*turbopackIgnore: true*/ process.cwd(), "..", "research"),
      path.resolve(primaryRoot, "..", "..", "..", "research"),
    ]),
  );
}

function isDefaultReplayDataRoot(root: string) {
  return toPosixPath(path.normalize(root)).endsWith("/data/research/replay");
}

function prefixedReportId(prefix: string, relativePath: string) {
  return prefix ? `${prefix}/${relativePath}` : relativePath;
}

function parseTitle(contents: string) {
  return contents
    .split(/\r?\n/)
    .find((line) => line.startsWith("# "))
    ?.replace(/^#\s+/, "")
    .trim();
}

function parseSummaryMetadata(contents: string) {
  const metadata = new Map<string, string>();
  for (const line of sectionLines(contents, "Summary")) {
    if (!line.startsWith("- ")) {
      continue;
    }
    const separatorIndex = line.indexOf(":");
    if (separatorIndex < 0) {
      continue;
    }
    const key = line.slice(2, separatorIndex).trim().toLowerCase();
    const value = cleanMarkdownValue(line.slice(separatorIndex + 1));
    metadata.set(key, value);
  }
  for (const line of sectionLines(contents, "Metrics")) {
    if (!line.startsWith("- ")) {
      continue;
    }
    const separatorIndex = line.indexOf(":");
    if (separatorIndex < 0) {
      continue;
    }
    const key = line.slice(2, separatorIndex).trim().toLowerCase();
    const value = cleanMarkdownValue(line.slice(separatorIndex + 1));
    metadata.set(key, value);
  }
  return metadata;
}

function parseSummarySentence(contents: string) {
  return sectionLines(contents, "Summary")
    .map((line) => line.trim())
    .find((line) => line && !line.startsWith("- ") && !line.startsWith("|"));
}

function sectionLines(contents: string, heading: string) {
  const lines = contents.replace(/\r\n/g, "\n").split("\n");
  const start = lines.findIndex(
    (line) => line.trim().toLowerCase() === `## ${heading.toLowerCase()}`,
  );
  if (start < 0) {
    return [];
  }
  const result: string[] = [];
  for (let index = start + 1; index < lines.length; index += 1) {
    const line = lines[index];
    if (line.startsWith("## ")) {
      break;
    }
    result.push(line.trim());
  }
  return result;
}

function parseTopRanking(
  contents: string,
  championModelKey?: string,
  targetModelKey?: string,
): ReplayReportMetricSnapshot | undefined {
  return (
    parseRankingSection(contents, championModelKey, targetModelKey) ??
    parseCandidateScoreboard(contents, championModelKey, targetModelKey)
  );
}

function parseRankingSection(
  contents: string,
  championModelKey?: string,
  targetModelKey?: string,
): ReplayReportMetricSnapshot | undefined {
  const lines = sectionLines(contents, "Ranking");
  const headerIndex = lines.findIndex((line) => line.startsWith("| Rank |"));
  if (headerIndex < 0 || !lines[headerIndex + 2]) {
    return undefined;
  }

  const headers = markdownCells(lines[headerIndex]).map((header) =>
    header.toLowerCase(),
  );
  const rows = lines
    .slice(headerIndex + 2)
    .filter((line) => line.startsWith("|"))
    .map((line) => markdownCells(line));
  const cellFor = (row: string[], header: string) =>
    row[headers.indexOf(header)];
  const targetRow = targetModelKey
    ? rows.find((row) => cleanStrategyName(cellFor(row, "strategy")) === targetModelKey)
    : rows[0];
  if (!targetRow) {
    return undefined;
  }
  const championRow = championModelKey
    ? rows.find((row) => cleanStrategyName(cellFor(row, "strategy")) === championModelKey)
    : undefined;
  const cell = (header: string) => cellFor(targetRow, header);
  const delta = cell("delta vs benchmark");
  const championBaseline = championRow
    ? cellFor(championRow, "delta vs benchmark")
    : undefined;
  return {
    strategy: cleanStrategyName(cell("strategy")),
    net: cell("net"),
    benchmark: cell("benchmark"),
    delta,
    maxDrawdown: cell("max dd"),
    volatility: cell("vol"),
    turnover: cell("turnover"),
    trades: cell("trades"),
    leakage: cell("leakage"),
    championDelta: formatPercentDelta(delta, championBaseline),
    championBaseline,
    championRank: championRow ? cellFor(championRow, "rank") : undefined,
  };
}

function parseCandidateScoreboard(
  contents: string,
  championModelKey?: string,
  targetModelKey?: string,
): ReplayReportMetricSnapshot | undefined {
  const lines = sectionLines(contents, "Candidate Scoreboard");
  const headerIndex = lines.findIndex((line) => line.startsWith("| Rank |"));
  if (headerIndex < 0 || !lines[headerIndex + 2]) {
    return undefined;
  }

  const headers = markdownCells(lines[headerIndex]).map((header) =>
    header.toLowerCase(),
  );
  const rows = lines
    .slice(headerIndex + 2)
    .filter((line) => line.startsWith("|"))
    .map((line) => markdownCells(line));
  const cellFor = (row: string[], header: string) =>
    row[headers.indexOf(header)];
  const firstRow = targetModelKey
    ? rows.find(
        (row) => cleanStrategyName(cellFor(row, "candidate")) === targetModelKey,
      )
    : rows[0];
  if (!firstRow) {
    return undefined;
  }
  const cell = (header: string) => cellFor(firstRow, header);
  const fullDelta = cell("full delta");
  const status = cell("status");
  const championRow = championModelKey
    ? rows.find(
        (row) => cleanStrategyName(cellFor(row, "candidate")) === championModelKey,
      )
    : undefined;
  const championBaseline = championRow
    ? cellFor(championRow, "full delta")
    : undefined;
  const championDelta = formatPercentDelta(fullDelta, championBaseline);
  return {
    strategy: cleanStrategyName(cell("candidate")),
    net: fullDelta,
    benchmark: cell("stress delta"),
    delta: fullDelta,
    maxDrawdown: cell("worst dd"),
    volatility: cell("risk score"),
    turnover: cell("avg fold delta"),
    trades: cell("positive folds"),
    leakage: cell("leakage") ?? (status ? "n/a" : undefined),
    championDelta,
    championBaseline,
    championRank: championRow ? cellFor(championRow, "rank") : undefined,
  };
}

function metricsFromSummary(
  metadata: Map<string, string>,
): ReplayReportMetricSnapshot | undefined {
  const net = metadata.get("net total return");
  const benchmark = metadata.get("benchmark total return");
  const delta = metadata.get("excess return");
  if (!net && !benchmark && !delta) {
    return undefined;
  }
  return {
    strategy: metadata.get("policy"),
    net,
    benchmark,
    delta,
    maxDrawdown: metadata.get("max drawdown"),
    volatility: metadata.get("annualized volatility"),
    turnover: metadata.get("turnover"),
    trades: metadata.get("trades"),
    leakage: metadata.get("status"),
  };
}

function markdownCells(line: string) {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cleanMarkdownValue(cell));
}

function buildTags(
  relativePath: string,
  kind: ReplayReportKind,
  metadata: Map<string, string>,
  ranking?: ReplayReportMetricSnapshot,
) {
  const tags = new Set<string>();
  tags.add(
    kind === "comparison"
      ? "Comparison"
      : kind === "strategy"
        ? "Strategy detail"
        : "Report",
  );
  if (relativePath.includes("sip")) tags.add("SIP");
  if (relativePath.includes("iex")) tags.add("IEX");
  if (relativePath.includes("grid")) tags.add("Grid");
  if (relativePath.includes("momentum")) tags.add("Momentum");
  if (relativePath.includes("cost")) tags.add("Cost sensitivity");
  if (metadata.get("range")) tags.add(metadata.get("range") as string);
  if (metadata.get("benchmark") ?? ranking?.benchmark) {
    tags.add(`Benchmark ${metadata.get("benchmark") ?? ranking?.benchmark}`);
  }
  return Array.from(tags).slice(0, 6);
}

function cleanMarkdownValue(value?: string) {
  return (value ?? "")
    .trim()
    .replace(/^`|`$/g, "")
    .replace(/`/g, "")
    .replace(/\*\*/g, "")
    .trim();
}

function cleanStrategyName(value?: string) {
  if (!value) {
    return undefined;
  }
  const modelId = /\(`?([^`)]+)`?\)/.exec(value);
  return cleanMarkdownValue(modelId?.[1] ?? value);
}

function parseInteger(value?: string) {
  if (!value) {
    return undefined;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isNaN(parsed) ? undefined : parsed;
}

function formatPercentDelta(left?: string, right?: string) {
  const leftValue = parsePercentNumber(left);
  const rightValue = parsePercentNumber(right);
  if (leftValue === undefined || rightValue === undefined) {
    return undefined;
  }
  const delta = leftValue - rightValue;
  return `${delta >= 0 ? "+" : ""}${delta.toFixed(2)}%`;
}

function parsePercentNumber(value?: string) {
  if (!value) {
    return undefined;
  }
  const parsed = Number.parseFloat(value.replace(/,/g, "").replace("%", ""));
  return Number.isNaN(parsed) ? undefined : parsed;
}

function titleFromFileName(fileName: string) {
  return fileName
    .replace(/\.md$/, "")
    .split("-")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function toPosixPath(value: string) {
  return value.split(path.sep).join(path.posix.sep);
}
