import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, describe, expect, it } from "vitest";

import { GET as getReplayReports } from "@/app/api/replay-reports/route";
import { replayReportRoot } from "@/lib/replay-reports";

describe("replay report route", () => {
  let reportRoot: string | undefined;
  let researchRoot: string | undefined;

  afterEach(async () => {
    delete process.env.TRADING_APP_REPLAY_REPORT_DIR;
    delete process.env.TRADING_APP_RESEARCH_REPORT_DIR;
    if (reportRoot) {
      await rm(reportRoot, { force: true, recursive: true });
      reportRoot = undefined;
    }
    if (researchRoot) {
      await rm(researchRoot, { force: true, recursive: true });
      researchRoot = undefined;
    }
  });

  it("indexes top-level hypothesis research reports as comparison evidence", async () => {
    reportRoot = await mkdtemp(path.join(tmpdir(), "replay-reports-"));
    researchRoot = await mkdtemp(path.join(tmpdir(), "hypothesis-reports-"));
    process.env.TRADING_APP_REPLAY_REPORT_DIR = reportRoot;
    process.env.TRADING_APP_RESEARCH_REPORT_DIR = researchRoot;
    await writeFile(
      path.join(researchRoot, "hypothesis_02_market_drawdown_circuit_breaker.md"),
      [
        "# Hypothesis 2 - Market Drawdown Circuit Breaker",
        "",
        "## Verdict",
        "",
        "Pass for research continuation, not for live trading.",
      ].join("\n"),
    );

    const response = await getReplayReports(
      new Request(
        "http://localhost/api/replay-reports?id=research%2Fhypothesis_02_market_drawdown_circuit_breaker.md",
      ),
    );
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.selectedReport).toMatchObject({
      id: "research/hypothesis_02_market_drawdown_circuit_breaker.md",
      kind: "comparison",
      title: "Hypothesis 2 - Market Drawdown Circuit Breaker",
    });
    expect(payload.content).toContain("Pass for research continuation");
  });

  it("indexes overnight autonomous research reviews as comparison evidence", async () => {
    reportRoot = await mkdtemp(path.join(tmpdir(), "replay-reports-"));
    researchRoot = await mkdtemp(path.join(tmpdir(), "overnight-reports-"));
    process.env.TRADING_APP_REPLAY_REPORT_DIR = reportRoot;
    process.env.TRADING_APP_RESEARCH_REPORT_DIR = researchRoot;
    await writeFile(
      path.join(
        researchRoot,
        "overnight_autonomous_learning_review_2026_06_02.md",
      ),
      [
        "# Overnight Autonomous Learning Review - 2026-06-02",
        "",
        "## Executive Read",
        "",
        "The only repeated challenger worth continuing to paper-track is still a circuit breaker.",
      ].join("\n"),
    );

    const response = await getReplayReports(
      new Request(
        "http://localhost/api/replay-reports?id=research%2Fovernight_autonomous_learning_review_2026_06_02.md",
      ),
    );
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.selectedReport).toMatchObject({
      id: "research/overnight_autonomous_learning_review_2026_06_02.md",
      kind: "comparison",
      title: "Overnight Autonomous Learning Review - 2026-06-02",
    });
    expect(payload.content).toContain("only repeated challenger");
  });

  it("indexes markdown reports and returns the default comparison content", async () => {
    reportRoot = await mkdtemp(path.join(tmpdir(), "replay-reports-"));
    process.env.TRADING_APP_REPLAY_REPORT_DIR = reportRoot;
    await mkdir(path.join(reportRoot, "strategies"));
    await writeFile(
      path.join(reportRoot, "demo-comparison.md"),
      [
        "# Historical Replay Strategy Comparison",
        "",
        "## Summary",
        "",
        "- Run id: `demo-run`",
        "- Range: `2016-01-04` to `2026-05-29`",
        "- Benchmark: `SPY`",
        "- Strategies compared: `2`",
        "- Strategies skipped: `0`",
        "- Champion: `demo:1`",
        "",
        "Top strategy demo:1 beat the benchmark by +5.00%.",
        "",
        "## Ranking",
        "",
        "| Rank | Strategy | Net | Benchmark | Delta vs Benchmark | Max DD | Vol | Turnover | Trades | Leakage |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        "| 1 | Demo Strategy (`demo:1`) | 15.00% | 10.00% | +5.00% | -8.00% | 12.00% | 2.00 | 4 | pass |",
      ].join("\n"),
    );
    await writeFile(
      path.join(reportRoot, "strategies", "demo-strategy.md"),
      [
        "# Historical Replay Report",
        "",
        "## Summary",
        "",
        "- Run id: `demo-strategy`",
        "- Policy: `demo:1`",
        "- Trades: `4`",
      ].join("\n"),
    );

    const response = await getReplayReports(
      new Request("http://localhost/api/replay-reports"),
    );
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.reports).toHaveLength(2);
    expect(payload.selectedReport).toMatchObject({
      id: "demo-comparison.md",
      kind: "comparison",
      runId: "demo-run",
      benchmark: "SPY",
      champion: "demo:1",
      strategyCount: 2,
    });
    expect(payload.selectedReport.topMetric).toMatchObject({
      strategy: "demo:1",
      delta: "+5.00%",
      leakage: "pass",
    });
    expect(payload.content).toContain("## Ranking");
  });

  it("loads a selected nested markdown report by safe id", async () => {
    reportRoot = await mkdtemp(path.join(tmpdir(), "replay-reports-"));
    process.env.TRADING_APP_REPLAY_REPORT_DIR = reportRoot;
    await mkdir(path.join(reportRoot, "strategies"));
    await writeFile(
      path.join(reportRoot, "strategies", "demo-strategy.md"),
      [
        "# Historical Replay Report",
        "",
        "## Summary",
        "",
        "- Run id: `demo-strategy`",
        "- Policy: `demo:1`",
      ].join("\n"),
    );

    const response = await getReplayReports(
      new Request(
        "http://localhost/api/replay-reports?id=strategies%2Fdemo-strategy.md",
      ),
    );
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.selectedId).toBe("strategies/demo-strategy.md");
    expect(payload.selectedReport.kind).toBe("strategy");
    expect(payload.content).toContain("- Policy: `demo:1`");
  });

  it("classifies discovery markdown as comparison evidence", async () => {
    reportRoot = await mkdtemp(path.join(tmpdir(), "replay-reports-"));
    process.env.TRADING_APP_REPLAY_REPORT_DIR = reportRoot;
    await writeFile(
      path.join(reportRoot, "replay-discovery-demo.md"),
      [
        "# Replay Discovery Report",
        "",
        "## Summary",
        "",
        "- Run id: `replay-discovery-demo`",
        "- Benchmark: `SPY`",
        "",
        "17 candidate(s) beat the benchmark in every validation fold.",
      ].join("\n"),
    );

    const response = await getReplayReports(
      new Request(
        "http://localhost/api/replay-reports?id=replay-discovery-demo.md",
      ),
    );
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.selectedReport).toMatchObject({
      id: "replay-discovery-demo.md",
      kind: "comparison",
      runId: "replay-discovery-demo",
    });
  });

  it("classifies replay hypothesis summaries as comparison evidence", async () => {
    reportRoot = await mkdtemp(path.join(tmpdir(), "replay-reports-"));
    process.env.TRADING_APP_REPLAY_REPORT_DIR = reportRoot;
    await writeFile(
      path.join(reportRoot, "replay-hypothesis-2-demo-summary.md"),
      [
        "# Hypothesis 2 Shared-Harness Reproduction",
        "",
        "## Summary",
        "",
        "- Run id: `replay-hypothesis-2-demo`",
        "- Range: `2016-01-04` to `2026-05-29`",
        "- Benchmark: `SPY`",
        "- Champion by raw return: `market_drawdown_circuit_breaker:raw-champion`",
        "- Gate-aligned research candidate: `market_drawdown_circuit_breaker:preferred`",
      ].join("\n"),
    );
    await writeFile(
      path.join(reportRoot, "replay-hypothesis-2-demo-comparison.md"),
      [
        "# Historical Replay Strategy Comparison",
        "",
        "## Summary",
        "",
        "- Run id: `replay-hypothesis-2-demo`",
        "- Range: `2016-01-04` to `2026-05-29`",
        "- Benchmark: `SPY`",
        "- Champion: `market_drawdown_circuit_breaker:raw-champion`",
        "",
        "## Ranking",
        "",
        "| Rank | Strategy | Net | Benchmark | Delta vs Benchmark | Max DD | Vol | Turnover | Trades | Leakage |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        "| 1 | Market Drawdown Circuit Breaker (`market_drawdown_circuit_breaker:raw-champion`) | 1969.87% | 340.99% | +1628.88% | -36.14% | 29.36% | 38.42 | 43 | pass |",
        "| 32 | Market Drawdown Circuit Breaker (`market_drawdown_circuit_breaker:preferred`) | 1502.44% | 340.99% | +1161.45% | -29.73% | 25.64% | 28.59 | 31 | pass |",
      ].join("\n"),
    );

    const response = await getReplayReports(
      new Request(
        "http://localhost/api/replay-reports?id=replay-hypothesis-2-demo-summary.md",
      ),
    );
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.selectedReport).toMatchObject({
      id: "replay-hypothesis-2-demo-summary.md",
      kind: "comparison",
      runId: "replay-hypothesis-2-demo",
      champion: "market_drawdown_circuit_breaker:raw-champion",
      range: "2016-01-04 to 2026-05-29",
    });
    expect(payload.selectedReport.topMetric).toMatchObject({
      strategy: "market_drawdown_circuit_breaker:preferred",
      delta: "+1161.45%",
      leakage: "pass",
      championDelta: "-467.43%",
      championBaseline: "+1628.88%",
      championRank: "1",
    });
  });

  it("classifies autonomous learning-cycle reports as comparison evidence", async () => {
    reportRoot = await mkdtemp(path.join(tmpdir(), "replay-reports-"));
    process.env.TRADING_APP_REPLAY_REPORT_DIR = reportRoot;
    await writeFile(
      path.join(reportRoot, "learning-cycle-nightly-demo.md"),
      [
        "# Autonomous Learning Cycle Report",
        "",
        "## Summary",
        "",
        "- Run id: `learning-cycle-nightly-demo`",
        "- Range: `2016-01-04` to `2026-06-01`",
        "- Benchmark: `SPY`",
        "- Candidate rows scored: `24`",
        "- Current champion: `market_drawdown_circuit_breaker:champion`",
        "- Recommended challenger: `market_drawdown_circuit_breaker:challenger`",
        "",
        "Autonomous learning completed and ranked candidate strategies.",
        "",
        "## Candidate Scoreboard",
        "",
        "| Rank | Universe | Candidate | Full Delta | Stress Delta | Positive Folds | Min Fold Delta | Avg Fold Delta | Worst DD | Risk Score | Gate Status | Status |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
        "| 1 | `semiconductor-champions` | Market Drawdown Circuit Breaker (`market_drawdown_circuit_breaker:leader`) | +1809.61% | +1691.31% | 3/3 | +19.57% | +179.08% | -46.24% | 24.20 | general evidence only | all folds positive |",
        "| 2 | `semiconductor-champions` | Market Drawdown Circuit Breaker (`market_drawdown_circuit_breaker:champion`) | +1200.00% | +1100.00% | 2/3 | -0.16% | +130.00% | -29.73% | 15.20 | general evidence only | mixed evidence |",
      ].join("\n"),
    );

    const response = await getReplayReports(
      new Request(
        "http://localhost/api/replay-reports?id=learning-cycle-nightly-demo.md",
      ),
    );
    const payload = await response.json();

    expect(response.status).toBe(200);
    expect(payload.selectedReport).toMatchObject({
      id: "learning-cycle-nightly-demo.md",
      kind: "comparison",
      runId: "learning-cycle-nightly-demo",
      benchmark: "SPY",
      champion: "market_drawdown_circuit_breaker:champion",
      range: "2016-01-04 to 2026-06-01",
    });
    expect(payload.selectedReport.topMetric).toMatchObject({
      strategy: "market_drawdown_circuit_breaker:leader",
      delta: "+1809.61%",
      benchmark: "+1691.31%",
      leakage: "n/a",
      championDelta: "+609.61%",
      championBaseline: "+1200.00%",
      championRank: "2",
    });
  });

  it("keeps default and relative replay roots scoped under the Next app data directory", () => {
    expect(replayReportRoot()).toBe(
      path.join(process.cwd(), "data", "research", "replay"),
    );

    process.env.TRADING_APP_REPLAY_REPORT_DIR = "research/replay";

    expect(replayReportRoot()).toBe(
      path.join(process.cwd(), "data", "research/replay"),
    );
  });
});
