"use client";

import {
  AlertTriangle,
  BookOpen,
  FileText,
  Gauge,
  PanelLeftClose,
  PanelLeftOpen,
  RefreshCw,
  Search,
  Table2,
  TrendingUp,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

const INDEX_COLLAPSED_STORAGE_KEY = "replay.index.collapsed";

import type {
  ReplayReportKind,
  ReplayReportMetricSnapshot,
  ReplayReportSummary,
} from "@/lib/types";

type ReplayReportsPanelProps = {
  reports: ReplayReportSummary[];
  selectedId?: string;
  selectedReport?: ReplayReportSummary;
  content: string;
  loading: boolean;
  error?: string | null;
  onSelect: (id: string) => void;
  onRefresh: () => void;
};

type ReportFilter = ReplayReportKind | "all";

const FILTERS: { key: ReportFilter; label: string }[] = [
  { key: "comparison", label: "Comparisons" },
  { key: "strategy", label: "Strategies" },
  { key: "all", label: "All" },
];

export function ReplayReportsPanel({
  reports,
  selectedId,
  selectedReport,
  content,
  loading,
  error,
  onSelect,
  onRefresh,
}: ReplayReportsPanelProps) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<ReportFilter>("comparison");
  const [indexCollapsed, setIndexCollapsed] = useState(false);
  useEffect(() => {
    try {
      if (window.localStorage.getItem(INDEX_COLLAPSED_STORAGE_KEY) === "true") {
        setIndexCollapsed(true);
      }
    } catch {
      /* localStorage unavailable; keep default */
    }
  }, []);
  const toggleIndex = useCallback(() => {
    setIndexCollapsed((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(
          INDEX_COLLAPSED_STORAGE_KEY,
          next ? "true" : "false",
        );
      } catch {
        /* ignore persistence failures */
      }
      return next;
    });
  }, []);
  const selected =
    selectedReport ?? reports.find((report) => report.id === selectedId);
  const counts = useMemo(() => countReports(reports), [reports]);
  const visibleReports = useMemo(
    () => filterReports(reports, filter, query),
    [filter, query, reports],
  );
  const topMetric = selected?.topMetric;

  return (
    <section className="replay-lab" aria-labelledby="replay-lab-heading">
      <div className="replay-lab__head">
        <div>
          <span className="eyebrow">Replay Evidence</span>
          <h2 id="replay-lab-heading">Historical replay library</h2>
          <p>
            Research evidence only. These results do not change paper or live
            trading authority.
          </p>
        </div>
        <button
          type="button"
          className="icon-action"
          aria-label="Refresh replay reports"
          onClick={onRefresh}
          disabled={loading}
        >
          <RefreshCw size={17} aria-hidden="true" />
        </button>
      </div>

      <div className="replay-scoreboard" aria-label="Selected replay summary">
        <MetricCard
          icon={<FileText size={17} aria-hidden="true" />}
          label="Reports"
          value={reports.length.toString()}
          detail={`${counts.comparison} comparisons - ${counts.strategy} strategies`}
        />
        <MetricCard
          icon={<TrendingUp size={17} aria-hidden="true" />}
          label={topMetric?.championDelta ? "Vs Champion" : "Champion"}
          value={
            topMetric?.championDelta ??
            shortModelName(selected?.champion ?? topMetric?.strategy)
          }
          detail={
            topMetric?.championDelta
              ? topMetric.championBaseline
                ? `Champion ${topMetric.championBaseline}`
                : "Current champion comparison"
              : selected?.benchmark
                ? `Benchmark ${selected.benchmark}`
                : "No benchmark parsed"
          }
          tone={metricTone(topMetric?.championDelta)}
        />
        <MetricCard
          icon={<Gauge size={17} aria-hidden="true" />}
          label="Delta"
          value={topMetric?.delta ?? "-"}
          detail={
            topMetric?.net ? `Net ${topMetric.net}` : "No top-line metric"
          }
          tone={metricTone(topMetric?.delta)}
        />
        <MetricCard
          icon={<Table2 size={17} aria-hidden="true" />}
          label="Leakage"
          value={topMetric?.leakage ?? "-"}
          detail={selected?.range ?? "Range unavailable"}
          tone={topMetric?.leakage === "pass" ? "pos" : undefined}
        />
      </div>

      {error ? (
        <div className="replay-alert" role="alert">
          <AlertTriangle size={17} aria-hidden="true" />
          <span>{error}</span>
        </div>
      ) : null}

      <div
        className={`replay-workbench${
          indexCollapsed ? " replay-workbench--collapsed" : ""
        }`}
      >
        {indexCollapsed ? null : (
        <aside className="replay-index" aria-label="Replay reports">
          <div className="replay-index__tools">
            <label className="replay-search">
              <Search size={16} aria-hidden="true" />
              <input
                aria-label="Search replay reports"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search"
              />
            </label>
            <div className="replay-filter" aria-label="Report kind">
              {FILTERS.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  aria-pressed={filter === item.key}
                  onClick={() => setFilter(item.key)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>

          <div className="replay-list" aria-live="polite">
            {visibleReports.length ? (
              visibleReports.map((report) => (
                <button
                  key={report.id}
                  type="button"
                  className="replay-list__item"
                  aria-pressed={report.id === selected?.id}
                  onClick={() => onSelect(report.id)}
                >
                  <span className="replay-list__kind">
                    {kindLabel(report.kind)}
                  </span>
                  <strong>{displayTitle(report)}</strong>
                  <span>{report.summary ?? report.relativePath}</span>
                  <span className="replay-list__meta">
                    {formatDate(report.updatedAt)}
                    {report.topMetric?.delta ? ` - ${report.topMetric.delta}` : ""}
                  </span>
                </button>
              ))
            ) : (
              <p className="empty">No replay markdown reports match this view.</p>
            )}
          </div>
        </aside>
        )}

        <article className="replay-reader" aria-label="Replay report reader">
          <div className="replay-reader__toolbar">
            <button
              type="button"
              className="replay-toggle"
              onClick={toggleIndex}
              aria-label={
                indexCollapsed ? "Show reports index" : "Hide reports index"
              }
              aria-pressed={!indexCollapsed}
              title={indexCollapsed ? "Show reports" : "Hide reports"}
            >
              {indexCollapsed ? (
                <PanelLeftOpen size={16} aria-hidden="true" />
              ) : (
                <PanelLeftClose size={16} aria-hidden="true" />
              )}
              <span>{indexCollapsed ? "Reports" : "Hide reports"}</span>
            </button>
          </div>
          {loading && !selected ? (
            <div className="replay-reader__empty">
              <BookOpen size={20} aria-hidden="true" />
              <span>Loading replay evidence...</span>
            </div>
          ) : selected ? (
            <>
              <header className="replay-reader__head">
                <div>
                  <span className="eyebrow">{kindLabel(selected.kind)}</span>
                  <h3>{displayTitle(selected)}</h3>
                  <p>
                    {selected.relativePath} - {formatBytes(selected.sizeBytes)} -{" "}
                    {formatDate(selected.updatedAt)}
                  </p>
                </div>
                <div className="replay-tags" aria-label="Report tags">
                  {selected.tags.map((tag) => (
                    <span key={tag}>{tag}</span>
                  ))}
                </div>
              </header>
              {topMetric ? <TopMetricStrip metric={topMetric} /> : null}
              <MarkdownDocument content={content} />
            </>
          ) : (
            <div className="replay-reader__empty">
              <BookOpen size={20} aria-hidden="true" />
              <span>No replay markdown reports found.</span>
            </div>
          )}
        </article>
      </div>
    </section>
  );
}

function MetricCard({
  icon,
  label,
  value,
  detail,
  tone,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  detail: string;
  tone?: "pos" | "neg" | "warn";
}) {
  const className =
    `replay-metric ${tone ? `replay-metric--${tone}` : ""}`.trim();
  return (
    <div className={className}>
      <span className="replay-metric__icon">{icon}</span>
      <span className="replay-metric__label">{label}</span>
      <strong>{value}</strong>
      <span>{detail}</span>
    </div>
  );
}

function TopMetricStrip({ metric }: { metric: ReplayReportMetricSnapshot }) {
  const metrics = [
    ["Strategy", shortModelName(metric.strategy)],
    ["Net", metric.net ?? "-"],
    ["Benchmark", metric.benchmark ?? "-"],
    ["Max DD", metric.maxDrawdown ?? "-"],
    ["Vol", metric.volatility ?? "-"],
    ["Trades", metric.trades ?? "-"],
  ];
  return (
    <div className="replay-topline" aria-label="Top replay metrics">
      {metrics.map(([label, value]) => (
        <span key={label}>
          <small>{label}</small>
          <strong>{value}</strong>
        </span>
      ))}
    </div>
  );
}

type MarkdownBlock =
  | { type: "heading"; level: number; text: string }
  | { type: "paragraph"; text: string }
  | { type: "quote"; text: string }
  | { type: "list"; items: string[] }
  | { type: "table"; headers: string[]; rows: string[][] }
  | { type: "code"; text: string };

function MarkdownDocument({ content }: { content: string }) {
  const blocks = useMemo(() => parseMarkdown(content), [content]);
  return (
    <div className="markdown-body">
      {blocks.map((block, index) => (
        <MarkdownBlockView block={block} key={`${block.type}-${index}`} />
      ))}
    </div>
  );
}

function MarkdownBlockView({ block }: { block: MarkdownBlock }) {
  if (block.type === "heading") {
    const HeadingTag = `h${Math.min(block.level + 1, 4)}` as "h2" | "h3" | "h4";
    return (
      <HeadingTag className="markdown-heading">
        <InlineMarkdown text={block.text} />
      </HeadingTag>
    );
  }
  if (block.type === "paragraph") {
    return (
      <p>
        <InlineMarkdown text={block.text} />
      </p>
    );
  }
  if (block.type === "quote") {
    return (
      <blockquote>
        <InlineMarkdown text={block.text} />
      </blockquote>
    );
  }
  if (block.type === "list") {
    return (
      <ul>
        {block.items.map((item) => (
          <li key={item}>
            <InlineMarkdown text={item} />
          </li>
        ))}
      </ul>
    );
  }
  if (block.type === "code") {
    return <pre>{block.text}</pre>;
  }
  return (
    <div className="markdown-table-wrap">
      <table>
        <thead>
          <tr>
            {block.headers.map((header) => (
              <th key={header}>{header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {block.rows.map((row, rowIndex) => (
            <tr key={row.join("|") || rowIndex}>
              {row.map((cell, cellIndex) => (
                <td className={cellToneClass(cell)} key={`${cell}-${cellIndex}`}>
                  <InlineMarkdown text={cell} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function InlineMarkdown({ text }: { text: string }) {
  return (
    <>
      {text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).map((part, index) => {
        if (part.startsWith("`") && part.endsWith("`")) {
          return <code key={`${part}-${index}`}>{part.slice(1, -1)}</code>;
        }
        if (part.startsWith("**") && part.endsWith("**")) {
          return <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>;
        }
        return <span key={`${part}-${index}`}>{part}</span>;
      })}
    </>
  );
}

function parseMarkdown(markdown: string): MarkdownBlock[] {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const blocks: MarkdownBlock[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    if (line.startsWith("```")) {
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].startsWith("```")) {
        codeLines.push(lines[index]);
        index += 1;
      }
      blocks.push({ type: "code", text: codeLines.join("\n") });
      index += 1;
      continue;
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(line);
    if (heading) {
      blocks.push({
        type: "heading",
        level: heading[1].length,
        text: heading[2],
      });
      index += 1;
      continue;
    }

    if (line.startsWith("> ")) {
      const quoteLines: string[] = [];
      while (index < lines.length && lines[index].startsWith("> ")) {
        quoteLines.push(lines[index].replace(/^>\s?/, ""));
        index += 1;
      }
      blocks.push({ type: "quote", text: quoteLines.join(" ") });
      continue;
    }

    if (isMarkdownTable(lines, index)) {
      const headers = markdownCells(lines[index]);
      index += 2;
      const rows: string[][] = [];
      while (index < lines.length && lines[index].trim().startsWith("|")) {
        rows.push(markdownCells(lines[index]));
        index += 1;
      }
      blocks.push({ type: "table", headers, rows });
      continue;
    }

    if (line.startsWith("- ")) {
      const items: string[] = [];
      while (index < lines.length && lines[index].startsWith("- ")) {
        items.push(lines[index].replace(/^-\s+/, ""));
        index += 1;
      }
      blocks.push({ type: "list", items });
      continue;
    }

    const paragraphLines: string[] = [];
    while (
      index < lines.length &&
      lines[index].trim() &&
      !isBlockStart(lines, index)
    ) {
      paragraphLines.push(lines[index].trim());
      index += 1;
    }
    blocks.push({ type: "paragraph", text: paragraphLines.join(" ") });
  }

  return blocks;
}

function isBlockStart(lines: string[], index: number) {
  const line = lines[index];
  return (
    line.startsWith("#") ||
    line.startsWith("> ") ||
    line.startsWith("- ") ||
    line.startsWith("```") ||
    isMarkdownTable(lines, index)
  );
}

function isMarkdownTable(lines: string[], index: number) {
  return (
    lines[index]?.trim().startsWith("|") &&
    /^\|\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(
      lines[index + 1]?.trim() ?? "",
    )
  );
}

function markdownCells(line: string) {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function filterReports(
  reports: ReplayReportSummary[],
  filter: ReportFilter,
  query: string,
) {
  const normalizedQuery = normalizeReportSearchText(query);
  return reports.filter((report) => {
    if (filter !== "all" && report.kind !== filter) {
      return false;
    }
    if (!normalizedQuery) {
      return true;
    }
    return reportMatchesSearchForTest(report, query);
  });
}

export function normalizeReportSearchText(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function reportMatchesSearchForTest(
  report: ReplayReportSummary,
  query: string,
) {
  const normalizedQuery = normalizeReportSearchText(query);
  if (!normalizedQuery) {
    return true;
  }
  const haystack = reportSearchHaystack(report);
  return (
    haystack.toLowerCase().includes(normalizedQuery) ||
    normalizeReportSearchText(haystack).includes(normalizedQuery)
  );
}

function reportSearchHaystack(report: ReplayReportSummary) {
  return [
    report.title,
    report.relativePath,
    report.relativePath.replace(/[-_/]+/g, " "),
    report.summary,
    report.champion,
    report.policy,
    ...report.tags,
  ]
    .filter(Boolean)
    .join(" ");
}

function countReports(reports: ReplayReportSummary[]) {
  return reports.reduce(
    (counts, report) => {
      counts[report.kind] += 1;
      return counts;
    },
    { comparison: 0, strategy: 0, other: 0 },
  );
}

function displayTitle(report: ReplayReportSummary) {
  if (report.runId) {
    return report.runId;
  }
  return report.title;
}

function shortModelName(value?: string) {
  if (!value) {
    return "-";
  }
  const cleaned = value.replace(/Monthly Sector ETF Momentum\s*/i, "").trim();
  return cleaned.length > 42 ? `${cleaned.slice(0, 39)}...` : cleaned;
}

function kindLabel(kind: ReplayReportKind) {
  if (kind === "comparison") {
    return "Comparison";
  }
  if (kind === "strategy") {
    return "Strategy detail";
  }
  return "Report";
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function formatBytes(value: number) {
  if (value < 1024) {
    return `${value} B`;
  }
  return `${(value / 1024).toFixed(1)} KB`;
}

function metricTone(value?: string): "pos" | "neg" | undefined {
  if (!value) {
    return undefined;
  }
  if (value.trim().startsWith("-")) {
    return "neg";
  }
  if (value.trim().startsWith("+")) {
    return "pos";
  }
  return undefined;
}

function cellToneClass(value: string) {
  const trimmed = value.trim();
  if (/^\+\d/.test(trimmed)) {
    return "is-pos";
  }
  if (/^-\d/.test(trimmed)) {
    return "is-neg";
  }
  if (trimmed === "pass" || trimmed === "passed") {
    return "is-pos";
  }
  return undefined;
}
