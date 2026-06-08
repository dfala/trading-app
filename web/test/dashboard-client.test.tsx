import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardClient } from "@/components/dashboard-client";
import { sampleSnapshot } from "@/test/fixtures";

describe("DashboardClient", () => {
  beforeEach(() => {
    // The dashboard default landing is the Overview screen. Every test in
    // this file was written before Overview existed and asserts on Home /
    // Risk content, so we land directly on #home for those. Tests that
    // exercise Overview itself set their own URL.
    window.history.replaceState(null, "", "/#home");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renders the Home and Risk slices from an operator snapshot", () => {
    render(
      <DashboardClient initialSnapshot={sampleSnapshot} autoRefresh={false} />,
    );

    expect(
      screen.getByRole("heading", {
        name: "Real-money actions are turned off. Your strategy only acts on its schedule.",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Paper Command Center")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /•\s*Home/i })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(
      screen.queryByRole("heading", {
        name: "Your safety net, in one place.",
      }),
    ).not.toBeInTheDocument();

    const nav = within(screen.getByRole("navigation"));
    fireEvent.click(nav.getByRole("button", { name: /Risk/i }));

    expect(
      screen.getByRole("heading", {
        name: "Your safety net, in one place.",
      }),
    ).toBeVisible();
    expect(nav.getByRole("button", { name: /Risk/i })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(screen.getByText("Risk rejected an order")).toBeInTheDocument();
    expect(screen.getAllByText("MAX_ORDERS_PER_DAY").length).toBeGreaterThan(0);
    expect(
      screen.getByRole("button", {
        name: "What does MAX_ORDERS_PER_DAY mean?",
      }),
    ).toBeInTheDocument();
  });

  it("renders live sandbox controls and posts live actions", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/live-sandbox/control") {
        return Response.json({
          accepted: true,
          message: "Live sandbox autonomy armed under the $100 cap.",
        });
      }
      if (url === "/api/snapshot") {
        return Response.json(sampleSnapshot);
      }
      return Response.json({});
    });
    vi.stubGlobal("fetch", fetchMock);
    render(
      <DashboardClient initialSnapshot={sampleSnapshot} autoRefresh={false} />,
    );

    const nav = within(screen.getByRole("navigation"));
    fireEvent.click(nav.getByRole("button", { name: /\$\s*Live/i }));
    fireEvent.click(screen.getByRole("button", { name: "Arm autonomy" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/live-sandbox/control",
        expect.any(Object),
      ),
    );
    const [, init] = fetchMock.mock.calls[0] as unknown as [
      RequestInfo | URL,
      RequestInit,
    ];
    const body = JSON.parse(String(init.body));

    expect(screen.getByText("$100 autonomous pilot with a hard kill switch.")).toBeVisible();
    expect(body.action).toBe("enable_live_autonomy");
  });

  it("does not leak a bare open-order count in the plain-English summary", () => {
    render(
      <DashboardClient initialSnapshot={sampleSnapshot} autoRefresh={false} />,
    );

    const summary = screen
      .getByRole("heading", { name: "A plain-English summary" })
      .closest("article");
    expect(summary).not.toBeNull();
    expect(within(summary as HTMLElement).queryByText(/^0$/)).not.toBeInTheDocument();
  });

  it("renders accepted and rejected daily trade decisions", () => {
    render(
      <DashboardClient initialSnapshot={sampleSnapshot} autoRefresh={false} />,
    );

    const decisionsCard = screen
      .getByRole("heading", { name: "What the strategy did today" })
      .closest("article");
    expect(decisionsCard).not.toBeNull();
    const card = within(decisionsCard as HTMLElement);

    expect(card.getByText("2 reviewed")).toBeVisible();
    expect(card.getByText("SPY FILLED")).toBeVisible();
    expect(card.getByText("BUY 5 · broker submitted · 1 fill(s)")).toBeVisible();
    expect(
      card.getByText(
        "sector_momentum submitted a BUY order for 5 SPY. Risk approved it, broker_submitted=True, and current status is FILLED.",
      ),
    ).toBeVisible();
    expect(card.getByText("SPY BLOCKED")).toBeVisible();
    expect(card.getByText("BUY 1 · not broker submitted")).toBeVisible();
    expect(
      card.queryByText(
        "No trade decisions reviewed yet today. They appear here after the daily runtime cycle scores each candidate.",
      ),
    ).not.toBeInTheDocument();
  });

  it("renders the daily AI review from the grounded daily report summary", () => {
    render(
      <DashboardClient initialSnapshot={sampleSnapshot} autoRefresh={false} />,
    );

    const aiCard = screen
      .getByRole("heading", { name: "AI is a copilot, not an oracle" })
      .closest("article");
    expect(aiCard).not.toBeNull();
    const card = within(aiCard as HTMLElement);

    expect(
      card.getByText(sampleSnapshot.daily_report?.ai_summary?.summary ?? ""),
    ).toBeVisible();
    expect(card.getByText("REVIEWED")).toBeVisible();
    expect(card.getByText("3 sources")).toBeVisible();
    expect(card.getByText("paper · manual approval")).toBeVisible();
    expect(
      card.queryByText(
        "The AI has not published a memo yet today. It is still gathering evidence.",
      ),
    ).not.toBeInTheDocument();
  });

  it("marks the daily AI review pending when the backend has no AI summary", () => {
    const dailyReport = { ...sampleSnapshot.daily_report };
    delete dailyReport.ai_summary;

    render(
      <DashboardClient
        initialSnapshot={{
          ...sampleSnapshot,
          daily_report: dailyReport,
        }}
        autoRefresh={false}
      />,
    );

    const aiCard = screen
      .getByRole("heading", { name: "AI is a copilot, not an oracle" })
      .closest("article");
    expect(aiCard).not.toBeNull();
    const card = within(aiCard as HTMLElement);

    expect(card.getByText("PENDING")).toBeVisible();
    expect(card.getByText("pending")).toBeVisible();
    expect(
      card.getByText(
        "The AI has not published a memo yet today. It is still gathering evidence.",
      ),
    ).toBeVisible();
  });

  it("does not draw a synthetic portfolio curve without recorded history", () => {
    render(
      <DashboardClient initialSnapshot={sampleSnapshot} autoRefresh={false} />,
    );

    const chart = screen.getByTestId("hero-equity-chart");
    expect(chart).toHaveAccessibleName("Paper equity history unavailable");
    expect(screen.getByText("No intraday equity history yet")).toBeVisible();
    expect(screen.getByText("waiting for history in this window")).toBeVisible();
    expect(chart.querySelector("[data-equity-line]")).not.toBeInTheDocument();
  });

  it("renders the portfolio curve from recorded equity history", () => {
    render(
      <DashboardClient
        initialSnapshot={{
          ...sampleSnapshot,
          generated_at: "2026-05-29T15:45:00Z",
          estimated_equity: "10025",
          portfolio_history: [
            {
              as_of: "2026-05-28T20:00:00Z",
              estimated_equity: "9975",
            },
            {
              as_of: "2026-05-29T13:30:00Z",
              estimated_equity: "10000",
            },
            {
              as_of: "2026-05-29T14:30:00Z",
              estimated_equity: "10010",
            },
          ],
        }}
        autoRefresh={false}
      />,
    );

    const chart = screen.getByTestId("hero-equity-chart");
    expect(chart).toHaveAccessibleName(
      "Paper equity curve from recorded dashboard snapshots",
    );
    expect(screen.getByText("+$25.00")).toBeVisible();
    expect(screen.getByText("+0.25% today")).toBeVisible();
    expect(screen.getByText("since first recorded snapshot today")).toBeVisible();
    expect(chart.querySelector("[data-equity-line]")).toBeInTheDocument();
  });

  it("expands the equity window when switching to a longer period", async () => {
    render(
      <DashboardClient
        initialSnapshot={{
          ...sampleSnapshot,
          generated_at: "2026-05-29T15:45:00Z",
          estimated_equity: "10025",
          portfolio_history: [
            { as_of: "2026-05-28T20:00:00Z", estimated_equity: "9975" },
            { as_of: "2026-05-29T13:30:00Z", estimated_equity: "10000" },
            { as_of: "2026-05-29T14:30:00Z", estimated_equity: "10010" },
          ],
        }}
        autoRefresh={false}
      />,
    );

    // 1D defaults to today only — baseline is the first point from today.
    expect(screen.getByText("+0.25% today")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "1W", pressed: false }));

    // 1W includes yesterday's $9,975 baseline, so the % move is larger.
    expect(
      screen.getByText("+0.50% this week"),
    ).toBeVisible();
    expect(
      screen.getByText("since first recorded snapshot this week"),
    ).toBeVisible();
  });

  it("opens every Python dashboard screen as a distinct Next tab", () => {
    render(
      <DashboardClient initialSnapshot={sampleSnapshot} autoRefresh={false} />,
    );

    const screens = [
      {
        button: /Models/i,
        heading: "What's trading on your behalf - and why.",
      },
      {
        button: /Paper/i,
        heading: "Holdings, fills, and the reconciliation evidence behind them.",
      },
      {
        button: /Risk/i,
        heading: "Your safety net, in one place.",
      },
      {
        button: /Research/i,
        heading: "Where new strategies are tested before they go anywhere.",
      },
      {
        button: /AI Review/i,
        heading: "Pending operator review",
      },
      {
        button: /Learn/i,
        heading: "How to read this dashboard.",
      },
    ];

    const nav = within(screen.getByRole("navigation"));
    for (const item of screens) {
      fireEvent.click(nav.getByRole("button", { name: item.button }));
      expect(
        screen.getByRole("heading", { name: item.heading }),
      ).toBeVisible();
      expect(nav.getByRole("button", { name: item.button })).toHaveAttribute(
        "aria-current",
        "page",
      );
    }
  });

  it("renders the top 30 autonomous leaderboard rows on Overview", () => {
    window.history.replaceState(null, "", "/#overview");
    const entries = Array.from({ length: 31 }, (_, index) => {
      const rank = index + 1;
      return {
        rank,
        seen_count: rank,
        latest_run_id: `run-${rank}`,
        universe_id: "test-universe",
        model_key: `test_strategy_${rank}:v${rank}`,
        strategy_name: `Test Strategy ${rank}`,
        full_delta: rank / 10,
        net_total_return: rank / 5,
        benchmark_total_return: rank / 10,
        stress_delta: rank / 20,
        min_fold_delta: 0.1,
        average_fold_delta: 0.2,
        worst_drawdown: -0.15,
        risk_adjusted_score: rank,
        positive_folds: 3,
        fold_count: 3,
        gate_status: "risk gates incomplete",
        status: "all folds positive",
      };
    });

    render(
      <DashboardClient
        initialSnapshot={{
          ...sampleSnapshot,
          model_cards: [
            {
              label: "Champion",
              strategy_id: "monthly_sector_momentum",
              version: "1.0.0",
              state: "paper",
              score: 1.23,
              detail: "Market-open paper authority only",
              evidence: {
                model_key: "monthly_sector_momentum:1.0.0",
                source: "test",
                net_total_return: 0.2,
                benchmark_total_return: 0.1,
                excess_return: 0.1,
                worst_drawdown: -0.12,
                risk_adjusted_score: 1.23,
              },
            },
          ],
          autonomous_learning: {
            ...sampleSnapshot.autonomous_learning,
            leaderboard: {
              generated_at: "2026-06-03T15:00:00Z",
              entry_count: entries.length,
              entries,
              summary: "Test leaderboard.",
            },
          },
        }}
        autoRefresh={false}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Top 30 model rankings" }),
    ).toBeVisible();
    expect(screen.getByText("CURRENT CHAMPION")).toBeVisible();
    expect(screen.getByText("LIVE")).toBeVisible();
    expect(screen.getByText("monthly_sector_momentum")).toBeVisible();
    expect(screen.getByText("test_strategy_30")).toBeVisible();
    expect(screen.getByText("v30")).toBeVisible();
    expect(screen.getByText("+600.00%")).toBeVisible();
    expect(screen.queryByText("test_strategy_31")).not.toBeInTheDocument();
  });

  it("opens a model performance page from a leaderboard row", async () => {
    window.history.replaceState(null, "", "/#overview");
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).startsWith("/api/model-performance")) {
        return Response.json({
          model_key: "test_strategy_1:v1",
          strategy_id: "test_strategy_1",
          version: "v1",
          strategy_name: "Test Strategy 1",
          universe_id: "test-universe",
          benchmark: "SPY",
          data_feed: "SIP",
          decision_frequency: "month_start",
          execution_price: "close",
          start_date: "2020-01-02",
          end_date: "2020-01-06",
          generated_at: "2026-06-03T16:00:00Z",
          source_report: "data/research/replay/test-report.json",
          source_run_id: "test-run",
          source_rank: 1,
          source_research_score: 2.5,
          window_policy: "longest stored full-period comparison for this model",
          available_window_count: 2,
          late_entry_risk: true,
          late_entry_risk_summary:
            "Latest 63 trading days account for 51.5% of full-period excess return.",
          recent_windows: [
            {
              trading_days: 21,
              start_date: "2019-12-05",
              end_date: "2020-01-06",
              model_return_delta: 0.04,
              benchmark_return_delta: 0.01,
              excess_return_delta: 0.03,
              excess_contribution_share: 0.2,
              late_entry_risk: false,
            },
            {
              trading_days: 63,
              start_date: "2019-10-07",
              end_date: "2020-01-06",
              model_return_delta: 0.12,
              benchmark_return_delta: 0.02,
              excess_return_delta: 0.10,
              excess_contribution_share: 0.515,
              late_entry_risk: true,
            },
          ],
          metrics: {
            net_total_return: 0.2,
            benchmark_total_return: 0.05,
            excess_return: 0.15,
            annualized_return: 0.1,
            annualized_volatility: 0.2,
            max_drawdown: -0.1,
            turnover: 1.2,
            trade_count: 3,
            decision_count: 2,
          },
          points: [
            {
              trading_date: "2020-01-02",
              model_equity: 100000,
              benchmark_equity: 100000,
              model_return: 0,
              benchmark_return: 0,
              excess_return: 0,
            },
            {
              trading_date: "2020-01-03",
              model_equity: 110000,
              benchmark_equity: 102000,
              model_return: 0.1,
              benchmark_return: 0.02,
              excess_return: 0.08,
            },
            {
              trading_date: "2020-01-06",
              model_equity: 120000,
              benchmark_equity: 105000,
              model_return: 0.2,
              benchmark_return: 0.05,
              excess_return: 0.15,
            },
          ],
        });
      }
      return Response.json({});
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <DashboardClient
        initialSnapshot={{
          ...sampleSnapshot,
          autonomous_learning: {
            ...sampleSnapshot.autonomous_learning,
            leaderboard: {
              generated_at: "2026-06-03T15:00:00Z",
              entry_count: 1,
              entries: [
                {
                  rank: 1,
                  seen_count: 1,
                  latest_run_id: "run-1",
                  universe_id: "test-universe",
                  model_key: "test_strategy_1:v1",
                  strategy_name: "Test Strategy 1",
                  full_delta: 0.15,
                  net_total_return: 0.2,
                  benchmark_total_return: 0.05,
                  stress_delta: 0.12,
                  min_fold_delta: 0.1,
                  average_fold_delta: 0.2,
                  worst_drawdown: -0.1,
                  risk_adjusted_score: 2.5,
                  positive_folds: 3,
                  fold_count: 3,
                  gate_status: "risk gates passed",
                  status: "all folds positive",
                },
              ],
              summary: "Test leaderboard.",
            },
          },
        }}
        autoRefresh={false}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: /test_strategy_1v1/i }),
    );

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "test_strategy_1:v1" }),
      ).toBeVisible();
    });
    expect(String(fetchMock.mock.calls[0][0])).toBe(
      "/api/model-performance?model_key=test_strategy_1%3Av1&universe_id=test-universe",
    );
    expect(screen.getByText("Return curve over time")).toBeVisible();
    expect(screen.getAllByText("+20.00%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("+5.00%").length).toBeGreaterThan(0);
    expect(screen.getByText("month start")).toBeVisible();
    expect(screen.getByText("Late-entry review")).toBeVisible();
    expect(
      screen.getByText(
        "Latest 63 trading days account for 51.5% of full-period excess return.",
      ),
    ).toBeVisible();
    expect(screen.getByText("Late review")).toBeVisible();
    expect(document.querySelector("[data-model-line]")).toBeInTheDocument();
    expect(document.querySelector("[data-market-line]")).toBeInTheDocument();
  });

  it("uses the Python Learn destinations for topic rows", () => {
    render(
      <DashboardClient initialSnapshot={sampleSnapshot} autoRefresh={false} />,
    );

    const nav = within(screen.getByRole("navigation"));
    fireEvent.click(nav.getByRole("button", { name: /Learn/i }));

    expect(
      screen.getByRole("link", { name: "Open Paper Trading: Paper Boundary" }),
    ).toHaveAttribute("href", "#paper");
    expect(
      screen.getByRole("link", { name: "Open Risk: Drawdown" }),
    ).toHaveAttribute("href", "#risk");
    expect(
      screen.getByRole("link", { name: "Open Models: Signal" }),
    ).toHaveAttribute("href", "#strategies");
    expect(
      screen.getByRole("link", { name: "Open AI Review: AI confidence" }),
    ).toHaveAttribute("href", "#ai");
    expect(
      screen.getByRole("link", { name: "Open Research Lab: Nightly Learning" }),
    ).toHaveAttribute("href", "#research");
  });

  it("supports glossary, tour, shortcuts, and command palette navigation", () => {
    render(
      <DashboardClient initialSnapshot={sampleSnapshot} autoRefresh={false} />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: /open glossary for this screen/i }),
    );
    expect(screen.getByRole("heading", { name: "Command Center" })).toBeVisible();
    expect(
      within(screen.getByLabelText("Glossary for this screen")).getByText(
        "Paper Portfolio",
      ),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /close glossary panel/i }));
    fireEvent.click(screen.getByRole("button", { name: /tour/i }));
    expect(screen.getByRole("heading", { name: "Your simulated portfolio" })).toBeVisible();

    fireEvent.keyDown(document, { key: "Escape" });
    fireEvent.keyDown(document, { key: "?" });
    expect(screen.getByRole("heading", { name: "Keyboard shortcuts" })).toBeVisible();

    fireEvent.keyDown(document, { key: "Escape" });
    fireEvent.keyDown(document, { key: "/", code: "Slash" });
    fireEvent.change(screen.getByPlaceholderText(/jump to a screen/i), {
      target: { value: "Paper Trading" },
    });
    fireEvent.click(screen.getAllByRole("option", { name: /Paper Trading/i })[0]);
    expect(
      screen.getByRole("heading", {
        name: "Holdings, fills, and the reconciliation evidence behind them.",
      }),
    ).toBeVisible();
  });

  it("loads historical replay markdown inside the Research screen", async () => {
    const fetchMock = vi.fn(async () =>
      Response.json({
        reports: [
          {
            id: "demo-comparison.md",
            title: "Historical Replay Strategy Comparison",
            fileName: "demo-comparison.md",
            relativePath: "demo-comparison.md",
            kind: "comparison",
            updatedAt: "2026-06-01T17:00:00Z",
            sizeBytes: 512,
            runId: "demo-run",
            range: "2016-01-04 to 2026-05-29",
            benchmark: "SPY",
            champion: "demo:1",
            strategyCount: 2,
            skippedCount: 0,
            summary: "Top strategy demo:1 beat the benchmark by +5.00%.",
            tags: ["Comparison", "SIP"],
            topMetric: {
              strategy: "demo:1",
              net: "15.00%",
              benchmark: "10.00%",
              delta: "+5.00%",
              leakage: "pass",
            },
          },
        ],
        selectedId: "demo-comparison.md",
        selectedReport: {
          id: "demo-comparison.md",
          title: "Historical Replay Strategy Comparison",
          fileName: "demo-comparison.md",
          relativePath: "demo-comparison.md",
          kind: "comparison",
          updatedAt: "2026-06-01T17:00:00Z",
          sizeBytes: 512,
          runId: "demo-run",
          range: "2016-01-04 to 2026-05-29",
          benchmark: "SPY",
          champion: "demo:1",
          strategyCount: 2,
          skippedCount: 0,
          summary: "Top strategy demo:1 beat the benchmark by +5.00%.",
          tags: ["Comparison", "SIP"],
          topMetric: {
            strategy: "demo:1",
            net: "15.00%",
            benchmark: "10.00%",
            delta: "+5.00%",
            leakage: "pass",
          },
        },
        content: [
          "# Historical Replay Strategy Comparison",
          "",
          "## Ranking",
          "",
          "| Rank | Strategy | Net | Benchmark | Delta vs Benchmark | Leakage |",
          "| ---: | --- | ---: | ---: | ---: | --- |",
          "| 1 | Demo Strategy (`demo:1`) | 15.00% | 10.00% | +5.00% | pass |",
        ].join("\n"),
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <DashboardClient initialSnapshot={sampleSnapshot} autoRefresh={false} />,
    );

    const nav = within(screen.getByRole("navigation"));
    fireEvent.click(nav.getByRole("button", { name: /Research/i }));

    expect(await screen.findByText("Historical replay library")).toBeVisible();
    expect(screen.getByText("Autonomous cycle · completed")).toBeVisible();
    expect(screen.getByText("Running")).toBeVisible();
    expect(
      screen.getByLabelText("Autonomous learning service is running"),
    ).toBeVisible();
    expect(screen.getByText("Sector Etf Momentum Grid")).toBeVisible();
    expect(screen.getByText("learning-cycle-nightly-demo")).toBeVisible();
    expect((await screen.findAllByText("demo-run")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("+5.00%").length).toBeGreaterThan(0);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/replay-reports",
      expect.objectContaining({ cache: "no-store" }),
    );
  });

  it("filters reports by flexible model-key text from indexed report content", async () => {
    const fetchMock = vi.fn(async () =>
      Response.json({
        reports: [
          {
            id: "semi-sleeve.md",
            title: "Historical Replay Strategy Comparison",
            fileName: "semi-sleeve.md",
            relativePath: "runs/semi-sleeve.md",
            kind: "comparison",
            updatedAt: "2026-06-01T17:00:00Z",
            sizeBytes: 512,
            runId: "semi-run",
            range: "2016-01-04 to 2026-05-29",
            benchmark: "SPY",
            champion: "risk_managed_semiconductor:vol-smh-v63-t020-off-cash",
            strategyCount: 2,
            skippedCount: 0,
            summary: "Top strategy beat the benchmark.",
            tags: ["Comparison", "SIP"],
            topMetric: {
              strategy: "Risk Managed Semiconductor",
              net: "888.29%",
              benchmark: "340.99%",
              delta: "+547.30%",
              maxDrawdown: "-28.00%",
              championDelta: "+0.00%",
              leakage: "pass",
            },
            searchText:
              "risk_managed_semiconductor:vol-smh-v63-t020-off-cash liquid-risk-on",
          },
          {
            id: "semi-sleeve-repeat.md",
            title: "Historical Replay Strategy Comparison",
            fileName: "semi-sleeve-repeat.md",
            relativePath: "runs/semi-sleeve-repeat.md",
            kind: "comparison",
            updatedAt: "2026-06-02T17:00:00Z",
            sizeBytes: 512,
            runId: "semi-run-repeat",
            range: "2016-01-04 to 2026-05-29",
            benchmark: "SPY",
            champion: "risk_managed_semiconductor:vol-smh-v63-t020-off-cash",
            strategyCount: 2,
            skippedCount: 0,
            summary: "Repeat report with identical top metric.",
            tags: ["Comparison", "SIP"],
            topMetric: {
              strategy: "Risk Managed Semiconductor",
              net: "888.29%",
              benchmark: "340.99%",
              delta: "+547.30%",
              maxDrawdown: "-28.00%",
              championDelta: "+0.00%",
              leakage: "pass",
            },
            searchText:
              "risk_managed_semiconductor:vol-smh-v63-t020-off-cash repeat",
          },
          {
            id: "broad-sector.md",
            title: "Historical Replay Strategy Comparison",
            fileName: "broad-sector.md",
            relativePath: "runs/broad-sector.md",
            kind: "comparison",
            updatedAt: "2026-05-30T17:00:00Z",
            sizeBytes: 512,
            runId: "broad-run",
            range: "2016-01-04 to 2026-05-29",
            benchmark: "SPY",
            champion: "sector_etf_momentum:grid-l63-n3",
            strategyCount: 2,
            skippedCount: 0,
            summary: "Broad sector model comparison.",
            tags: ["Comparison", "IEX"],
            topMetric: {
              strategy: "Sector ETF Momentum",
              net: "140.00%",
              benchmark: "120.00%",
              delta: "+20.00%",
              maxDrawdown: "-18.00%",
              championDelta: "-408.00%",
              leakage: "pass",
            },
            searchText: "sector_etf_momentum:grid-l63-n3 broad portfolio",
          },
          {
            id: "notes-only.md",
            title: "Research Notes",
            fileName: "notes-only.md",
            relativePath: "runs/notes-only.md",
            kind: "other",
            updatedAt: "2026-05-29T17:00:00Z",
            sizeBytes: 128,
            summary: "A report with no parsed ranking metric.",
            tags: ["Notes"],
            searchText: "research notes without ranking metrics",
          },
        ],
        selectedId: "semi-sleeve.md",
        selectedReport: null,
        content: "",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <DashboardClient initialSnapshot={sampleSnapshot} autoRefresh={false} />,
    );

    const nav = within(screen.getByRole("navigation"));
    fireEvent.click(nav.getByRole("button", { name: /Reports/i }));

    const search = await screen.findByLabelText("Search reports");
    const reportsScreen = screen
      .getByText("Every research replay, ranked.")
      .closest("section");
    expect(reportsScreen).not.toBeNull();
    const reports = within(reportsScreen as HTMLElement);
    expect(reports.getByText("Risk Managed Semiconductor")).toBeVisible();
    expect(reports.getByText("Sector ETF Momentum")).toBeVisible();
    expect(
      reports.getByText(
        "2 ranked rows from 4 reports; 1 duplicate row collapsed; 1 unranked report",
      ),
    ).toBeVisible();
    expect(reports.getByText(/2 replay files/)).toBeVisible();

    fireEvent.change(search, { target: { value: "v63 t020" } });

    await waitFor(() => {
      expect(reports.queryByText("Sector ETF Momentum")).not.toBeInTheDocument();
    });
    expect(reports.getByText("Risk Managed Semiconductor")).toBeVisible();
    expect(
      reports.getByText(
        "1 ranked row from 2 matching reports; 1 duplicate row collapsed",
      ),
    ).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "Clear" }));

    await waitFor(() => {
      expect(reports.getByText("Sector ETF Momentum")).toBeVisible();
    });
    expect(reports.getByText("Risk Managed Semiconductor")).toBeVisible();
  });

  it("treats exact model-key searches as visible ranked-row matches", async () => {
    const targetModel = "benchmark_relative_strength_etf:grid-l252-t21-n2";
    const otherTopModel = "benchmark_relative_strength_etf:grid-l126-t63-n1";
    const fetchMock = vi.fn(async () =>
      Response.json({
        reports: [
          {
            id: "mentions-target.md",
            title: "Historical Replay Strategy Comparison",
            fileName: "mentions-target.md",
            relativePath: "runs/mentions-target.md",
            kind: "comparison",
            updatedAt: "2026-06-03T17:00:00Z",
            sizeBytes: 512,
            runId: "mentions-target",
            range: "2016-01-04 to 2026-06-02",
            benchmark: "SPY",
            champion: otherTopModel,
            strategyCount: 2,
            skippedCount: 0,
            summary: "The requested model appears lower in this report.",
            tags: ["Comparison", "SIP"],
            topMetric: {
              strategy: otherTopModel,
              net: "1521.71%",
              benchmark: "340.99%",
              delta: "+1180.72%",
              maxDrawdown: "-28.95%",
              championDelta: "+0.00%",
              leakage: "pass",
            },
            searchText: `${otherTopModel} ${targetModel}`,
          },
          {
            id: "target-top.md",
            title: "Historical Replay Strategy Comparison",
            fileName: "target-top.md",
            relativePath: "runs/target-top.md",
            kind: "comparison",
            updatedAt: "2026-06-02T17:00:00Z",
            sizeBytes: 512,
            runId: "target-top",
            range: "2016-01-04 to 2026-06-01",
            universeId: "macro-defensive",
            benchmark: "SPY",
            champion: targetModel,
            strategyCount: 2,
            skippedCount: 0,
            summary: "The requested model is the displayed ranked row.",
            tags: ["Comparison", "SIP"],
            topMetric: {
              strategy: targetModel,
              net: "483.49%",
              benchmark: "340.99%",
              delta: "+142.50%",
              maxDrawdown: "-18.96%",
              championDelta: "+0.00%",
              leakage: "pass",
            },
            searchText: targetModel,
          },
        ],
        selectedId: "mentions-target.md",
        selectedReport: null,
        content: "",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <DashboardClient initialSnapshot={sampleSnapshot} autoRefresh={false} />,
    );

    const nav = within(screen.getByRole("navigation"));
    fireEvent.click(nav.getByRole("button", { name: /Reports/i }));

    const search = await screen.findByLabelText("Search reports");
    fireEvent.change(search, { target: { value: targetModel } });

    const reportsScreen = screen
      .getByText("Every research replay, ranked.")
      .closest("section");
    expect(reportsScreen).not.toBeNull();
    const reports = within(reportsScreen as HTMLElement);

    await waitFor(() => {
      expect(reports.queryByText(otherTopModel)).not.toBeInTheDocument();
    });
    expect(reports.getByText(targetModel)).toBeVisible();
    expect(reports.queryByText("CHAMPION")).not.toBeInTheDocument();
    expect(
      reports.getByText("1 ranked row from 1 matching report"),
    ).toBeVisible();
  });

  it("opens the model graph when clicking a Reports result with a model key", async () => {
    const targetModel = "benchmark_relative_strength_etf:grid-l252-t21-n2";
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.startsWith("/api/model-performance")) {
        return Response.json({
          model_key: targetModel,
          strategy_id: "benchmark_relative_strength_etf",
          version: "grid-l252-t21-n2",
          strategy_name: "Benchmark Relative Strength ETF",
          universe_id: "macro-defensive",
          benchmark: "SPY",
          data_feed: "SIP",
          decision_frequency: "month_start",
          execution_price: "close",
          start_date: "2020-01-02",
          end_date: "2020-01-03",
          generated_at: "2026-06-03T16:00:00Z",
          source_report: "data/research/replay/report.json",
          source_run_id: "report-run",
          source_rank: 1,
          source_research_score: 2.5,
          window_policy: "longest stored full-period comparison for this model",
          available_window_count: 1,
          metrics: {
            net_total_return: 0.2,
            benchmark_total_return: 0.05,
            excess_return: 0.15,
            annualized_return: 0.1,
            annualized_volatility: 0.2,
            max_drawdown: -0.1,
            turnover: 1.2,
            trade_count: 3,
            decision_count: 2,
          },
          points: [
            {
              trading_date: "2020-01-02",
              model_equity: 100000,
              benchmark_equity: 100000,
              model_return: 0,
              benchmark_return: 0,
              excess_return: 0,
            },
            {
              trading_date: "2020-01-03",
              model_equity: 120000,
              benchmark_equity: 105000,
              model_return: 0.2,
              benchmark_return: 0.05,
              excess_return: 0.15,
            },
          ],
        });
      }
      return Response.json({
        reports: [
          {
            id: "target-top.md",
            title: "Historical Replay Strategy Comparison",
            fileName: "target-top.md",
            relativePath: "runs/target-top.md",
            kind: "comparison",
            updatedAt: "2026-06-02T17:00:00Z",
            sizeBytes: 512,
            runId: "target-top",
            range: "2016-01-04 to 2026-06-01",
            universeId: "macro-defensive",
            benchmark: "SPY",
            champion: targetModel,
            strategyCount: 2,
            skippedCount: 0,
            summary: "The requested model is the displayed ranked row.",
            tags: ["Comparison", "SIP"],
            topMetric: {
              strategy: targetModel,
              net: "483.49%",
              benchmark: "340.99%",
              delta: "+142.50%",
              maxDrawdown: "-18.96%",
              championDelta: "+0.00%",
              leakage: "pass",
            },
            searchText: targetModel,
          },
        ],
        selectedId: "target-top.md",
        selectedReport: null,
        content: "",
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(
      <DashboardClient initialSnapshot={sampleSnapshot} autoRefresh={false} />,
    );

    const nav = within(screen.getByRole("navigation"));
    fireEvent.click(nav.getByRole("button", { name: /Reports/i }));

    const row = await screen.findByRole("button", {
      name: `Open model graph for ${targetModel}`,
    });
    expect(row).toHaveTextContent("macro-defensive");
    fireEvent.click(row);

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: targetModel }),
      ).toBeVisible();
    });
    expect(String(fetchMock.mock.calls.at(-1)?.[0])).toBe(
      `/api/model-performance?model_key=${encodeURIComponent(targetModel)}&universe_id=macro-defensive`,
    );
    expect(window.location.hash).toBe(
      `#model?model_key=${encodeURIComponent(targetModel)}&universe_id=macro-defensive`,
    );
    expect(screen.getByText("Return curve over time")).toBeVisible();
  });

  it("sends operator controls through the Next proxy route", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        Response.json({
          status: "accepted",
          message: "Paper trading is paused.",
          control_state: {
            ...sampleSnapshot.control_state,
            paused: true,
          },
        }),
      )
      .mockResolvedValueOnce(Response.json(sampleSnapshot));
    vi.stubGlobal("fetch", fetchMock);

    render(
      <DashboardClient initialSnapshot={sampleSnapshot} autoRefresh={false} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Risk/i }));
    fireEvent.click(screen.getByRole("button", { name: /pause trading/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/control",
        expect.objectContaining({
          method: "POST",
        }),
      );
    });
    const controlBody = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(controlBody.action).toBe("pause_runtime");
    expect(controlBody.requested_by).toBe("next-dashboard");
    expect(await screen.findByText("Paper trading is paused.")).toBeVisible();
  });
});
