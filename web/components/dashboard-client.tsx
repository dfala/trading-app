"use client";

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";

import type {
  ControlResult,
  DashboardAlert,
  DashboardMetric,
  DashboardModelCard,
  DashboardModelEvidence,
  DashboardSnapshot,
  Fill,
  LiveSandboxControlAction,
  LiveSandboxControlResult,
  ModelComparison,
  ModelPerformanceResponse,
  ModelStrategyProfile,
  NightlyLearningRun,
  OperatorControlAction,
  Position,
  ReplayReportResponse,
  ReplayReportSummary,
  RejectedSignal,
  ShadowChallengerObservation,
  ShadowHistoryResponse,
  ShadowModelSeries,
  StrategyDefinition,
  TradeExplanation,
} from "@/lib/types";
import { ReplayReportsPanel } from "@/components/replay-reports-panel";
import { GLOSSARY, SCREEN_LABELS, TOPICS, deepLinkFor } from "@/lib/glossary";

type ScreenKey =
  | "overview"
  | "home"
  | "strategies"
  | "paper"
  | "live"
  | "risk"
  | "research"
  | "reports"
  | "ai"
  | "learn"
  | "model";

type ThemePref = "light" | "dark" | "system";
const THEME_PREFS: readonly ThemePref[] = ["light", "dark", "system"];

function isThemePref(value: unknown): value is ThemePref {
  return value === "light" || value === "dark" || value === "system";
}

function resolveTheme(pref: ThemePref): "light" | "dark" {
  if (pref === "light" || pref === "dark") return pref;
  if (
    typeof window !== "undefined" &&
    window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: light)").matches
  ) {
    return "light";
  }
  return "dark";
}

type DashboardClientProps = {
  initialSnapshot?: DashboardSnapshot;
  autoRefresh?: boolean;
  refreshIntervalMs?: number;
};

type LiveSandboxHistoryPoint = {
  asOf: string;
  timestamp: number;
  equity: number;
  deployed: number;
  cash: number;
};

type ModelSelection = {
  modelKey: string;
  universeId?: string;
};

const CONTROL_REASON = "Next.js operator dashboard";
const NAV_ITEMS = [
  ["live", "Live", "$"],
  ["overview", "Overview", "O"],
  ["home", "Home", "•"],
  ["strategies", "Models", "M"],
  ["paper", "Paper", "P"],
  ["risk", "Risk", "R"],
  ["research", "Research", "L"],
  ["reports", "Reports", "T"],
  ["ai", "AI Review", "AI"],
  ["learn", "Learn", "?"],
] as const;
const SCREEN_TITLES: Record<ScreenKey, string> = {
  overview: "Overview",
  home: "Command Center",
  strategies: "Models",
  paper: "Paper Trading",
  live: "Live Sandbox",
  risk: "Risk",
  research: "Research Lab",
  reports: "Reports",
  ai: "AI Review",
  learn: "Learn",
  model: "Model Detail",
};

const GOTO_KEYS: Record<string, ScreenKey> = {
  o: "overview",
  h: "home",
  m: "strategies",
  p: "paper",
  "$": "live",
  r: "risk",
  l: "research",
  t: "reports",
  a: "ai",
  "?": "learn",
};
const RULE_GLOSSARY_KEYS: Record<string, string> = {
  MAX_ORDERS_PER_DAY: "rule_max_orders_per_day",
};

export function DashboardClient({
  initialSnapshot,
  autoRefresh = true,
  refreshIntervalMs = 5000,
}: DashboardClientProps) {
  const [snapshot, setSnapshot] = useState<DashboardSnapshot | undefined>(
    initialSnapshot,
  );
  const [loading, setLoading] = useState(!initialSnapshot);
  const [error, setError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] =
    useState<OperatorControlAction | null>(null);
  const [pendingLiveAction, setPendingLiveAction] =
    useState<LiveSandboxControlAction | null>(null);
  const [controlMessage, setControlMessage] = useState<string | null>(null);
  const [activeScreen, setActiveScreen] = useState<ScreenKey>("live");
  const [liveHistory, setLiveHistory] = useState<LiveSandboxHistoryPoint[]>([]);
  const [vocab, setVocab] = useState<"plain" | "technical">("plain");
  const [theme, setTheme] = useState<ThemePref>("system");
  const [tourOpen, setTourOpen] = useState(false);
  const [tourStep, setTourStep] = useState(0);
  const [whatsThisOpen, setWhatsThisOpen] = useState(false);
  const [commandOpen, setCommandOpen] = useState(false);
  const [commandQuery, setCommandQuery] = useState("");
  const [commandIndex, setCommandIndex] = useState(0);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [gotoPrefix, setGotoPrefix] = useState(false);
  const [replayReports, setReplayReports] = useState<ReplayReportSummary[]>(
    [],
  );
  const [selectedReplayReportId, setSelectedReplayReportId] = useState<
    string | undefined
  >(undefined);
  const [selectedReplayReport, setSelectedReplayReport] =
    useState<ReplayReportSummary>();
  const [replayReportContent, setReplayReportContent] = useState("");
  const [replayReportsLoading, setReplayReportsLoading] = useState(false);
  const [replayReportsError, setReplayReportsError] = useState<string | null>(
    null,
  );
  const [selectedModel, setSelectedModel] = useState<ModelSelection>();
  const [modelPerformance, setModelPerformance] =
    useState<ModelPerformanceResponse>();
  const [modelPerformanceLoading, setModelPerformanceLoading] = useState(false);
  const [modelPerformanceError, setModelPerformanceError] = useState<
    string | null
  >(null);
  const modelPerformanceRequestId = useRef(0);

  const commandResults = useMemo(
    () => buildCommandResults(commandQuery, snapshot),
    [commandQuery, snapshot],
  );

  const refreshSnapshot = useCallback(async () => {
    try {
      const response = await fetch("/api/snapshot", { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`Snapshot request failed with ${response.status}`);
      }
      setSnapshot((await response.json()) as DashboardSnapshot);
      setError(null);
    } catch (loadError) {
      const message =
        loadError instanceof Error ? loadError.message : "Snapshot unavailable";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadReplayReports = useCallback(async (id?: string) => {
    setReplayReportsLoading(true);
    try {
      const query = id ? `?id=${encodeURIComponent(id)}` : "";
      const response = await fetch(`/api/replay-reports${query}`, {
        cache: "no-store",
      });
      const payload = (await response.json()) as ReplayReportResponse;
      if (!response.ok) {
        throw new Error(
          payload.error ?? `Replay reports failed with ${response.status}`,
        );
      }
      setReplayReports(payload.reports);
      setSelectedReplayReportId(payload.selectedId);
      setSelectedReplayReport(payload.selectedReport);
      setReplayReportContent(payload.content ?? "");
      setReplayReportsError(null);
    } catch (loadError) {
      const message =
        loadError instanceof Error
          ? loadError.message
          : "Replay reports unavailable";
      setReplayReportsError(message);
    } finally {
      setReplayReportsLoading(false);
    }
  }, []);

  const loadModelPerformance = useCallback(async (selection: ModelSelection) => {
    const requestId = modelPerformanceRequestId.current + 1;
    modelPerformanceRequestId.current = requestId;
    setModelPerformanceLoading(true);
    setModelPerformanceError(null);
    try {
      const params = new URLSearchParams({ model_key: selection.modelKey });
      if (selection.universeId) {
        params.set("universe_id", selection.universeId);
      }
      const response = await fetch(`/api/model-performance?${params.toString()}`, {
        cache: "no-store",
      });
      const payload = (await response.json()) as ModelPerformanceResponse;
      if (!response.ok) {
        throw new Error(
          payload.error ?? `Model performance failed with ${response.status}`,
        );
      }
      if (requestId !== modelPerformanceRequestId.current) {
        return;
      }
      setModelPerformance(payload);
      setModelPerformanceError(null);
    } catch (loadError) {
      if (requestId !== modelPerformanceRequestId.current) {
        return;
      }
      const message =
        loadError instanceof Error
          ? loadError.message
          : "Model performance unavailable";
      setModelPerformance(undefined);
      setModelPerformanceError(message);
    } finally {
      if (requestId === modelPerformanceRequestId.current) {
        setModelPerformanceLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    const syncHashScreen = () => {
      const modelSelection = modelSelectionFromHash(window.location.hash);
      if (modelSelection) {
        setSelectedModel(modelSelection);
        setActiveScreen("model");
        void loadModelPerformance(modelSelection);
        return;
      }
      const nextScreen = screenFromHash(window.location.hash);
      if (nextScreen) {
        setActiveScreen(nextScreen);
      }
    };

    syncHashScreen();
    window.addEventListener("hashchange", syncHashScreen);
    return () => window.removeEventListener("hashchange", syncHashScreen);
  }, [loadModelPerformance]);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem("dashVocab");
      if (stored === "technical" || stored === "plain") {
        setVocab(stored);
      }
    } catch {
      // Ignore private-mode localStorage failures.
    }
  }, []);

  useEffect(() => {
    document.documentElement.dataset.vocab = vocab;
    try {
      window.localStorage.setItem("dashVocab", vocab);
    } catch {
      // Ignore private-mode localStorage failures.
    }
  }, [vocab]);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem("dashTheme");
      if (isThemePref(stored)) {
        setTheme(stored);
      }
    } catch {
      // Ignore private-mode localStorage failures.
    }
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.themePref = theme;
    root.dataset.theme = resolveTheme(theme);
    try {
      window.localStorage.setItem("dashTheme", theme);
    } catch {
      // Ignore private-mode localStorage failures.
    }
    if (theme !== "system" || typeof window.matchMedia !== "function") {
      return;
    }
    const mql = window.matchMedia("(prefers-color-scheme: light)");
    const sync = () => {
      root.dataset.theme = mql.matches ? "light" : "dark";
    };
    if (mql.addEventListener) mql.addEventListener("change", sync);
    else mql.addListener(sync);
    return () => {
      if (mql.removeEventListener) mql.removeEventListener("change", sync);
      else mql.removeListener(sync);
    };
  }, [theme]);

  useEffect(() => {
    if (!initialSnapshot) {
      void refreshSnapshot();
    }
    if (!autoRefresh) {
      return;
    }
    const interval = window.setInterval(refreshSnapshot, refreshIntervalMs);
    return () => window.clearInterval(interval);
  }, [autoRefresh, initialSnapshot, refreshIntervalMs, refreshSnapshot]);

  useEffect(() => {
    const point = liveSandboxHistoryPoint(snapshot);
    if (!point) {
      return;
    }
    setLiveHistory((history) => {
      const next = [
        ...history.filter((item) => item.timestamp !== point.timestamp),
        point,
      ].sort((left, right) => left.timestamp - right.timestamp);
      return next.slice(-240);
    });
  }, [snapshot]);

  useEffect(() => {
    if (
      (activeScreen === "research" || activeScreen === "reports") &&
      replayReports.length === 0 &&
      !replayReportsLoading &&
      !replayReportsError
    ) {
      void loadReplayReports();
    }
  }, [
    activeScreen,
    loadReplayReports,
    replayReports.length,
    replayReportsError,
    replayReportsLoading,
  ]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const isTyping =
        target?.tagName === "INPUT" ||
        target?.tagName === "TEXTAREA" ||
        target?.isContentEditable;

      if (event.key === "Escape") {
        setTourOpen(false);
        setWhatsThisOpen(false);
        setCommandOpen(false);
        setShortcutsOpen(false);
        setGotoPrefix(false);
        return;
      }

      if (commandOpen) {
        if (event.key === "ArrowDown") {
          event.preventDefault();
          setCommandIndex((index) =>
            Math.min(index + 1, Math.max(commandResults.length - 1, 0)),
          );
        } else if (event.key === "ArrowUp") {
          event.preventDefault();
          setCommandIndex((index) => Math.max(index - 1, 0));
        } else if (event.key === "Enter") {
          event.preventDefault();
          const result = commandResults[commandIndex];
          if (result) {
            activateCommandResult(result);
          }
        }
        return;
      }

      if (isTyping) {
        return;
      }

      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        openCommand();
        return;
      }
      if (event.key === "/") {
        event.preventDefault();
        openCommand();
        return;
      }
      if (event.key === "?") {
        event.preventDefault();
        setShortcutsOpen(true);
        return;
      }
      if (event.key.toLowerCase() === "t") {
        event.preventDefault();
        setVocab((value) => (value === "plain" ? "technical" : "plain"));
        return;
      }
      if (gotoPrefix) {
        const screen = GOTO_KEYS[event.key.toLowerCase()];
        if (screen) {
          event.preventDefault();
          selectScreen(screen);
        }
        setGotoPrefix(false);
        return;
      }
      if (event.key.toLowerCase() === "g") {
        setGotoPrefix(true);
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [commandIndex, commandOpen, commandResults, gotoPrefix]);

  useEffect(() => {
    setCommandIndex(0);
  }, [commandQuery]);

  const latestGenerated = formatIso(snapshot?.generated_at);

  function selectScreen(screen: ScreenKey) {
    setActiveScreen(screen);
    window.history.replaceState(null, "", `#${screen}`);
    setWhatsThisOpen(false);
    setCommandOpen(false);
  }

  function selectModelSelection(selection: ModelSelection) {
    setSelectedModel(selection);
    setActiveScreen("model");
    window.history.replaceState(null, "", modelSelectionHash(selection));
    setWhatsThisOpen(false);
    setCommandOpen(false);
    void loadModelPerformance(selection);
  }

  function selectModel(row: OverviewRow) {
    const selection: ModelSelection = {
      modelKey: row.modelKey,
      universeId: row.universeId,
    };
    selectModelSelection(selection);
  }

  function setVocabMode(next: "plain" | "technical") {
    setVocab(next);
  }

  function openCommand() {
    setCommandQuery("");
    setCommandIndex(0);
    setCommandOpen(true);
  }

  function activateCommandResult(result: CommandResult) {
    if (result.type === "screen") {
      selectScreen(result.screen);
    } else if (result.type === "term") {
      selectScreen(result.screen);
      setWhatsThisOpen(true);
    } else if (result.type === "action") {
      if (result.action === "toggle-vocab") {
        setVocab((value) => (value === "plain" ? "technical" : "plain"));
      } else if (result.action === "cycle-theme") {
        setTheme((current) => {
          const idx = THEME_PREFS.indexOf(current);
          return THEME_PREFS[(idx + 1) % THEME_PREFS.length];
        });
      } else if (result.action === "start-tour") {
        if (activeScreen !== "home") selectScreen("home");
        setTourStep(0);
        setTourOpen(true);
      } else if (result.action === "open-whats-this") {
        setWhatsThisOpen(true);
      } else if (result.action === "show-shortcuts") {
        setShortcutsOpen(true);
      }
      setCommandOpen(false);
    }
  }

  async function sendControl(action: OperatorControlAction) {
    setPendingAction(action);
    setControlMessage(null);
    try {
      const response = await fetch("/api/control", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          action,
          requested_at: new Date().toISOString(),
          requested_by: "next-dashboard",
          reason: CONTROL_REASON,
        }),
      });
      const result = (await response.json()) as ControlResult;
      if (!response.ok) {
        throw new Error(result.error ?? `Control failed with ${response.status}`);
      }
      setControlMessage(result.message ?? "Control action accepted.");
      await refreshSnapshot();
    } catch (controlError) {
      const message =
        controlError instanceof Error
          ? controlError.message
          : "Control action failed";
      setControlMessage(message);
    } finally {
      setPendingAction(null);
    }
  }

  async function sendLiveSandboxControl(action: LiveSandboxControlAction) {
    setPendingLiveAction(action);
    setControlMessage(null);
    try {
      const response = await fetch("/api/live-sandbox/control", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          action,
          requested_at: new Date().toISOString(),
          requested_by: "next-dashboard",
          reason: "Next.js live sandbox control",
        }),
      });
      const result = (await response.json()) as LiveSandboxControlResult;
      if (!response.ok) {
        throw new Error(result.error ?? `Live control failed with ${response.status}`);
      }
      setControlMessage(result.message ?? "Live sandbox control accepted.");
      await refreshSnapshot();
    } catch (controlError) {
      const message =
        controlError instanceof Error
          ? controlError.message
          : "Live sandbox control failed";
      setControlMessage(message);
    } finally {
      setPendingLiveAction(null);
    }
  }

  if (loading && !snapshot) {
    return (
      <main className="viewport">
        <article className="surface">
          <div className="surface__head">
            <div className="surface__title">
              <span className="eyebrow">Operator Dashboard</span>
              <h2>Loading paper runtime</h2>
            </div>
          </div>
          <div className="surface__body">
            <p className="microcopy">Waiting for the Python backend snapshot.</p>
          </div>
        </article>
      </main>
    );
  }

  return (
    <div className="app">
      <LeftRail
        snapshot={snapshot}
        activeScreen={activeScreen}
        onSelectScreen={selectScreen}
      />
      <div>
        <TopBar
          snapshot={snapshot}
          generatedAt={latestGenerated}
          activeScreen={activeScreen}
          vocab={vocab}
          onVocab={setVocabMode}
          theme={theme}
          onTheme={setTheme}
          onOpenWhatsThis={() => setWhatsThisOpen(true)}
          onOpenTour={() => {
            // Step 1 anchors the hero on Home — switch screens before opening
            // so the target exists in the DOM when the overlay measures it.
            if (activeScreen !== "home") selectScreen("home");
            setTourStep(0);
            setTourOpen(true);
          }}
        />
        <main className="viewport">
          {error ? (
            <Notice title="Backend unavailable" message={error} tone="danger" />
          ) : null}
          {controlMessage ? (
            <Notice
              title="Operator control"
              message={controlMessage}
              tone="ai"
            />
          ) : null}
          <OverviewScreen
            snapshot={snapshot}
            onNavigate={selectScreen}
            onOpenModel={selectModel}
            active={activeScreen === "overview"}
          />
          <HomeScreen
            snapshot={snapshot}
            onRefresh={refreshSnapshot}
            active={activeScreen === "home"}
          />
          <StrategiesScreen
            snapshot={snapshot}
            active={activeScreen === "strategies"}
          />
          <PaperScreen snapshot={snapshot} active={activeScreen === "paper"} />
          <LiveSandboxScreen
            snapshot={snapshot}
            liveHistory={liveHistory}
            pendingAction={pendingLiveAction}
            onControl={sendLiveSandboxControl}
            active={activeScreen === "live"}
          />
          <RiskScreen
            snapshot={snapshot}
            pendingAction={pendingAction}
            onControl={sendControl}
            active={activeScreen === "risk"}
          />
          <ResearchScreen
            snapshot={snapshot}
            replayReports={replayReports}
            selectedReplayReportId={selectedReplayReportId}
            selectedReplayReport={selectedReplayReport}
            replayReportContent={replayReportContent}
            replayReportsLoading={replayReportsLoading}
            replayReportsError={replayReportsError}
            onSelectReplayReport={(id) => void loadReplayReports(id)}
            onRefreshReplayReports={() =>
              void loadReplayReports(selectedReplayReportId)
            }
            active={activeScreen === "research"}
          />
          <ReportsScreen
            reports={replayReports}
            loading={replayReportsLoading}
            error={replayReportsError}
            onRefresh={() =>
              void loadReplayReports(selectedReplayReportId)
            }
            onOpenReport={(row) => {
              const modelKey = modelKeyFromReportStrategy(row.strategy);
              if (modelKey) {
                selectModelSelection({
                  modelKey,
                  universeId: row.universeId,
                });
                return;
              }
              void loadReplayReports(row.id);
              selectScreen("research");
            }}
            active={activeScreen === "reports"}
          />
          <AiReviewScreen snapshot={snapshot} active={activeScreen === "ai"} />
          <LearnScreen
            active={activeScreen === "learn"}
            onSelectScreen={selectScreen}
          />
          <ModelPerformanceScreen
            active={activeScreen === "model"}
            selection={selectedModel}
            performance={modelPerformance}
            loading={modelPerformanceLoading}
            error={modelPerformanceError}
            onBack={() => selectScreen("overview")}
          />
          <footer className="footer">
            Generated
            <span data-refresh-time> {latestGenerated}</span>. Paper mode only.
            No live-money actions are available from this dashboard.
          </footer>
        </main>
      </div>
      <TourOverlay
        open={tourOpen}
        step={tourStep}
        onNext={() => {
          if (tourStep >= TOUR_STEPS.length - 1) {
            setTourOpen(false);
          } else {
            setTourStep((current) => current + 1);
          }
        }}
        onClose={() => setTourOpen(false)}
      />
      <WhatsThisPanel
        open={whatsThisOpen}
        screen={activeScreen}
        onClose={() => setWhatsThisOpen(false)}
      />
      <CommandPalette
        open={commandOpen}
        query={commandQuery}
        results={commandResults}
        selectedIndex={commandIndex}
        onQuery={setCommandQuery}
        onClose={() => setCommandOpen(false)}
        onHover={setCommandIndex}
        onActivate={activateCommandResult}
      />
      <ShortcutsHelp
        open={shortcutsOpen}
        onClose={() => setShortcutsOpen(false)}
      />
    </div>
  );
}

function LeftRail({
  snapshot,
  activeScreen,
  onSelectScreen,
}: {
  snapshot?: DashboardSnapshot;
  activeScreen: ScreenKey;
  onSelectScreen: (screen: ScreenKey) => void;
}) {
  const killSwitch = Boolean(snapshot?.kill_switch_enabled);
  const killClass = killSwitch
    ? "pill pill--danger"
    : "pill pill--good pill--armed";
  const killLabel = killSwitch ? "Kill switch ON" : "Kill switch OFF";

  return (
    <aside className="rail" aria-label="Primary navigation">
      <div>
        <div className="rail__brand">
          <span className="rail__mark">TL</span>
          <span className="rail__brand-text">
            <strong>Trading Lab</strong>
            <small>Paper Cockpit</small>
          </span>
        </div>
        <nav className="rail__nav">
          {NAV_ITEMS.map(([key, label, glyph]) => (
            <button
              className="nav-item"
              data-screen-link={key}
              type="button"
              aria-current={key === activeScreen ? "page" : undefined}
              key={key}
              onClick={() => onSelectScreen(key)}
            >
              <span className="nav-item__icon">{glyph}</span>
              <span>{label}</span>
            </button>
          ))}
        </nav>
      </div>
      <div />
      <div className="rail__foot">
        <strong data-field="broker">{snapshot?.broker ?? "backend"}</strong>
        <span
          data-tour-anchor="kill"
          style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
        >
          <span data-field="kill-switch" className={killClass}>
            {killLabel}
          </span>
          {glossary("", "kill_switch")}
        </span>
      </div>
    </aside>
  );
}

function TopBar({
  snapshot,
  generatedAt,
  activeScreen,
  vocab,
  onVocab,
  theme,
  onTheme,
  onOpenWhatsThis,
  onOpenTour,
}: {
  snapshot?: DashboardSnapshot;
  generatedAt: string;
  activeScreen: ScreenKey;
  vocab: "plain" | "technical";
  onVocab: (value: "plain" | "technical") => void;
  theme: ThemePref;
  onTheme: (value: ThemePref) => void;
  onOpenWhatsThis: () => void;
  onOpenTour: () => void;
}) {
  const mode = snapshot?.mode ?? "Awaiting runtime";
  const modeClass = mode.toLowerCase().includes("paper")
    ? "mode mode--paper"
    : "mode mode--live";

  return (
    <header className="topbar">
      <div className="topbar__title">
        <small>Operator Dashboard</small>
        <span
          data-screen-title
          data-title_overview="Overview"
          data-title_home="Command Center"
          data-title_strategies="Models"
          data-title_paper="Paper Trading"
          data-title_risk="Risk"
          data-title_research="Research Lab"
          data-title_reports="Reports"
          data-title_ai="AI Review"
          data-title_learn="Learn"
        >
          {SCREEN_TITLES[activeScreen]}
        </span>
      </div>
      <div className="topbar__strip">
        <button
          type="button"
          className="whats-this-trigger"
          data-whats-this-open
          aria-label="Open glossary for this screen"
          title="What's on this screen?"
          onClick={onOpenWhatsThis}
        >
          What&apos;s this?
        </button>
        <button
          type="button"
          className="tour-trigger"
          data-tour-start
          aria-label="Open dashboard tour"
          title="Take the tour"
          onClick={onOpenTour}
        >
          Tour
        </button>
        <div className="vocab-toggle" role="group" aria-label="Vocabulary">
          <button
            type="button"
            className="vocab-toggle__btn"
            data-vocab-set="plain"
            aria-pressed={vocab === "plain"}
            title="Plain language"
            onClick={() => onVocab("plain")}
          >
            Plain
          </button>
          <button
            type="button"
            className="vocab-toggle__btn"
            data-vocab-set="technical"
            aria-pressed={vocab === "technical"}
            title="Technical terms"
            onClick={() => onVocab("technical")}
          >
            Technical
          </button>
        </div>
        <div className="theme-toggle" role="group" aria-label="Theme">
          <button
            type="button"
            className="theme-toggle__btn"
            data-theme-set="light"
            aria-pressed={theme === "light"}
            title="Light theme"
            onClick={() => onTheme("light")}
          >
            Light
          </button>
          <button
            type="button"
            className="theme-toggle__btn"
            data-theme-set="dark"
            aria-pressed={theme === "dark"}
            title="Dark theme"
            onClick={() => onTheme("dark")}
          >
            Dark
          </button>
          <button
            type="button"
            className="theme-toggle__btn"
            data-theme-set="system"
            aria-pressed={theme === "system"}
            title="Match operating system"
            onClick={() => onTheme("system")}
          >
            System
          </button>
        </div>
        <span
          data-tour-anchor="mode"
          style={{ display: "inline-flex", alignItems: "center", gap: 6 }}
        >
          <span className={modeClass} data-field="mode">
            {mode}
          </span>
          {glossary("", "paper_trading")}
        </span>
        <span className="topbar__time">
          <span data-refresh-time> {generatedAt}</span>
        </span>
      </div>
    </header>
  );
}

// =================================================================
// Overview screen
// A plain-English landing page for non-finance users. Pulls already-
// available snapshot fields and curates them so the user can read off:
//  - how their paper portfolio is doing right now
//  - how much the champion model beat the market in backtest
//  - how the best challenger compares to the champion
//  - which promoted models (champion + shadow set) look strongest, plus
//    any autonomous-learning newcomer with a stronger backtest
//  - what the learning worker is investigating next
// Every metric label is wrapped in glossary() so the ? tooltip explains
// the term inline.
// =================================================================

type OverviewRowKind = "champion" | "shadow" | "newcomer";

type OverviewRow = {
  modelKey: string;
  strategyId: string;
  version: string;
  rank?: number | null;
  universeId?: string;
  kind: OverviewRowKind;
  label: string;
  net?: number | null;
  excess?: number | null;
  stress?: number | null;
  maxDD?: number | null;
  score?: number | null;
  seen?: number | null;
  positiveFolds?: number | null;
  foldCount?: number | null;
  gate?: string | null;
  status?: string | null;
  note?: string;
};

function isActivePaperModelCard(card: DashboardModelCard): boolean {
  return isActivePaperModelLabel(card.label);
}

function isActivePaperModelLabel(label: string | undefined): boolean {
  const normalized = (label ?? "").trim().toLowerCase();
  return (
    normalized === "champion" ||
    normalized === "paper authority" ||
    normalized === "active paper model"
  );
}

function OverviewScreen({
  snapshot,
  active,
  onNavigate,
  onOpenModel,
}: {
  snapshot?: DashboardSnapshot;
  active: boolean;
  onNavigate: (screen: ScreenKey) => void;
  onOpenModel: (row: OverviewRow) => void;
}) {
  const activeModel =
    (snapshot?.model_cards ?? []).find(isActivePaperModelCard) ??
    (snapshot?.model_cards ?? [])[0];
  const challengers = (snapshot?.model_cards ?? []).filter(
    (card) => !isActivePaperModelCard(card),
  );
  const bestChallenger = challengers.reduce<typeof challengers[number] | undefined>(
    (top, card) => {
      const score = Number(card.score) || 0;
      const topScore = Number(top?.score) || -Infinity;
      return score > topScore ? card : top;
    },
    undefined,
  );

  const performance = portfolioPerformance(snapshot, "ALL");
  const activeModelExcess = activeModel?.evidence?.excess_return ?? null;
  const activeModelNet = activeModel?.evidence?.net_total_return ?? null;
  const activeModelDD = activeModel?.evidence?.worst_drawdown ?? null;
  const benchmark = activeModel?.evidence?.benchmark ?? "SPY";

  const rows = buildOverviewRows(snapshot);
  const queue = snapshot?.autonomous_learning_service;
  const research = snapshot?.autonomous_learning;

  return (
    <section className="screen screen--overview" data-screen="overview" hidden={!active}>
      <div className="screen__head">
        <div>
          <span className="eyebrow">Overview</span>
          <h1>What&apos;s working, in plain English.</h1>
          <p>
            One page that answers: how is the paper portfolio doing, how did
            the active paper model beat the market historically, what challengers are
            ahead, and what the research worker is testing next.
          </p>
        </div>
      </div>

      <div className="overview-headline">
        <article className="overview-stat overview-stat--hero">
          <span className="eyebrow">{glossary("Your paper portfolio", "paper_portfolio")}</span>
          <strong className="overview-stat__value mono">
            {money(snapshot?.estimated_equity)}
          </strong>
          <span
            className={`overview-stat__delta mono ${
              performance.positive ? "pos" : "neg"
            }`}
          >
            {moneyDelta(performance.delta)} · {percentDelta(performance.percent)} all time
          </span>
          <span className="microcopy">
            {performance.hasHistory
              ? `Paper-trading return since the first recorded snapshot (${performance.points.length} ticks).`
              : "Waiting for the runtime to log a second equity snapshot."}
          </span>
        </article>
        <article className="overview-stat">
          <span className="eyebrow">
            {glossary("Paper model beat market by", "excess_return")}
          </span>
          <strong
            className={`overview-stat__value mono ${signClass(percentValue(activeModelExcess))}`}
          >
            {percentValue(activeModelExcess)}
          </strong>
          <span className="overview-stat__delta">
            backtest {percentValue(activeModelNet)} vs {benchmark}{" "}
            {percentValue(
              activeModel?.evidence?.benchmark_total_return ?? null,
            )}
          </span>
          <span className="microcopy">
            How much the active paper model beat the market over its full
            historical replay window.
          </span>
        </article>
        <article className="overview-stat">
          <span className="eyebrow">
            {glossary("Paper model's worst drawdown", "max_drawdown")}
          </span>
          <strong
            className={`overview-stat__value mono ${signClass(percentValue(activeModelDD))}`}
          >
            {percentValue(activeModelDD)}
          </strong>
          <span className="overview-stat__delta">
            from peak to trough in backtest
          </span>
          <span className="microcopy">
            Lower magnitude = smoother ride. A -25% max DD means the strategy
            once lost 25% from its highest point before recovering.
          </span>
        </article>
      </div>

      <Surface
        eyebrow="Paper authority vs best challenger"
        title="Is something out-performing the live model?"
      >
        <p className="surface__summary">
          The paper authority is the model trading paper money right now. The best
          challenger is the candidate the research engine likes most. A big
          positive delta is the engine&apos;s case for promoting it next.
        </p>
        {activeModel && bestChallenger ? (
          <OverviewDuel champion={activeModel} challenger={bestChallenger} />
        ) : (
          <Empty>
            Paper model or challenger data not available in the snapshot yet.
          </Empty>
        )}
      </Surface>

      <Surface
        eyebrow="Leaderboard"
        title="Top 30 model rankings"
        pill={<Pill tone="ai">{rows.length}</Pill>}
      >
        <p className="surface__summary">
          The highest-ranked candidates from the autonomous learning
          leaderboard, annotated when a row is also the active paper model or a
          shadow challenger. Treat this as a research ranking, not a promotion
          queue: models whose edge is concentrated in the latest 21/63 trading
          days still need 3/6/12-month consistency checks before champion review.
        </p>
        {rows.length === 0 ? (
          <Empty>No models to rank yet.</Empty>
        ) : (
          <OverviewLeaderboard
            rows={rows}
            champion={activeModel}
            onOpenModel={onOpenModel}
          />
        )}
        <p className="microcopy">
          See every replay we&apos;ve run on the{" "}
          <button
            type="button"
            className="overview-link"
            onClick={() => onNavigate("reports")}
          >
            Reports tab
          </button>{" "}
          (7,000+ historical replays).
        </p>
      </Surface>

      <Surface
        eyebrow="Research worker"
        title={glossary("What we're testing next", "hypothesis_queue")}
        pill={
          queue?.service_status ? (
            <Pill tone={queue.service_status === "running_cycle" ? "ai" : "ghost"}>
              {queue.service_status}
            </Pill>
          ) : null
        }
      >
        <OverviewHypothesisQueue queue={queue} research={research} />
      </Surface>
    </section>
  );
}

function OverviewDuel({
  champion,
  challenger,
}: {
  champion: DashboardModelCard;
  challenger: DashboardModelCard;
}) {
  const activeLabel = isActivePaperModelCard(champion)
    ? champion.label
    : "Champion";
  const cScore = Number(champion.score) || 0;
  const xScore = Number(challenger.score) || 0;
  const total = Math.abs(cScore) + Math.abs(xScore);
  const cPct = total === 0 ? 50 : (Math.abs(cScore) / total) * 100;
  const xPct = total === 0 ? 50 : (Math.abs(xScore) / total) * 100;
  const delta = xScore - cScore;
  const challengerLeads = delta > 0;
  const championNet = champion.evidence?.net_total_return ?? null;
  const challengerNet = challenger.evidence?.net_total_return ?? null;
  const championDD = champion.evidence?.worst_drawdown ?? null;
  const challengerDD = challenger.evidence?.worst_drawdown ?? null;

  return (
    <div className="duel" data-overview-duel>
      <div
        className={`duel__side duel__side--left${
          challengerLeads ? "" : " duel__side--winner"
        }`}
      >
        <span className="duel__label">{activeLabel}</span>
        <span className="duel__score mono">{formatScore(cScore)}</span>
        <div className="duel__bar">
          <span className="duel__fill duel__fill--left" style={{ width: `${cPct}%` }} />
        </div>
        <span className="duel__hint mono">
          Net {percentValue(championNet)} · Max DD {percentValue(championDD)}
        </span>
        <span className="duel__hint">{compactModelLabel(champion)}</span>
      </div>
      <div className="duel__pivot">
        <span className="duel__delta-label">
          {challengerLeads ? "Challenger leads by" : `${activeLabel} leads by`}
        </span>
        <span className={`duel__delta mono ${challengerLeads ? "pos" : "neg"}`}>
          {challengerLeads ? "+" : ""}
          {formatScore(delta)}
        </span>
        <span className="duel__hint">
          {challengerLeads
            ? "Research-only. Awaiting promotion."
            : `${activeLabel} still ahead.`}
        </span>
      </div>
      <div
        className={`duel__side duel__side--right${
          challengerLeads ? " duel__side--winner" : ""
        }`}
      >
        <span className="duel__label">{challenger.label}</span>
        <span className="duel__score mono">{formatScore(xScore)}</span>
        <div className="duel__bar">
          <span className="duel__fill duel__fill--right" style={{ width: `${xPct}%` }} />
        </div>
        <span className="duel__hint mono">
          Net {percentValue(challengerNet)} · Max DD {percentValue(challengerDD)}
        </span>
        <span className="duel__hint">{compactModelLabel(challenger)}</span>
      </div>
    </div>
  );
}

function OverviewLeaderboard({
  rows,
  champion,
  onOpenModel,
}: {
  rows: OverviewRow[];
  champion?: DashboardModelCard;
  onOpenModel: (row: OverviewRow) => void;
}) {
  const championRow = champion ? overviewRowFromModelCard(champion) : undefined;
  const championModelKey = championRow?.modelKey;
  const pinnedChampion =
    championRow && !rows.some((row) => row.modelKey === championRow.modelKey)
      ? championRow
      : undefined;

  const columns = (
    <colgroup>
      <col className="overview-table__rank" />
      <col className="overview-table__model" />
      <col className="overview-table__role" />
      <col className="overview-table__metric" />
      <col className="overview-table__delta" />
      <col className="overview-table__metric" />
      <col className="overview-table__folds" />
      <col className="overview-table__metric" />
      <col className="overview-table__score" />
      <col className="overview-table__seen" />
      <col className="overview-table__gate-col" />
    </colgroup>
  );

  return (
    <div
      className="reports-table-wrap overview-table-wrap"
      role="region"
      aria-label="Top model rankings"
    >
      <table className="reports-table overview-table">
        {columns}
        <thead>
          <tr>
            <th scope="col">Rank</th>
            <th scope="col" className="reports-table__strategy">
              Model
            </th>
            <th scope="col">Role</th>
            <th scope="col">{glossary("Net %", "net_total_return")}</th>
            <th scope="col">{glossary("Beat market", "excess_return")}</th>
            <th scope="col">Stress</th>
            <th scope="col">Folds</th>
            <th scope="col">{glossary("Max DD", "max_drawdown")}</th>
            <th scope="col">{glossary("Score", "risk_adjusted_score")}</th>
            <th scope="col">Seen</th>
            <th scope="col">Gate</th>
          </tr>
        </thead>
        <tbody>
          {pinnedChampion ? (
              <OverviewLeaderboardRow
                row={pinnedChampion}
                championModelKey={championModelKey}
                onOpenModel={onOpenModel}
                pinned
              />
            ) : null}
            {rows.map((row) => (
              <OverviewLeaderboardRow
                key={`${row.kind}:${row.modelKey}`}
                row={row}
                championModelKey={championModelKey}
                onOpenModel={onOpenModel}
              />
            ))}
        </tbody>
      </table>
    </div>
  );
}

function OverviewLeaderboardRow({
  row,
  championModelKey,
  onOpenModel,
  pinned = false,
}: {
  row: OverviewRow;
  championModelKey?: string;
  onOpenModel: (row: OverviewRow) => void;
  pinned?: boolean;
}) {
  const isChampion = row.modelKey === championModelKey || row.kind === "champion";
  const activeBadge = isActivePaperModelLabel(row.label)
    ? row.label.toUpperCase()
    : "CHAMPION";
  const rowClass = [
    "reports-table__row",
    isChampion ? "reports-table__row--champion overview-table__champion-row" : "",
    pinned ? "overview-table__champion-pinned" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <tr className={rowClass}>
      <td className="mono">{pinned ? "LIVE" : row.rank ?? "-"}</td>
      <td className="reports-table__strategy">
        {isChampion ? (
          <span className="reports-table__champion-tag">
            {pinned && activeBadge === "CHAMPION"
              ? "CURRENT CHAMPION"
              : activeBadge}
          </span>
        ) : null}
        <button
          type="button"
          className="overview-model-link"
          onClick={() => onOpenModel(row)}
        >
          <span className="reports-table__strategy-name">{row.strategyId}</span>
          <span className="reports-table__sub mono">{row.version}</span>
        </button>
        {row.universeId ? (
          <span className="reports-table__sub">{row.universeId}</span>
        ) : null}
      </td>
      <td>{row.label}</td>
      <td className={`mono ${signClassFromValue(row.net)}`}>
        {percentValue(row.net)}
      </td>
      <td className={`mono ${signClassFromValue(row.excess)}`}>
        {percentValue(row.excess)}
      </td>
      <td className={`mono ${signClassFromValue(row.stress)}`}>
        {percentValue(row.stress)}
      </td>
      <td className="mono">
        {row.positiveFolds !== undefined &&
        row.positiveFolds !== null &&
        row.foldCount !== undefined &&
        row.foldCount !== null
          ? `${row.positiveFolds}/${row.foldCount}`
          : "-"}
      </td>
      <td className={`mono ${signClassFromValue(row.maxDD)}`}>
        {percentValue(row.maxDD)}
      </td>
      <td className="mono">{formatScore(row.score)}</td>
      <td className="mono">{row.seen ?? "-"}</td>
      <td>
        <span className="reports-table__gate">
          {pinned
            ? row.note ?? "Live paper authority"
            : row.gate ?? row.status ?? row.note ?? "-"}
        </span>
      </td>
    </tr>
  );
}

function ModelPerformanceScreen({
  active,
  selection,
  performance,
  loading,
  error,
  onBack,
}: {
  active: boolean;
  selection?: ModelSelection;
  performance?: ModelPerformanceResponse;
  loading: boolean;
  error: string | null;
  onBack: () => void;
}) {
  const modelKey = performance?.model_key ?? selection?.modelKey ?? "Model";
  const benchmark = performance?.benchmark ?? "SPY";
  const points = performance?.points ?? [];
  const metrics = performance?.metrics;
  const recentWindows = performance?.recent_windows ?? [];

  return (
    <section className="screen screen--model" data-screen="model" hidden={!active}>
      <div className="screen__head">
        <div>
          <span className="eyebrow">Model Detail</span>
          <h1 className="mono">{modelKey}</h1>
          <p>
            Point-in-time replay curve for the selected leaderboard model,
            compared against {benchmark} over the longest stored evaluation
            window for that model and universe.
          </p>
        </div>
        <button type="button" className="btn" onClick={onBack}>
          Back to leaderboard
        </button>
      </div>

      {loading ? (
        <Surface eyebrow="Performance" title="Building replay curve">
          <Empty>Re-running the stored historical comparison for this model.</Empty>
        </Surface>
      ) : error ? (
        <Notice title="Model performance unavailable" message={error} tone="danger" />
      ) : performance && metrics ? (
        <>
          <div className="model-performance-stats">
            <article className="overview-stat">
              <span className="eyebrow">Total return</span>
              <strong
                className={`overview-stat__value mono ${signClassFromValue(
                  metrics.net_total_return,
                )}`}
              >
                {percentValue(metrics.net_total_return)}
              </strong>
              <span className="overview-stat__delta">
                {performance.start_date} to {performance.end_date}
              </span>
            </article>
            <article className="overview-stat">
              <span className="eyebrow">Market return</span>
              <strong
                className={`overview-stat__value mono ${signClassFromValue(
                  metrics.benchmark_total_return,
                )}`}
              >
                {percentValue(metrics.benchmark_total_return)}
              </strong>
              <span className="overview-stat__delta">{benchmark}</span>
            </article>
            <article className="overview-stat">
              <span className="eyebrow">Beat market by</span>
              <strong
                className={`overview-stat__value mono ${signClassFromValue(
                  metrics.excess_return,
                )}`}
              >
                {percentValue(metrics.excess_return)}
              </strong>
              <span className="overview-stat__delta">
                simulated after costs
              </span>
            </article>
            <article className="overview-stat">
              <span className="eyebrow">Worst drawdown</span>
              <strong
                className={`overview-stat__value mono ${signClassFromValue(
                  metrics.max_drawdown,
                )}`}
              >
                {percentValue(metrics.max_drawdown)}
              </strong>
              <span className="overview-stat__delta">
                {metrics.trade_count} trades · {metrics.decision_count} decisions
              </span>
            </article>
          </div>

          <Surface
            eyebrow="Model vs market"
            title="Return curve over time"
            pill={<Pill tone="ai">{performance.data_feed}</Pill>}
          >
            {performance.late_entry_risk ? (
              <div
                className="model-performance-warning"
                data-field="late-entry-risk"
              >
                <span className="eyebrow">Late-entry review</span>
                <strong>
                  {performance.late_entry_risk_summary ??
                    "Recent-window concentration is too high for promotion review."}
                </strong>
              </div>
            ) : null}
            <div className="model-performance-chart-card">
              <ModelPerformanceChart points={points} benchmark={benchmark} />
            </div>
            {recentWindows.length > 0 ? (
              <ModelPerformanceRecentWindows
                windows={recentWindows}
                benchmark={benchmark}
              />
            ) : null}
            <div className="model-performance-meta">
              <KRow
                label="Universe"
                value={performance.universe_id ?? "unknown"}
              />
              <KRow label="Window policy" value={performance.window_policy} />
              <KRow
                label="Replay cadence"
                value={performance.decision_frequency.replace(/_/g, " ")}
              />
              <KRow
                label="Fill proxy"
                value={performance.execution_price}
              />
              <KRow
                label="Stored windows"
                value={
                  <span className="mono">
                    {performance.available_window_count}
                  </span>
                }
              />
              <KRow
                label="Source rank"
                value={
                  performance.source_rank ? (
                    <span className="mono">#{performance.source_rank}</span>
                  ) : (
                    "n/a"
                  )
                }
              />
              <KRow
                label="Research score"
                value={
                  <span className="mono">
                    {numberOrFallback(performance.source_research_score, "n/a")}
                  </span>
                }
              />
              <KRow
                label="Source report"
                value={
                  <span className="mono model-performance-source">
                    {performance.source_report}
                  </span>
                }
              />
            </div>
          </Surface>

          {performance.strategy_profile ? (
            <ModelStrategyExplainer
              profile={performance.strategy_profile}
              strategyName={performance.strategy_name}
              benchmark={benchmark}
            />
          ) : null}
        </>
      ) : (
        <Surface eyebrow="Performance" title="No model selected">
          <Empty>Choose a model from the Overview leaderboard.</Empty>
        </Surface>
      )}
    </section>
  );
}

function ModelPerformanceRecentWindows({
  windows,
  benchmark,
}: {
  windows: ModelPerformanceResponse["recent_windows"];
  benchmark: string;
}) {
  if (!windows || windows.length === 0) {
    return null;
  }
  return (
    <div className="model-performance-windows">
      <div className="model-performance-windows__head">
        <span className="eyebrow">Recent-window concentration</span>
        <span>Model vs {benchmark}</span>
      </div>
      <div className="model-performance-window-grid">
        <span>Window</span>
        <span>Model</span>
        <span>Excess</span>
        <span>Share</span>
        <span>Status</span>
        {windows.map((window) => (
          <Fragment key={window.trading_days}>
            <strong>{window.trading_days}d</strong>
            <span className={`mono ${signClassFromValue(window.model_return_delta)}`}>
              {percentValue(window.model_return_delta)}
            </span>
            <span className={`mono ${signClassFromValue(window.excess_return_delta)}`}>
              {percentValue(window.excess_return_delta)}
            </span>
            <span
              className={`mono ${window.late_entry_risk ? "warn" : ""}`}
              title={`${window.start_date} to ${window.end_date}`}
            >
              {percentValue(window.excess_contribution_share)}
            </span>
            <span className={window.late_entry_risk ? "warn" : ""}>
              {window.late_entry_risk ? "Late review" : "Clear"}
            </span>
          </Fragment>
        ))}
      </div>
    </div>
  );
}

function ModelStrategyExplainer({
  profile,
  strategyName,
  benchmark,
}: {
  profile: ModelStrategyProfile;
  strategyName: string;
  benchmark: string;
}) {
  const parameters = Object.entries(profile.parameters ?? {});
  const failures = profile.failure_modes ?? [];
  return (
    <>
      <Surface
        eyebrow="How this model invests"
        title={<span data-field="model-strategy-name">{strategyName}</span>}
        pill={
          <Pill tone="ai">{profile.trading_cadence.replace(/_/g, " ")}</Pill>
        }
      >
        <div className="hero__lead">
          <span className="hero__label">
            {glossary("Hypothesis", "hypothesis")}
          </span>
          <p className="surface__summary" data-field="model-strategy-hypothesis">
            {profile.hypothesis}
          </p>
        </div>
        <div className="model-performance-meta">
          <KRow
            label={glossary("Invests in", "universe")}
            value={
              <span className="mono" data-field="model-strategy-universe">
                {profile.invests_in.join(" · ")}
              </span>
            }
          />
          <KRow
            label={glossary("Measured against", "benchmark")}
            value={<span className="mono">{benchmark}</span>}
          />
          <KRow
            label={glossary("Decision cadence", "cadence")}
            value={profile.trading_cadence.replace(/_/g, " ")}
          />
          <KRow
            label={glossary("Holding period", "holding_period")}
            value={profile.holding_period}
          />
          {parameters.map(([key, value]) => (
            <KRow
              key={key}
              label={key.replace(/_/g, " ")}
              value={<span className="mono">{value}</span>}
            />
          ))}
        </div>
      </Surface>

      <div className="grid-3" aria-label="How this model decides">
        <Surface
          eyebrow={glossary("Signal", "signal_logic")}
          title="How it picks what to buy"
        >
          <p className="surface__summary" data-field="model-strategy-signal">
            {profile.signal_logic}
          </p>
        </Surface>
        <Surface
          eyebrow={glossary("Sizing", "sizing_logic")}
          title="How much it buys"
        >
          <p className="surface__summary" data-field="model-strategy-sizing">
            {profile.sizing_logic}
          </p>
        </Surface>
        <Surface
          eyebrow={glossary("Exit", "exit_logic")}
          title="When it sells"
        >
          <p className="surface__summary" data-field="model-strategy-exit">
            {profile.exit_logic}
          </p>
        </Surface>
      </div>

      {failures.length ? (
        <Surface
          eyebrow={glossary("Known Failure Modes", "failure_modes")}
          title="When this model misses"
          pill={<Pill tone="warn">{failures.length} documented</Pill>}
        >
          <HonestRows
            values={failures}
            empty="No known failure modes recorded for this model."
            tone="warn"
            attrs="data-model-strategy-failure-list"
          />
        </Surface>
      ) : null}
    </>
  );
}

function ModelPerformanceChart({
  points,
  benchmark,
}: {
  points: ModelPerformanceResponse["points"];
  benchmark: string;
}) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [range, setRange] = useState<ChartRange | null>(null);

  // A new series (different model or refreshed data) invalidates any zoom
  // window carried over from the previously viewed model.
  useEffect(() => {
    setRange(null);
    setHoverIndex(null);
  }, [points]);

  if (points.length < 2) {
    return (
      <div
        className="model-performance-chart__empty"
        role="img"
        aria-label="Model performance curve unavailable"
      >
        <span>No equity curve available yet</span>
      </div>
    );
  }

  const chartWidth = 1200;
  const chartHeight = 360;
  // Rendered height of .model-performance-svg in CSS. The svg width is
  // fluid but its height is fixed, so vertical tooltip anchoring uses px.
  const svgRenderedHeight = 420;
  const pad = 42;
  const maxIndex = points.length - 1;
  // Zoom window selected with the drag brush below the chart, expressed as
  // indexes into the full series. Clamped here so a stale range (e.g. right
  // after the points refresh) can never slice out of bounds.
  const windowStart = range
    ? Math.max(Math.min(range.start, maxIndex - 1), 0)
    : 0;
  const windowEnd = range
    ? Math.min(Math.max(range.end, windowStart + 1), maxIndex)
    : maxIndex;
  const zoomed = windowStart > 0 || windowEnd < maxIndex;
  const visible = points.slice(windowStart, windowEnd + 1);
  const values = visible.flatMap((point) => [
    Number(point.model_return),
    Number(point.benchmark_return),
    0,
  ]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = Math.max(max - min, 0.0001);
  const innerW = chartWidth - pad * 2;
  const innerH = chartHeight - pad * 2;
  const xy = (value: number, index: number) => {
    const x = (index / Math.max(visible.length - 1, 1)) * innerW + pad;
    const y = chartHeight - pad - ((value - min) / spread) * innerH;
    return [x, y] as const;
  };
  const modelPath = pathForSeries(
    visible.map((point) => Number(point.model_return)),
    xy,
  );
  const benchmarkPath = pathForSeries(
    visible.map((point) => Number(point.benchmark_return)),
    xy,
  );
  const zeroPath = pathForSeries(visible.map(() => 0), xy);
  const gridValues = [max, min + spread * 0.5, min];
  const firstDate = visible[0].trading_date;
  const lastDate = visible[visible.length - 1].trading_date;
  const lastModel = xy(
    Number(visible[visible.length - 1].model_return),
    visible.length - 1,
  );
  const lastBenchmark = xy(
    Number(visible[visible.length - 1].benchmark_return),
    visible.length - 1,
  );

  // The SVG renders with preserveAspectRatio="none", so it stretches
  // non-uniformly to fill its box. Map the pointer back into viewBox
  // coordinates via the bounding-rect ratio, then snap to the nearest
  // data point.
  const handlePointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    if (!rect.width) return;
    const viewX = ((event.clientX - rect.left) / rect.width) * chartWidth;
    const ratio = (viewX - pad) / Math.max(innerW, 1);
    const index = Math.round(ratio * (visible.length - 1));
    setHoverIndex(Math.min(Math.max(index, 0), visible.length - 1));
  };

  const hovered =
    hoverIndex === null || hoverIndex >= visible.length
      ? undefined
      : visible[hoverIndex];
  const hoverModel =
    hovered && hoverIndex !== null
      ? xy(Number(hovered.model_return), hoverIndex)
      : undefined;
  const hoverBenchmark =
    hovered && hoverIndex !== null
      ? xy(Number(hovered.benchmark_return), hoverIndex)
      : undefined;
  // Anchor the tooltip beside the crosshair, flipping to the left of it
  // near the right edge so it never overflows the card. Percent units keep
  // the math correct under the non-uniform SVG stretch.
  const tooltipFlip = hoverModel ? hoverModel[0] > chartWidth * 0.62 : false;
  const tooltipTopPct =
    hoverModel && hoverBenchmark
      ? Math.min(
          Math.max(
            (Math.min(hoverModel[1], hoverBenchmark[1]) / chartHeight) * 100,
            14,
          ),
          82,
        )
      : 0;

  return (
    <div className="model-performance-chart">
      <div className="model-performance-legend">
        <span>
          <i className="legend-dot legend-dot--model" /> Model{" "}
          <strong className="mono">
            {percentValue(points[points.length - 1].model_return)}
          </strong>
        </span>
        <span>
          <i className="legend-dot legend-dot--market" /> {benchmark}{" "}
          <strong className="mono">
            {percentValue(points[points.length - 1].benchmark_return)}
          </strong>
        </span>
        {zoomed ? (
          <button
            type="button"
            className="chart-reset"
            onClick={() => {
              setRange(null);
              setHoverIndex(null);
            }}
          >
            Reset window
          </button>
        ) : null}
      </div>
      <svg
        className="area-chart model-performance-svg"
        viewBox={`0 0 ${chartWidth} ${chartHeight}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`Model return curve compared with ${benchmark}`}
        onPointerMove={handlePointerMove}
        onPointerLeave={() => setHoverIndex(null)}
      >
        {gridValues.map((value) => {
          const [, y] = xy(value, 0);
          return (
            <Fragment key={value}>
              <line
                className="grid-line"
                x1={pad}
                x2={chartWidth - pad}
                y1={y}
                y2={y}
              />
              <text className="axis-text" x={8} y={y + 4}>
                {percentValue(value)}
              </text>
            </Fragment>
          );
        })}
        <path d={zeroPath} className="model-performance-zero" />
        <path d={benchmarkPath} className="line-market" data-market-line />
        <path d={modelPath} className="line-ai" data-model-line />
        <circle className="end-dot ai" cx={lastModel[0]} cy={lastModel[1]} r="4" />
        <circle
          className="end-dot market"
          cx={lastBenchmark[0]}
          cy={lastBenchmark[1]}
          r="4"
        />
        <text className="axis-text" x={pad} y={chartHeight - 10}>
          {firstDate}
        </text>
        <text
          className="axis-text"
          x={chartWidth - pad}
          y={chartHeight - 10}
          textAnchor="end"
        >
          {lastDate}
        </text>
        {hoverModel && hoverBenchmark ? (
          <g className="chart-crosshair" aria-hidden="true">
            <line
              className="chart-crosshair__line"
              x1={hoverModel[0]}
              x2={hoverModel[0]}
              y1={pad}
              y2={chartHeight - pad}
              vectorEffect="non-scaling-stroke"
            />
            <circle
              className="chart-crosshair__dot chart-crosshair__dot--model"
              cx={hoverModel[0]}
              cy={hoverModel[1]}
              r="4.5"
            />
            <circle
              className="chart-crosshair__dot chart-crosshair__dot--market"
              cx={hoverBenchmark[0]}
              cy={hoverBenchmark[1]}
              r="4.5"
            />
          </g>
        ) : null}
      </svg>
      {hovered && hoverModel ? (
        <div
          className={`chart-tooltip${tooltipFlip ? " chart-tooltip--flip" : ""}`}
          style={{
            left: `${(hoverModel[0] / chartWidth) * 100}%`,
            // px, not %: the chart container also holds the range brush, so
            // a container percentage would drift off the (fixed-height) svg.
            top: `${((tooltipTopPct / 100) * svgRenderedHeight).toFixed(1)}px`,
          }}
          aria-hidden="true"
        >
          <span className="chart-tooltip__date mono">
            {hovered.trading_date}
          </span>
          <span className="chart-tooltip__row">
            <i className="legend-dot legend-dot--model" />
            Model
            <strong
              className={`mono ${signClassFromValue(hovered.model_return)}`}
            >
              {percentValue(hovered.model_return)}
            </strong>
          </span>
          <span className="chart-tooltip__row">
            <i className="legend-dot legend-dot--market" />
            {benchmark}
            <strong
              className={`mono ${signClassFromValue(hovered.benchmark_return)}`}
            >
              {percentValue(hovered.benchmark_return)}
            </strong>
          </span>
        </div>
      ) : null}
      <ChartRangeBrush
        points={points}
        start={windowStart}
        end={windowEnd}
        onChange={(next) => {
          setHoverIndex(null);
          setRange(next);
        }}
      />
    </div>
  );
}

type ChartRange = { start: number; end: number };

function ChartRangeBrush({
  points,
  start,
  end,
  onChange,
}: {
  points: ModelPerformanceResponse["points"];
  start: number;
  end: number;
  onChange: (next: ChartRange) => void;
}) {
  const brushWidth = 1200;
  const brushHeight = 56;
  const padX = 42; // matches the main chart's horizontal pad so x positions align
  const drag = useRef<{
    mode: "left" | "right" | "pan" | "select";
    anchorIndex: number;
    startAtDown: number;
    endAtDown: number;
  } | null>(null);

  const maxIndex = points.length - 1;
  const innerW = brushWidth - padX * 2;
  const values = points.map((point) => Number(point.model_return));
  const min = Math.min(...values, 0);
  const max = Math.max(...values, 0);
  const spread = Math.max(max - min, 0.0001);
  const xFor = (index: number) =>
    (index / Math.max(maxIndex, 1)) * innerW + padX;
  const yFor = (value: number) =>
    brushHeight - 8 - ((value - min) / spread) * (brushHeight - 16);
  const minimapPath = `M ${values
    .map(
      (value, index) => `${xFor(index).toFixed(1)},${yFor(value).toFixed(1)}`,
    )
    .join(" L ")}`;
  // Minimum selectable span so the zoomed chart always has a drawable line.
  const minSpan = Math.max(2, Math.round(maxIndex * 0.01));

  // Like the main chart, this svg stretches (preserveAspectRatio:none), so
  // pointer x maps back through the bounding-rect ratio.
  const indexAt = (svg: SVGSVGElement, clientX: number) => {
    const rect = svg.getBoundingClientRect();
    if (!rect.width) return 0;
    const viewX = ((clientX - rect.left) / rect.width) * brushWidth;
    const ratio = (viewX - padX) / Math.max(innerW, 1);
    return Math.round(Math.min(Math.max(ratio, 0), 1) * maxIndex);
  };

  const handlePointerDown = (event: React.PointerEvent<SVGSVGElement>) => {
    const svg = event.currentTarget;
    const rect = svg.getBoundingClientRect();
    if (!rect.width) return;
    // Decide what was grabbed using client px so the hit zone feels the
    // same regardless of how wide the chart renders.
    const scale = rect.width / brushWidth;
    const startX = rect.left + xFor(start) * scale;
    const endX = rect.left + xFor(end) * scale;
    const grabZone = 10;
    const mode =
      Math.abs(event.clientX - startX) <= grabZone
        ? "left"
        : Math.abs(event.clientX - endX) <= grabZone
          ? "right"
          : event.clientX > startX && event.clientX < endX
            ? "pan"
            : "select";
    drag.current = {
      mode,
      anchorIndex: indexAt(svg, event.clientX),
      startAtDown: start,
      endAtDown: end,
    };
    svg.setPointerCapture(event.pointerId);
    event.preventDefault();
  };

  const handlePointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    const state = drag.current;
    if (!state) return;
    const index = indexAt(event.currentTarget, event.clientX);
    if (state.mode === "left") {
      onChange({
        start: Math.max(Math.min(index, end - minSpan), 0),
        end,
      });
    } else if (state.mode === "right") {
      onChange({
        start,
        end: Math.min(Math.max(index, start + minSpan), maxIndex),
      });
    } else if (state.mode === "pan") {
      const span = state.endAtDown - state.startAtDown;
      const nextStart = Math.min(
        Math.max(state.startAtDown + (index - state.anchorIndex), 0),
        maxIndex - span,
      );
      onChange({ start: nextStart, end: nextStart + span });
    } else {
      let lo = Math.min(state.anchorIndex, index);
      let hi = Math.max(state.anchorIndex, index);
      if (hi - lo < minSpan) {
        hi = Math.min(lo + minSpan, maxIndex);
        lo = Math.max(hi - minSpan, 0);
      }
      onChange({ start: lo, end: hi });
    }
  };

  const endDrag = () => {
    drag.current = null;
  };

  return (
    <div className="chart-brush">
      <svg
        className="chart-brush__svg"
        viewBox={`0 0 ${brushWidth} ${brushHeight}`}
        preserveAspectRatio="none"
        aria-label="Drag to choose the chart time window"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        <path className="chart-brush__path" d={minimapPath} />
        <rect
          className="chart-brush__mask"
          x={padX}
          y={0}
          width={Math.max(xFor(start) - padX, 0)}
          height={brushHeight}
        />
        <rect
          className="chart-brush__mask"
          x={xFor(end)}
          y={0}
          width={Math.max(brushWidth - padX - xFor(end), 0)}
          height={brushHeight}
        />
        <rect
          className="chart-brush__window"
          x={xFor(start)}
          y={0}
          width={Math.max(xFor(end) - xFor(start), 0)}
          height={brushHeight}
        />
        <line
          className="chart-brush__handle"
          x1={xFor(start)}
          x2={xFor(start)}
          y1={0}
          y2={brushHeight}
          vectorEffect="non-scaling-stroke"
        />
        <line
          className="chart-brush__handle"
          x1={xFor(end)}
          x2={xFor(end)}
          y1={0}
          y2={brushHeight}
          vectorEffect="non-scaling-stroke"
        />
        <rect
          className="chart-brush__handle-hit"
          x={xFor(start) - 9}
          y={0}
          width={18}
          height={brushHeight}
        />
        <rect
          className="chart-brush__handle-hit"
          x={xFor(end) - 9}
          y={0}
          width={18}
          height={brushHeight}
        />
      </svg>
      <div className="chart-brush__dates" aria-hidden="true">
        <span className="mono">{points[start].trading_date}</span>
        <span className="mono">{points[end].trading_date}</span>
      </div>
    </div>
  );
}

function pathForSeries(
  values: number[],
  xy: (value: number, index: number) => readonly [number, number],
) {
  return `M ${values
    .map((value, index) => {
      const [x, y] = xy(value, index);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" L ")}`;
}

function overviewRowFromModelCard(card: DashboardModelCard): OverviewRow {
  const key = card.evidence?.model_key ?? `${card.strategy_id}:${card.version}`;
  return {
    modelKey: key,
    strategyId: card.strategy_id,
    version: card.version,
    rank: card.evidence?.rank ?? null,
    universeId: card.evidence?.universe_id ?? undefined,
    kind: isActivePaperModelLabel(card.label) ? "champion" : "shadow",
    label: card.label,
    net: card.evidence?.net_total_return ?? null,
    excess: card.evidence?.excess_return ?? card.evidence?.full_delta ?? null,
    stress: card.evidence?.stress_delta ?? null,
    maxDD: card.evidence?.worst_drawdown ?? null,
    score: card.evidence?.risk_adjusted_score ?? card.score,
    seen: card.evidence?.seen_count ?? null,
    positiveFolds: card.evidence?.positive_folds ?? null,
    foldCount: card.evidence?.fold_count ?? null,
    gate: card.evidence?.gate_status ?? null,
    status: card.evidence?.status ?? null,
    note: card.detail,
  };
}

function buildOverviewRows(snapshot?: DashboardSnapshot): OverviewRow[] {
  const cards = snapshot?.model_cards ?? [];
  const roleByModelKey = new Map<string, string>();
  for (const card of cards) {
    const key = card.evidence?.model_key ?? `${card.strategy_id}:${card.version}`;
    roleByModelKey.set(key, card.label);
  }

  const leaderboard = snapshot?.autonomous_learning?.leaderboard?.entries ?? [];
  if (leaderboard.length) {
    return leaderboard.slice(0, 30).map((entry) => {
      const modelKey = entry.model_key ?? "unknown";
      const [strategyId, ...versionParts] = modelKey.split(":");
      const role = roleByModelKey.get(modelKey) ?? "Research";
      const kind: OverviewRowKind =
        isActivePaperModelLabel(role)
          ? "champion"
          : role.startsWith("Shadow")
            ? "shadow"
            : "newcomer";
      return {
        modelKey,
        strategyId: strategyId || "unknown",
        version: versionParts.join(":"),
        rank: entry.rank ?? null,
        universeId: entry.universe_id,
        kind,
        label: role,
        excess: entry.full_delta ?? null,
        net: entry.net_total_return ?? null,
        stress: entry.stress_delta ?? null,
        maxDD: entry.worst_drawdown ?? null,
        score: entry.risk_adjusted_score ?? null,
        seen: entry.seen_count ?? null,
        positiveFolds: entry.positive_folds ?? null,
        foldCount: entry.fold_count ?? null,
        gate: entry.gate_status ?? null,
        status: entry.status ?? null,
      };
    });
  }

  return cards.map((card, index) => {
    return {
      ...overviewRowFromModelCard(card),
      rank: index + 1,
    };
  });
}

function OverviewHypothesisQueue({
  queue,
  research,
}: {
  queue?: DashboardSnapshot["autonomous_learning_service"];
  research?: DashboardSnapshot["autonomous_learning"];
}) {
  if (!queue && !research) {
    return (
      <Empty>The autonomous research worker has not reported in yet.</Empty>
    );
  }
  const currentTask = queue?.current_task ?? "idle";
  const lanes = queue?.historical_lane_counts ?? {};
  const laneEntries = Object.entries(lanes).sort((a, b) => b[1] - a[1]);
  const recommended =
    research?.recommended_challenger_model_key ??
    queue?.latest_recommended_challenger_model_key ??
    null;
  const heartbeatSince = queue?.heartbeat_at
    ? formatRelative(queue.heartbeat_at)
    : null;

  return (
    <>
      <p className="surface__summary">
        Research runs continuously. The worker pulls a hypothesis from its
        queue, replays it against history, scores the result, then picks the
        next one. If something looks better than the champion, it&apos;s
        flagged for promotion review.
      </p>
      <div className="k-split">
        <div className="k-list">
          <KRow label="Current task" value={<span className="mono">{currentTask}</span>} />
          <KRow
            label="Running hypothesis"
            value={
              <span className="mono">
                {humanizeHypothesisId(queue?.current_historical_hypothesis_id)}
              </span>
            }
          />
          <KRow
            label="Next up"
            value={
              <span className="mono">
                {humanizeHypothesisId(queue?.next_historical_hypothesis_id)}
              </span>
            }
          />
          <KRow
            label="Last completed"
            value={
              <span className="mono">
                {humanizeHypothesisId(queue?.last_historical_hypothesis_id)}
              </span>
            }
          />
        </div>
        <div className="k-list">
          <KRow
            label="Heartbeat"
            value={heartbeatSince ? `${heartbeatSince}` : "no heartbeat"}
          />
          <KRow
            label="Completed cycles"
            value={<span className="mono">{queue?.completed_cycle_count ?? 0}</span>}
          />
          <KRow
            label="Failed cycles"
            value={<span className="mono">{queue?.failed_cycle_count ?? 0}</span>}
          />
          <KRow
            label={glossary("Recommended challenger", "shadow_candidate")}
            value={
              recommended ? (
                <span className="mono">{recommended}</span>
              ) : (
                <span className="row__meta">none yet</span>
              )
            }
          />
        </div>
      </div>
      {laneEntries.length > 0 ? (
        <div className="overview-lanes">
          <span className="eyebrow">Queue depth by lane</span>
          <ul className="overview-lane-list">
            {laneEntries.map(([lane, count]) => (
              <li key={lane}>
                <span className="overview-lane__name">{lane.replace(/_/g, " ")}</span>
                <span className="mono">{count}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </>
  );
}

function compactModelLabel(card: DashboardModelCard): string {
  return `${card.strategy_id}:${card.version}`;
}

function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return "—";
  }
  return Number(value).toFixed(2);
}

function signClassFromValue(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) {
    return "";
  }
  const n = Number(value);
  if (n > 0) return "pos";
  if (n < 0) return "neg";
  return "";
}

function humanizeHypothesisId(value?: string | null): string {
  if (!value) return "—";
  // IDs look like "priority-tune-ai-boom-2023-d36-market-drawdown-circuit-breaker-…-81e0d043".
  // Drop the trailing hex suffix, replace dashes with spaces, leave the
  // family prefix so the user can still tell what's being explored.
  return value
    .replace(/-[a-f0-9]{8,}(-\d{8}T\d{6}Z)?$/i, "")
    .replace(/-/g, " ");
}

function formatRelative(iso: string): string {
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return iso;
  const diff = Date.now() - t;
  const secs = Math.round(diff / 1000);
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

function HomeScreen({
  snapshot,
  onRefresh,
  active,
}: {
  snapshot?: DashboardSnapshot;
  onRefresh: () => Promise<void>;
  active: boolean;
}) {
  return (
    <section className="screen" data-screen="home" hidden={!active}>
      <div className="screen__head">
        <div>
          <span className="eyebrow">
            {glossary("Paper Command Center", "paper_trading")}
          </span>
          <h1>
            Real-money actions are turned off. Your strategy only acts on its
            schedule.
          </h1>
          <p className="microcopy">
            Live-money actions are disabled. Strategy authority remains
            schedule-bound.
          </p>
        </div>
      </div>

      <HomeHero snapshot={snapshot} />
      <TodaySummary snapshot={snapshot} />
      <MetricStats snapshot={snapshot} />

      <div className="grid-2-1">
        <LatestDecisions snapshot={snapshot} />
        <AiSummary snapshot={snapshot} />
      </div>

      <div className="grid-2">
        <SystemStatus snapshot={snapshot} onRefresh={onRefresh} />
        <PaperBoundary snapshot={snapshot} />
      </div>

      <DataFeed snapshot={snapshot} />
    </section>
  );
}

function RiskScreen({
  snapshot,
  pendingAction,
  onControl,
  active,
}: {
  snapshot?: DashboardSnapshot;
  pendingAction: OperatorControlAction | null;
  onControl: (action: OperatorControlAction) => Promise<void>;
  active: boolean;
}) {
  return (
    <section className="screen" data-screen="risk" hidden={!active}>
      <div className="screen__head">
        <div>
          <span className="eyebrow">Risk</span>
          <h1>Your safety net, in one place.</h1>
          <p>
            How risky things are right now, what trades were blocked, where your
            money is, and the one button that stops it all.
          </p>
        </div>
      </div>

      <RiskHero snapshot={snapshot} />
      <RiskStats snapshot={snapshot} />
      <Exposure snapshot={snapshot} />

      <div className="grid-2">
        <RejectedSignals snapshot={snapshot} />
        <Alerts snapshot={snapshot} />
      </div>

      <OperatorControls
        snapshot={snapshot}
        pendingAction={pendingAction}
        onControl={onControl}
      />
    </section>
  );
}

function StrategiesScreen({
  snapshot,
  active,
}: {
  snapshot?: DashboardSnapshot;
  active: boolean;
}) {
  return (
    <section className="screen" data-screen="strategies" hidden={!active}>
      <div className="screen__head">
        <div>
          <span className="eyebrow">Your strategies</span>
          <h1>What&apos;s trading on your behalf - and why.</h1>
          <p>
            Every trade can be traced back to the strategy that fired it, the
            data it used, and whether the safety system let it through.
          </p>
        </div>
      </div>
      <ActiveStrategyHero snapshot={snapshot} />
      <ShadowPerformance active={active} />
      <StrategyStats snapshot={snapshot} />
      <ModelArena snapshot={snapshot} />
      <StrategyLogic snapshot={snapshot} />
      <FailureAndAi snapshot={snapshot} />
    </section>
  );
}

// Color palette used for shadow-model lines. Cyan/AI is reserved for the
// active hero accent so it doesn't double as a chart series; we cycle through
// these distinct hues instead.
const SHADOW_PALETTE = [
  "#2bd576", // pos green
  "#f4b740", // warn amber
  "#ff4d5e", // neg red
  "#a78bfa", // violet
  "#5ee3ff", // ai cyan — included as last so it appears only when needed
  "#ff8aa0",
  "#7fffd4",
  "#ffa971",
];

function ShadowPerformance({ active }: { active: boolean }) {
  const [data, setData] = useState<ShadowHistoryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(() => new Set());
  const inFlight = useRef(false);

  const fetchHistory = useCallback(() => {
    if (inFlight.current) return;
    inFlight.current = true;
    setLoading(true);
    fetch("/api/shadow-history", { cache: "no-store" })
      .then(async (res) => {
        const payload = (await res.json()) as ShadowHistoryResponse;
        if (!res.ok && payload.error) throw new Error(payload.error);
        setData(payload);
        setError(null);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Shadow history unavailable");
      })
      .finally(() => {
        inFlight.current = false;
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (active && !data && !inFlight.current) {
      fetchHistory();
    }
  }, [active, data, fetchHistory]);

  const models = data?.models ?? [];
  // Lock each model_key to a palette color based on its position in the FULL
  // list. Both chart and legend look colors up from this map so toggling a
  // model on/off doesn't reshuffle the colors of the remaining lines.
  const colorByKey = useMemo(() => {
    const map = new Map<string, string>();
    models.forEach((m, idx) => {
      map.set(m.model_key, SHADOW_PALETTE[idx % SHADOW_PALETTE.length]);
    });
    return map;
  }, [models]);
  const visibleModels = useMemo(
    () => models.filter((m) => !hidden.has(m.model_key)),
    [models, hidden],
  );

  return (
    <Surface
      eyebrow="Shadow Trading"
      title="Shadow model equity"
      pill={
        <Pill tone="ai">
          {loading
            ? "loading"
            : models.length
              ? `${models.length} live`
              : "no data yet"}
        </Pill>
      }
    >
      <p className="surface__summary">
        Every candidate runs a virtual book in parallel with the champion.
        Each line is one model&apos;s equity, normalized to its first
        observation so curves are comparable regardless of starting cash.
      </p>
      <div className="shadow-controls">
        <button
          type="button"
          className="btn"
          onClick={() => {
            setData(null);
            fetchHistory();
          }}
          disabled={loading}
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>
      {error ? (
        <Notice
          title="Could not load shadow history"
          message={error}
          tone="danger"
        />
      ) : null}
      {models.length === 0 ? (
        <Empty>
          {loading
            ? "Loading shadow history…"
            : "No shadow observations have been recorded yet. They'll appear here once the runtime logs its next cycle."}
        </Empty>
      ) : (
        <>
          {models.every((m) => m.points.length < 2) ? (
            <p className="microcopy">
              Each model has only one observation logged so far — the chart
              shows current equity as a ring per model. Curves will draw
              themselves once the runtime logs another cycle.
            </p>
          ) : null}
          <ShadowChart models={visibleModels} colorByKey={colorByKey} />
          <ShadowLegend
            models={models}
            colorByKey={colorByKey}
            hidden={hidden}
            onToggle={(key) =>
              setHidden((prev) => {
                const next = new Set(prev);
                if (next.has(key)) next.delete(key);
                else next.add(key);
                return next;
              })
            }
          />
        </>
      )}
    </Surface>
  );
}

function ShadowChart({
  models,
  colorByKey,
}: {
  models: ShadowModelSeries[];
  colorByKey: Map<string, string>;
}) {
  // Fixed viewBox + matching CSS aspect-ratio (set on .shadow-chart) so the
  // SVG always renders at the same proportions instead of stretching to fill
  // whatever width the surface provides.
  const width = 960;
  const height = 320;
  const padL = 56;
  const padR = 24;
  const padT = 16;
  const padB = 32;
  const innerW = width - padL - padR;
  const innerH = height - padT - padB;

  const { tMin, tMax, vMin, vMax } = useMemo(() => {
    let tMin = Number.POSITIVE_INFINITY;
    let tMax = Number.NEGATIVE_INFINITY;
    let vMin = Number.POSITIVE_INFINITY;
    let vMax = Number.NEGATIVE_INFINITY;
    for (const series of models) {
      for (const point of series.points) {
        const t = Date.parse(point.as_of);
        if (!Number.isFinite(t) || series.starting_equity <= 0) continue;
        const v = point.equity / series.starting_equity - 1;
        if (t < tMin) tMin = t;
        if (t > tMax) tMax = t;
        if (v < vMin) vMin = v;
        if (v > vMax) vMax = v;
      }
    }
    // Pad the y-range slightly so flat lines don't sit on the axis.
    const pad = Math.max(Math.abs(vMax - vMin) * 0.1, 0.005);
    return { tMin, tMax, vMin: vMin - pad, vMax: vMax + pad };
  }, [models]);

  if (!Number.isFinite(tMin) || !Number.isFinite(tMax)) {
    return null;
  }

  const tSpan = Math.max(tMax - tMin, 1);
  const vSpan = Math.max(vMax - vMin, 0.001);

  const xFor = (t: number) => padL + ((t - tMin) / tSpan) * innerW;
  const yFor = (v: number) => padT + (1 - (v - vMin) / vSpan) * innerH;

  // Zero baseline for visual reference.
  const zeroY = vMin <= 0 && vMax >= 0 ? yFor(0) : null;

  return (
    <div className="shadow-chart">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="Shadow model equity over time"
      >
        {[0.25, 0.5, 0.75].map((frac) => (
          <line
            key={frac}
            className="shadow-chart__grid"
            x1={padL}
            x2={padL + innerW}
            y1={padT + innerH * frac}
            y2={padT + innerH * frac}
          />
        ))}
        {zeroY !== null ? (
          <line
            className="shadow-chart__zero"
            x1={padL}
            x2={padL + innerW}
            y1={zeroY}
            y2={zeroY}
          />
        ) : null}
        {[
          { v: vMax, anchor: "end" as const, y: padT + 10 },
          { v: vMin, anchor: "end" as const, y: padT + innerH - 4 },
        ].map((tick, idx) => (
          <text
            key={idx}
            className="shadow-chart__tick"
            x={padL - 6}
            y={tick.y}
            textAnchor={tick.anchor}
          >
            {(tick.v * 100).toFixed(1)}%
          </text>
        ))}
        <text
          className="shadow-chart__tick"
          x={padL}
          y={height - 6}
          textAnchor="start"
        >
          {new Date(tMin).toISOString().slice(0, 10)}
        </text>
        <text
          className="shadow-chart__tick"
          x={padL + innerW}
          y={height - 6}
          textAnchor="end"
        >
          {new Date(tMax).toISOString().slice(0, 10)}
        </text>
        {models.map((series) => {
          // Color is looked up by model_key from the caller-supplied map so
          // toggling models on/off doesn't reshuffle palette assignments.
          const color =
            colorByKey.get(series.model_key) ?? SHADOW_PALETTE[0];
          if (series.starting_equity <= 0) return null;
          const drawable = series.points
            .map((point) => ({
              x: xFor(Date.parse(point.as_of)),
              y: yFor(point.equity / series.starting_equity - 1),
            }))
            .filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y));
          if (drawable.length === 0) return null;
          if (drawable.length === 1) {
            const p = drawable[0];
            // Hollow ring so overlapping single-obs dots from different
            // models remain visually distinguishable.
            return (
              <circle
                key={series.model_key}
                cx={p.x}
                cy={p.y}
                r={7}
                fill="none"
                stroke={color}
                strokeWidth={2}
              />
            );
          }
          const d = drawable
            .map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(2)},${p.y.toFixed(2)}`)
            .join(" ");
          return (
            <g key={series.model_key}>
              <path
                d={d}
                fill="none"
                stroke={color}
                strokeWidth={1.75}
                strokeLinejoin="round"
                strokeLinecap="round"
              />
              <circle
                cx={drawable[drawable.length - 1].x}
                cy={drawable[drawable.length - 1].y}
                r={3}
                fill={color}
              />
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function ShadowLegend({
  models,
  colorByKey,
  hidden,
  onToggle,
}: {
  models: ShadowModelSeries[];
  colorByKey: Map<string, string>;
  hidden: Set<string>;
  onToggle: (key: string) => void;
}) {
  return (
    <ul className="shadow-legend" aria-label="Shadow models">
      {models.map((m) => {
        const color = colorByKey.get(m.model_key) ?? SHADOW_PALETTE[0];
        const isHidden = hidden.has(m.model_key);
        const sign = m.total_return >= 0 ? "+" : "";
        const returnText = `${sign}${(m.total_return * 100).toFixed(2)}%`;
        const tone =
          m.total_return > 0 ? "pos" : m.total_return < 0 ? "neg" : "";
        return (
          <li key={m.model_key}>
            <button
              type="button"
              className={`shadow-legend__btn${isHidden ? " shadow-legend__btn--hidden" : ""}`}
              onClick={() => onToggle(m.model_key)}
              aria-pressed={!isHidden}
              title={isHidden ? "Show in chart" : "Hide from chart"}
            >
              <span
                className="shadow-legend__dot"
                style={{ background: color }}
                aria-hidden="true"
              />
              <span className="shadow-legend__label">
                <span className="shadow-legend__strategy">
                  {m.strategy_id ?? m.model_key.split(":")[0]}
                </span>
                <span className="shadow-legend__version">
                  {m.version ?? m.model_key.split(":")[1] ?? ""}
                </span>
              </span>
              <span className={`shadow-legend__return mono ${tone}`}>
                {returnText}
              </span>
              <span className="shadow-legend__points">
                {m.points.length} obs
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function PaperScreen({
  snapshot,
  active,
}: {
  snapshot?: DashboardSnapshot;
  active: boolean;
}) {
  return (
    <section className="screen" data-screen="paper" hidden={!active}>
      <div className="screen__head">
        <div>
          <span className="eyebrow">Paper Trading</span>
          <h1>Holdings, fills, and the reconciliation evidence behind them.</h1>
          <p>Paper mode only. Every order, fill, and lot is traceable.</p>
        </div>
      </div>
      <PaperHero snapshot={snapshot} />
      <PaperStats snapshot={snapshot} />
      <PositionsLedger snapshot={snapshot} />
      <div className="grid-2">
        <RecentFills snapshot={snapshot} />
        <OpenOrders snapshot={snapshot} />
      </div>
      <div className="grid-2">
        <StatementReview snapshot={snapshot} />
        <AuditTrail snapshot={snapshot} />
      </div>
      <TaxEstimate snapshot={snapshot} />
    </section>
  );
}

function LiveSandboxScreen({
  snapshot,
  liveHistory,
  pendingAction,
  onControl,
  active,
}: {
  snapshot?: DashboardSnapshot;
  liveHistory: LiveSandboxHistoryPoint[];
  pendingAction: LiveSandboxControlAction | null;
  onControl: (action: LiveSandboxControlAction) => Promise<void>;
  active: boolean;
}) {
  const sandbox = snapshot?.live_sandbox;
  const control = sandbox?.control_state;
  const status = sandbox?.status ?? "disabled";
  const enabled = Boolean(sandbox?.enabled);
  const autonomy = Boolean(control?.live_autonomy_enabled);
  const killSwitch = Boolean(control?.live_kill_switch_enabled);
  const blocked = sandbox?.blocked_reasons ?? [];
  const intents = sandbox?.order_intents ?? sandbox?.latest_cycle?.order_intents ?? [];
  const openOrders = sandbox?.open_orders ?? [];
  const positions = sandbox?.positions ?? [];
  const fills = sandbox?.recent_fills ?? [];
  const statusTone =
    status === "running" || status === "armed"
      ? "good"
      : status === "disabled" || status === "paused" || status === "kill_switch"
        ? "warn"
        : "danger";

  return (
    <section className="screen" data-screen="live" hidden={!active}>
      <div className="screen__head">
        <div>
          <span className="eyebrow">Live Sandbox</span>
          <h1>$100 autonomous pilot with a hard kill switch.</h1>
          <p>
            Fixed champion, fixed macro-defensive universe, tagged live orders only.
          </p>
        </div>
      </div>

      <Surface
        eyebrow="Live Control"
        title={<span data-field="live-sandbox-status">{humanizeCode(status)}</span>}
        pill={<Pill tone={statusTone}>{enabled ? "Configured" : "Disabled"}</Pill>}
      >
        <div className="k-list">
          <KRow label="Cap" value={money(sandbox?.max_live_allocation)} valueClass="pos" />
          <KRow label="Deployed" value={money(sandbox?.cap_deployed)} valueClass={Number(sandbox?.cap_deployed ?? 0) > 100 ? "neg" : "mono"} />
          <KRow label="Equity" value={money(sandbox?.sandbox_equity)} valueClass="mono" />
          <KRow label="Model" value={<span className="mono">{sandbox?.model_key ?? "unavailable"}</span>} />
          <KRow label="Universe" value={<span className="mono">{sandbox?.universe_id ?? "unavailable"}</span>} />
          <KRow label="Broker" value={<span className="mono">{sandbox?.broker_provider ?? "not connected"}</span>} />
          <KRow label="Order prefix" value={<span className="mono">{sandbox?.order_prefix ?? "live-sandbox-"}</span>} />
          <KRow label="Autonomy" value={autonomy ? "armed" : "paused"} valueClass={autonomy ? "pos" : "warn"} />
          <KRow label="Kill switch" value={killSwitch ? "on" : "off"} valueClass={killSwitch ? "neg" : "pos"} />
        </div>
        <div className="btn-row" style={{ marginTop: 12 }}>
          <LiveControlButton
            action="enable_live_autonomy"
            label="Arm autonomy"
            disabled={!enabled || (autonomy && !killSwitch)}
            pendingAction={pendingAction}
            onControl={onControl}
          />
          <LiveControlButton
            action="pause_live_autonomy"
            label="Pause"
            disabled={!autonomy}
            pendingAction={pendingAction}
            onControl={onControl}
          />
          <LiveControlButton
            action="enable_live_kill_switch"
            label="Kill switch"
            danger
            disabled={killSwitch}
            pendingAction={pendingAction}
            onControl={onControl}
          />
          <LiveControlButton
            action="force_live_reconciliation"
            label="Reconcile"
            pendingAction={pendingAction}
            onControl={onControl}
          />
        </div>
      </Surface>

      <Surface
        eyebrow="Live Graph"
        title="Sandbox equity and deployed capital"
        pill={<Pill tone="info">{liveHistory.length}</Pill>}
      >
        <div className="live-chart">
          <LiveSandboxChart
            points={liveHistory}
            maxAllocation={numericValue(sandbox?.max_live_allocation) ?? 100}
          />
        </div>
        <div className="live-chart__legend" aria-label="Live graph legend">
          <span><i className="legend-dot legend-dot--equity" />Equity</span>
          <span><i className="legend-dot legend-dot--deployed" />Deployed</span>
          <span><i className="legend-line" />Cap</span>
        </div>
      </Surface>

      <div className="grid-2">
        <Surface
          eyebrow="Blocks"
          title="Current live gates"
          pill={<Pill tone={blocked.length ? "warn" : "good"}>{blocked.length}</Pill>}
        >
          <div className="row-list" data-live-blocks>
            {blocked.length ? (
              blocked.map((reason) => (
                <Row primary={<small>{reason}</small>} tone="warn" key={reason} />
              ))
            ) : (
              <Empty>All live sandbox gates are clear.</Empty>
            )}
          </div>
        </Surface>

        <Surface
          eyebrow="Allowlist"
          title={`${sandbox?.allowed_symbols?.length ?? 0} symbols`}
          pill={<Pill tone="info">{sandbox?.benchmark_symbol ?? "SPY"}</Pill>}
        >
          <div className="replay-tags">
            {(sandbox?.allowed_symbols ?? []).map((symbol) => (
              <span key={symbol}>{symbol}</span>
            ))}
          </div>
        </Surface>
      </div>

      <div className="grid-2">
        <Surface
          eyebrow="Next Intents"
          title="Model rebalance preview"
          pill={<Pill tone={intents.length ? "info" : "ghost"}>{intents.length}</Pill>}
        >
          <div className="row-list" data-live-intents>
            {intents.length ? (
              intents.map((intent, index) => (
                <Row
                  key={`${intent.symbol}-${intent.side}-${index}`}
                  primary={<strong>{intent.symbol ?? "UNKNOWN"}</strong>}
                  primarySub={enumText(intent.side, "side")}
                  value={money(intent.estimated_notional)}
                  valueTone={enumText(intent.side, "") === "BUY" ? "pos" : "warn"}
                  meta={<span className="mono">{intent.quantity ?? "0"}</span>}
                />
              ))
            ) : (
              <Empty>No live rebalance intent currently queued.</Empty>
            )}
          </div>
        </Surface>

        <Surface
          eyebrow="Tagged Orders"
          title="Open live sandbox orders"
          pill={<Pill tone={openOrders.length ? "warn" : "good"}>{openOrders.length}</Pill>}
        >
          <div className="row-list" data-live-open-orders>
            {openOrders.length ? (
              openOrders.map((order, index) => {
                const row = recordValue(order);
                return (
                  <Row
                    key={stringValue(row.client_order_id ?? row.broker_order_id, `order-${index}`)}
                    primary={<strong>{stringValue(row.symbol, "UNKNOWN")}</strong>}
                    primarySub={enumText(row.side, "side")}
                    value={stringValue(row.status, "open")}
                    meta={<span className="mono">{stringValue(row.quantity, "0")}</span>}
                  />
                );
              })
            ) : (
              <Empty>No tagged live sandbox orders are open.</Empty>
            )}
          </div>
        </Surface>
      </div>

      <div className="grid-2">
        <Surface
          eyebrow="Live Ledger"
          title="Sandbox positions"
          pill={<Pill tone={positions.length ? "info" : "ghost"}>{positions.length}</Pill>}
        >
          <div className="row-list" data-live-positions>
            {positions.length ? (
              positions.map((position) => (
                <Row
                  key={position.symbol}
                  primary={<strong>{position.symbol}</strong>}
                  primarySub={`qty ${position.quantity}`}
                  value={money(position.average_cost)}
                />
              ))
            ) : (
              <Empty>No live sandbox positions.</Empty>
            )}
          </div>
        </Surface>

        <Surface
          eyebrow="Recent Live Fills"
          title="Tagged fills"
          pill={<Pill tone={fills.length ? "info" : "ghost"}>{fills.length}</Pill>}
        >
          <div className="row-list" data-live-fills>
            {fills.length ? (
              fills.map((fill, index) => (
                <Row
                  key={`${fill.order_id}-${fill.filled_at}-${index}`}
                  primary={<strong>{fill.symbol}</strong>}
                  primarySub={enumText(fill.side, "fill")}
                  value={money(fill.price)}
                  meta={<span className="mono">{fill.quantity}</span>}
                />
              ))
            ) : (
              <Empty>No live sandbox fills yet.</Empty>
            )}
          </div>
        </Surface>
      </div>
    </section>
  );
}

function LiveSandboxChart({
  points,
  maxAllocation,
}: {
  points: LiveSandboxHistoryPoint[];
  maxAllocation: number;
}) {
  const chartWidth = 960;
  const chartHeight = 260;
  const padX = 42;
  const padY = 24;
  if (!points.length) {
    return (
      <div
        className="live-chart__empty"
        role="img"
        aria-label="Live sandbox chart unavailable"
      >
        <span>No live sandbox snapshots yet</span>
      </div>
    );
  }

  const values = [
    0,
    maxAllocation,
    ...points.map((point) => point.equity),
    ...points.map((point) => point.deployed),
  ];
  const maxValue = Math.max(...values, 1);
  const minValue = Math.min(...values, 0);
  const spread = Math.max(maxValue - minValue, 1);
  const innerWidth = chartWidth - padX * 2;
  const innerHeight = chartHeight - padY * 2;
  const xFor = (index: number) =>
    points.length === 1
      ? chartWidth / 2
      : padX + (index / (points.length - 1)) * innerWidth;
  const yFor = (value: number) =>
    chartHeight - padY - ((value - minValue) / spread) * innerHeight;
  const pathFor = (field: "equity" | "deployed") =>
    `M ${points
      .map((point, index) => `${xFor(index).toFixed(1)},${yFor(point[field]).toFixed(1)}`)
      .join(" L ")}`;
  const equityPath = pathFor("equity");
  const deployedPath = pathFor("deployed");
  const capY = yFor(maxAllocation);
  const last = points[points.length - 1];
  const lastX = xFor(points.length - 1);
  const latestLabel = formatLiveChartTime(last.asOf);
  const equityTone = last.equity >= maxAllocation ? "pos" : "ai";

  return (
    <svg
      className="area-chart live-chart__svg"
      viewBox={`0 0 ${chartWidth} ${chartHeight}`}
      preserveAspectRatio="none"
      role="img"
      aria-label="Live sandbox equity and deployed capital"
    >
      {[0, 0.25, 0.5, 0.75, 1].map((tick) => {
        const y = padY + tick * innerHeight;
        return (
          <line
            key={tick}
            className="grid-line"
            x1={padX}
            x2={chartWidth - padX}
            y1={y}
            y2={y}
          />
        );
      })}
      <line
        className="live-chart__cap"
        x1={padX}
        x2={chartWidth - padX}
        y1={capY}
        y2={capY}
      />
      <text className="axis-text" x={padX} y={Math.max(12, capY - 6)}>
        {money(String(maxAllocation))} cap
      </text>
      <path d={deployedPath} className="line-ai" data-live-deployed-line />
      <path
        d={equityPath}
        className={equityTone === "pos" ? "line-pos" : "line-ai"}
        data-live-equity-line
      />
      <circle
        className={equityTone === "pos" ? "end-dot" : "end-dot ai"}
        cx={lastX}
        cy={yFor(last.equity)}
        r="4"
      />
      <circle
        className="end-dot market"
        cx={lastX}
        cy={yFor(last.deployed)}
        r="3.5"
      />
      <text className="axis-text" x={padX} y={chartHeight - 6}>
        {formatLiveChartTime(points[0].asOf)}
      </text>
      <text
        className="axis-text"
        x={chartWidth - padX}
        y={chartHeight - 6}
        textAnchor="end"
      >
        {latestLabel}
      </text>
    </svg>
  );
}

function ResearchScreen({
  snapshot,
  replayReports,
  selectedReplayReportId,
  selectedReplayReport,
  replayReportContent,
  replayReportsLoading,
  replayReportsError,
  onSelectReplayReport,
  onRefreshReplayReports,
  active,
}: {
  snapshot?: DashboardSnapshot;
  replayReports: ReplayReportSummary[];
  selectedReplayReportId?: string;
  selectedReplayReport?: ReplayReportSummary;
  replayReportContent: string;
  replayReportsLoading: boolean;
  replayReportsError: string | null;
  onSelectReplayReport: (id: string) => void;
  onRefreshReplayReports: () => void;
  active: boolean;
}) {
  return (
    <section className="screen" data-screen="research" hidden={!active}>
      <div className="screen__head">
        <div>
          <span className="eyebrow">Research Lab</span>
          <h1>Where new strategies are tested before they go anywhere.</h1>
          <p>
            The AI suggests improvements every night. You decide if any of them
            ever get used.
          </p>
        </div>
      </div>
      <ResearchHero snapshot={snapshot} />
      <LearningLoopStatus snapshot={snapshot} />
      <CandidateReadiness snapshot={snapshot} />
      <ReplayReportsPanel
        reports={replayReports}
        selectedId={selectedReplayReportId}
        selectedReport={selectedReplayReport}
        content={replayReportContent}
        loading={replayReportsLoading}
        error={replayReportsError}
        onSelect={onSelectReplayReport}
        onRefresh={onRefreshReplayReports}
      />
      <ResearchMemo snapshot={snapshot} />
      <WalkForwardStrip snapshot={snapshot} />
      <SystemHealth snapshot={snapshot} />
      <p className="microcopy">
        Research is observed, not promoted. The active model never mutates
        without operator approval.
      </p>
    </section>
  );
}

function ReportsScreen({
  reports,
  loading,
  error,
  onRefresh,
  onOpenReport,
  active,
}: {
  reports: ReplayReportSummary[];
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  onOpenReport: (row: ReportsTableRowData) => void;
  active: boolean;
}) {
  const [searchQuery, setSearchQuery] = useState("");
  const filteredReports = useMemo(
    () => filterReports(reports, searchQuery),
    [reports, searchQuery],
  );
  const baseRows = useMemo(
    () => rankReportsForTable(filteredReports),
    [filteredReports],
  );
  const rankedReportCount = useMemo(
    () => filteredReports.filter((report) => report.topMetric).length,
    [filteredReports],
  );
  const [sort, setSort] = useState<ReportsSortState>(null);
  const [page, setPage] = useState(1);
  const sortedRows = useMemo(
    () => applyReportsSort(baseRows, sort),
    [baseRows, sort],
  );

  // Reset to the first page whenever the sort or the underlying dataset
  // changes, so we never strand the user on an out-of-range page (e.g. they
  // were on page 4, then re-sorted or a refresh shrank the list).
  useEffect(() => {
    setPage(1);
  }, [sort, baseRows, searchQuery]);

  const totalRows = sortedRows.length;
  const searchActive = searchQuery.trim().length > 0;
  const totalPages = Math.max(1, Math.ceil(totalRows / REPORTS_PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageStart = (currentPage - 1) * REPORTS_PAGE_SIZE;
  const pageRows = sortedRows.slice(pageStart, pageStart + REPORTS_PAGE_SIZE);
  const hiddenDuplicateRows = Math.max(0, rankedReportCount - totalRows);
  const unrankedReports = Math.max(0, filteredReports.length - rankedReportCount);
  const countSummary = reportsCountSummary({
    totalRows,
    totalReports: reports.length,
    matchingReports: filteredReports.length,
    hiddenDuplicateRows,
    unrankedReports,
    searchActive,
  });

  const handleSort = (key: ReportsSortKey) => {
    setSort((prev) => {
      if (!prev || prev.key !== key) return { key, direction: "desc" };
      if (prev.direction === "desc") return { key, direction: "asc" };
      return null; // third click clears -> default score order
    });
  };

  return (
    <section className="screen" data-screen="reports" hidden={!active}>
      <div className="screen__head">
        <div>
          <span className="eyebrow">Reports</span>
          <h1>Every research replay, ranked.</h1>
          <p>
            Each row is the top-scoring strategy from one replay. Click any
            column header to sort; click again to reverse, a third time to
            restore the default score order.
          </p>
        </div>
        <button
          type="button"
          className="btn"
          onClick={onRefresh}
          disabled={loading}
        >
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      {error ? (
        <Notice title="Reports unavailable" message={error} tone="danger" />
      ) : null}

      {reports.length > 0 ? (
        <div className="reports-search">
          <label className="reports-search__label" htmlFor="reports-search">
            Search reports
          </label>
          <div className="reports-search__control">
            <input
              id="reports-search"
              type="search"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.currentTarget.value)}
              placeholder="Model key, strategy, run id, file name"
            />
            {searchActive ? (
              <button
                type="button"
                className="btn btn--ghost reports-search__clear"
                onClick={() => setSearchQuery("")}
              >
                Clear
              </button>
            ) : null}
          </div>
          <span className="reports-search__count">
            {countSummary}
          </span>
        </div>
      ) : null}

      {sortedRows.length === 0 ? (
        <p className="empty">
          {loading
            ? "Loading replay reports…"
            : searchActive
              ? "No reports match that search."
              : "No replay reports have been generated yet."}
        </p>
      ) : (
        <div className="reports-table-wrap">
          <table className="reports-table">
            <thead>
              <tr>
                <ReportsSortHeader
                  label="Strategy"
                  sortKey="strategy"
                  sort={sort}
                  onSort={handleSort}
                  className="reports-table__strategy"
                />
                <ReportsSortHeader
                  label="Δ vs champion"
                  sortKey="championDelta"
                  sort={sort}
                  onSort={handleSort}
                />
                <ReportsSortHeader
                  label="Δ vs market"
                  sortKey="marketDelta"
                  sort={sort}
                  onSort={handleSort}
                />
                <ReportsSortHeader
                  label="Net %"
                  sortKey="net"
                  sort={sort}
                  onSort={handleSort}
                />
                <ReportsSortHeader
                  label="Max DD"
                  sortKey="maxDrawdown"
                  sort={sort}
                  onSort={handleSort}
                />
                <ReportsSortHeader
                  label="Date"
                  sortKey="updatedAt"
                  sort={sort}
                  onSort={handleSort}
                  className="reports-table__date"
                />
              </tr>
            </thead>
            <tbody>
              {pageRows.map((row) => (
                <ReportsTableRow
                  key={row.id}
                  row={row}
                  onOpen={onOpenReport}
                />
              ))}
            </tbody>
          </table>
          {totalRows > REPORTS_PAGE_SIZE ? (
            <ReportsPagination
              page={currentPage}
              totalPages={totalPages}
              rangeStart={pageStart + 1}
              rangeEnd={pageStart + pageRows.length}
              totalRows={totalRows}
              label={totalRows === 1 ? "ranked row" : "ranked rows"}
              onPageChange={setPage}
            />
          ) : null}
        </div>
      )}
    </section>
  );
}

const REPORTS_PAGE_SIZE = 25;

function reportsCountSummary({
  totalRows,
  totalReports,
  matchingReports,
  hiddenDuplicateRows,
  unrankedReports,
  searchActive,
}: {
  totalRows: number;
  totalReports: number;
  matchingReports: number;
  hiddenDuplicateRows: number;
  unrankedReports: number;
  searchActive: boolean;
}): string {
  const source = searchActive
    ? formatCount(matchingReports, "matching report")
    : formatCount(totalReports, "report");
  const parts = [`${formatCount(totalRows, "ranked row")} from ${source}`];
  if (hiddenDuplicateRows > 0) {
    parts.push(`${formatCount(hiddenDuplicateRows, "duplicate row")} collapsed`);
  }
  if (unrankedReports > 0) {
    parts.push(formatCount(unrankedReports, "unranked report"));
  }
  return parts.join("; ");
}

function formatCount(count: number, singular: string): string {
  return `${count.toLocaleString()} ${singular}${count === 1 ? "" : "s"}`;
}

function filterReports(
  reports: ReplayReportSummary[],
  query: string,
): ReplayReportSummary[] {
  const exactModelKey = exactReportModelKeyQuery(query);
  if (exactModelKey) {
    return reports.filter((report) =>
      reportMatchesExactModelKey(report, exactModelKey),
    );
  }

  const tokens = normalizeReportSearchText(query)
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (tokens.length === 0) {
    return reports;
  }
  return reports.filter((report) => {
    const haystack = reportSearchText(report);
    const normalizedHaystack = normalizeReportSearchText(haystack);
    return tokens.every(
      (token) => haystack.includes(token) || normalizedHaystack.includes(token),
    );
  });
}

function exactReportModelKeyQuery(query: string): string | undefined {
  const trimmed = query.trim().toLowerCase();
  if (!/^[a-z0-9][a-z0-9_]*:[a-z0-9][a-z0-9_.-]*$/i.test(trimmed)) {
    return undefined;
  }
  return trimmed;
}

function reportMatchesExactModelKey(
  report: ReplayReportSummary,
  modelKey: string,
): boolean {
  return report.topMetric?.strategy?.trim().toLowerCase() === modelKey;
}

function modelKeyFromReportStrategy(strategy: string): string | undefined {
  return exactReportModelKeyQuery(strategy);
}

function reportSearchText(report: ReplayReportSummary): string {
  const metric = report.topMetric;
  return [
    report.id,
    report.title,
    report.fileName,
    report.relativePath,
    report.kind,
    report.runId,
    report.range,
    report.universeId,
    report.benchmark,
    report.champion,
    report.policy,
    report.summary,
    ...(report.tags ?? []),
    metric?.strategy,
    metric?.universe,
    metric?.net,
    metric?.benchmark,
    metric?.delta,
    metric?.maxDrawdown,
    metric?.trades,
    metric?.leakage,
    metric?.championDelta,
    metric?.championBaseline,
    metric?.championRank,
    report.searchText,
  ]
    .filter((value): value is string => typeof value === "string" && value.length > 0)
    .join(" ")
    .toLowerCase();
}

function normalizeReportSearchText(value: string): string {
  return value.toLowerCase().replace(/[_:./-]+/g, " ");
}

function ReportsPagination({
  page,
  totalPages,
  rangeStart,
  rangeEnd,
  totalRows,
  label = "rows",
  onPageChange,
}: {
  page: number;
  totalPages: number;
  rangeStart: number;
  rangeEnd: number;
  totalRows: number;
  label?: string;
  onPageChange: (page: number) => void;
}) {
  const atFirst = page <= 1;
  const atLast = page >= totalPages;
  return (
    <nav className="reports-pagination" aria-label="Reports pages">
      <p className="reports-pagination__status" aria-live="polite">
        Showing <strong>{rangeStart.toLocaleString()}</strong>–
        <strong>{rangeEnd.toLocaleString()}</strong> of{" "}
        <strong>{totalRows.toLocaleString()}</strong> {label}
      </p>
      <div className="reports-pagination__controls">
        <button
          type="button"
          className="btn"
          onClick={() => onPageChange(Math.max(1, page - 1))}
          disabled={atFirst}
          aria-label="Previous page"
        >
          Previous
        </button>
        <span className="reports-pagination__page" aria-current="page">
          Page {page} of {totalPages}
        </span>
        <button
          type="button"
          className="btn"
          onClick={() => onPageChange(Math.min(totalPages, page + 1))}
          disabled={atLast}
          aria-label="Next page"
        >
          Next
        </button>
      </div>
    </nav>
  );
}

type ReportsSortKey =
  | "strategy"
  | "championDelta"
  | "marketDelta"
  | "net"
  | "maxDrawdown"
  | "updatedAt";

type ReportsSortDirection = "asc" | "desc";

type ReportsSortState = { key: ReportsSortKey; direction: ReportsSortDirection } | null;

function ReportsSortHeader({
  label,
  sortKey,
  sort,
  onSort,
  className,
}: {
  label: string;
  sortKey: ReportsSortKey;
  sort: ReportsSortState;
  onSort: (key: ReportsSortKey) => void;
  className?: string;
}) {
  const active = sort?.key === sortKey;
  const direction = active ? sort!.direction : undefined;
  const ariaSort = active
    ? direction === "asc"
      ? "ascending"
      : "descending"
    : "none";
  return (
    <th
      scope="col"
      className={`reports-table__th${active ? " reports-table__th--active" : ""}${className ? ` ${className}` : ""}`}
      aria-sort={ariaSort}
    >
      <button
        type="button"
        className="reports-table__sort"
        onClick={() => onSort(sortKey)}
      >
        <span>{label}</span>
        <span
          className="reports-table__sort-icon"
          aria-hidden="true"
          data-direction={direction ?? "none"}
        >
          {direction === "asc" ? "▲" : direction === "desc" ? "▼" : "↕"}
        </span>
      </button>
    </th>
  );
}

type ReportsTableRowData = {
  id: string;
  strategy: string;
  championDelta: string;
  marketDelta: string;
  net: string;
  maxDrawdown: string;
  updatedAt: string;
  range?: string;
  universeId?: string;
  benchmark?: string;
  duplicateCount: number;
};

function ReportsTableRow({
  row,
  onOpen,
}: {
  row: ReportsTableRowData;
  onOpen: (row: ReportsTableRowData) => void;
}) {
  const opensModel = modelKeyFromReportStrategy(row.strategy) !== undefined;
  return (
    <tr
      className="reports-table__row"
      onClick={() => onOpen(row)}
      tabIndex={0}
      role="button"
      aria-label={`${opensModel ? "Open model graph for" : "Open report"} ${row.strategy}`}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen(row);
        }
      }}
    >
      <td className="reports-table__strategy">
        <span className="reports-table__strategy-name">{row.strategy}</span>
        <span className="reports-table__sub">
          {row.duplicateCount > 1
            ? `${row.duplicateCount.toLocaleString()} replay files · `
            : ""}
          {row.universeId ? `${row.universeId} · ` : ""}
          {row.range ?? "—"}
          {row.benchmark ? ` · vs ${row.benchmark}` : ""}
        </span>
      </td>
      <td className={`mono ${signClass(row.championDelta)}`}>
        {row.championDelta}
      </td>
      <td className={`mono ${signClass(row.marketDelta)}`}>{row.marketDelta}</td>
      <td className={`mono ${signClass(row.net)}`}>{row.net}</td>
      <td className={`mono ${signClass(row.maxDrawdown)}`}>{row.maxDrawdown}</td>
      <td className="mono reports-table__date">
        {formatReportDate(row.updatedAt)}
      </td>
    </tr>
  );
}

function rankReportsForTable(
  reports: ReplayReportSummary[],
): ReportsTableRowData[] {
  // Report-level `champion` metadata is historical and can predate the current
  // late-entry/portfolio-governance gates, so the Reports table does not stamp
  // a global champion badge. It ranks visible replay rows only.
  const parsedRows = reports
    .filter((report) => report.topMetric)
    .map<ReportsTableRowData>((report) => {
      const m = report.topMetric!;
      return {
        id: report.id,
        strategy: m.strategy ?? report.champion ?? report.runId ?? report.title,
        championDelta: m.championDelta ?? "—",
        marketDelta: m.delta ?? "—",
        net: m.net ?? "—",
        maxDrawdown: m.maxDrawdown ?? "—",
        updatedAt: report.updatedAt,
        range: report.range,
        universeId: report.universeId,
        benchmark: report.benchmark,
        duplicateCount: 1,
      };
    });
  const collapsedRows = new Map<string, ReportsTableRowData>();
  for (const row of parsedRows) {
    const signature = reportsTableRowSignature(row);
    const existing = collapsedRows.get(signature);
    if (!existing) {
      collapsedRows.set(signature, row);
      continue;
    }
    const duplicateCount = existing.duplicateCount + 1;
    const rowTime = Date.parse(row.updatedAt);
    const existingTime = Date.parse(existing.updatedAt);
    if (
      Number.isFinite(rowTime) &&
      (!Number.isFinite(existingTime) || rowTime > existingTime)
    ) {
      collapsedRows.set(signature, { ...row, duplicateCount });
    } else {
      existing.duplicateCount = duplicateCount;
    }
  }
  const rows = [...collapsedRows.values()];

  // Default order: net % descending.
  const parseNet = (value: string): number => {
    const m = value.match(/(-?[\d.]+)/);
    return m ? Number.parseFloat(m[1]) : Number.NEGATIVE_INFINITY;
  };
  rows.sort((a, b) => {
    return parseNet(b.net) - parseNet(a.net);
  });
  return rows;
}

function reportsTableRowSignature(row: ReportsTableRowData): string {
  return [
    row.strategy,
    row.championDelta,
    row.marketDelta,
    row.net,
    row.maxDrawdown,
    row.range ?? "",
    row.universeId ?? "",
    row.benchmark ?? "",
  ].join("\u0000");
}

function applyReportsSort(
  rows: ReportsTableRowData[],
  sort: ReportsSortState,
): ReportsTableRowData[] {
  if (!sort) return rows;
  const dir = sort.direction === "asc" ? 1 : -1;

  const compare = (a: ReportsTableRowData, b: ReportsTableRowData): number => {
    switch (sort.key) {
      case "strategy":
        return a.strategy.localeCompare(b.strategy);
      case "updatedAt": {
        const at = Date.parse(a.updatedAt);
        const bt = Date.parse(b.updatedAt);
        const safeA = Number.isNaN(at) ? -Infinity : at;
        const safeB = Number.isNaN(bt) ? -Infinity : bt;
        return safeA - safeB;
      }
      case "championDelta":
        return parseNumeric(a.championDelta) - parseNumeric(b.championDelta);
      case "marketDelta":
        return parseNumeric(a.marketDelta) - parseNumeric(b.marketDelta);
      case "net":
        return parseNumeric(a.net) - parseNumeric(b.net);
      case "maxDrawdown":
        return parseNumeric(a.maxDrawdown) - parseNumeric(b.maxDrawdown);
    }
  };

  return [...rows].sort((a, b) => dir * compare(a, b));
}

function parseNumeric(value: string | undefined): number {
  if (!value) return Number.NEGATIVE_INFINITY;
  const match = value.match(/-?\d+(\.\d+)?/);
  return match ? Number.parseFloat(match[0]) : Number.NEGATIVE_INFINITY;
}

function signClass(value: string | undefined): string {
  if (!value) return "";
  const trimmed = value.trim();
  if (trimmed.startsWith("+") && !trimmed.startsWith("+0.00")) return "pos";
  if (trimmed.startsWith("-") && !trimmed.startsWith("-0.00")) return "neg";
  return "";
}

function formatReportDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "2-digit",
  }).format(date);
}

function AiReviewScreen({
  snapshot,
  active,
}: {
  snapshot?: DashboardSnapshot;
  active: boolean;
}) {
  const nightly = snapshot?.nightly_learning;
  const headline =
    nightly?.active_model_unchanged === true
      ? "Copilot active · operator-approved"
      : "Pending operator review";
  const confidence = nightly?.recommendations?.[0]?.confidence;

  return (
    <section className="screen" data-screen="ai" hidden={!active}>
      <div className="screen__head" aria-label="AI Governance posture">
        <div>
          <span className="eyebrow">{glossary("AI oversight", "ai_governance")}</span>
          <h1>{headline}</h1>
          <p>
            <Confidence score={confidence} />
            &nbsp;·&nbsp; The AI explains, summarizes, and recommends. It never
            trades or changes anything on its own.
          </p>
        </div>
      </div>
      <DailyMemo snapshot={snapshot} />
      <div className="grid-2">
        <CompletionAudit snapshot={snapshot} />
        <FinalAcceptance snapshot={snapshot} />
      </div>
      <div className="grid-2">
        <ReportsAndLearning snapshot={snapshot} />
        <LiveReadiness snapshot={snapshot} />
      </div>
      <p className="microcopy">
        AI cannot trade, promote models, or change risk limits. Every change
        requires human approval.
      </p>
    </section>
  );
}

function LearnScreen({
  active,
  onSelectScreen,
}: {
  active: boolean;
  onSelectScreen: (screen: ScreenKey) => void;
}) {
  return (
    <section className="screen" data-screen="learn" hidden={!active}>
      <div className="screen__head">
        <div>
          <span className="eyebrow">Learn</span>
          <h1>How to read this dashboard.</h1>
          <p>
            A plain-language reference for every technical term in the app. Pick
            a topic — each entry links to the screen where you&apos;ll see it in
            use.
          </p>
        </div>
      </div>
      <nav
        aria-label="Topic index"
        style={{ display: "flex", flexWrap: "wrap", gap: 8 }}
      >
        {Object.entries(TOPICS).map(([key, topic]) => (
          <a
            className="pill pill--ghost"
            href={`#learn-${key}`}
            style={{ textDecoration: "none" }}
            key={key}
          >
            {topic.heading}
          </a>
        ))}
      </nav>
      {Object.entries(TOPICS).map(([key, topic]) => (
        <Fragment key={key}>
          <span id={`learn-${key}`} />
          <Surface
            eyebrow={topic.heading}
            title="Terms you'll see in this topic."
            pill={
              <a
                className="pill pill--ghost"
                href={topic.defaultLink}
                style={{ textDecoration: "none" }}
                onClick={(event) => {
                  const screen = screenFromHash(topic.defaultLink) ?? "home";
                  event.preventDefault();
                  onSelectScreen(screen);
                }}
              >
                See on {SCREEN_LABELS[topic.defaultLink]} →
              </a>
            }
          >
            <p className="surface__summary">{topic.blurb}</p>
            <div className="row-list">
              {topic.terms.map((termKey) => {
                const entry = GLOSSARY[termKey];
                if (!entry) {
                  return null;
                }
                const deepLink = deepLinkFor(termKey, topic.defaultLink);
                const screen = screenFromHash(deepLink) ?? "home";
                return (
                  <a
                    className="row row--link"
                    data-screen-link={screen}
                    href={deepLink}
                    aria-label={`Open ${SCREEN_LABELS[deepLink]}: ${entry.term}`}
                    onClick={(event) => {
                      event.preventDefault();
                      onSelectScreen(screen);
                    }}
                    key={termKey}
                  >
                    <div className="row__primary">
                      <strong className="mono" style={{ fontSize: 13 }}>
                        {entry.term}
                      </strong>
                      <small>{entry.definition}</small>
                    </div>
                    <div
                      className="row__value"
                      style={{ color: "var(--ai)", fontSize: 12 }}
                    >
                      See on {SCREEN_LABELS[deepLink]} →
                    </div>
                  </a>
                );
              })}
            </div>
          </Surface>
        </Fragment>
      ))}
      <p className="microcopy">
        Definitions are also available as ? tooltips next to any technical term
        in the app. Plain / Technical switches the label; the meaning is
        unchanged.
      </p>
    </section>
  );
}

function HomeHero({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const [period, setPeriod] = useState<PortfolioPeriod>("1D");

  // Restore the last-selected period across reloads so the user keeps their
  // preferred view. Falls back silently if localStorage is unavailable.
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem("dashPortfolioPeriod");
      if (isPortfolioPeriod(stored)) setPeriod(stored);
    } catch {
      /* ignore */
    }
  }, []);

  const selectPeriod = (next: PortfolioPeriod) => {
    setPeriod(next);
    try {
      window.localStorage.setItem("dashPortfolioPeriod", next);
    } catch {
      /* ignore */
    }
  };

  const equity = money(snapshot?.estimated_equity);
  const performance = portfolioPerformance(snapshot, period);
  const windowLabel = PORTFOLIO_PERIOD_LABELS[period];

  return (
    <section className="hero" aria-label="Paper Portfolio" data-tour-anchor="hero">
      <div className="hero__lead">
        <span className="hero__label">
          {glossary("Your portfolio", "paper_portfolio")}
        </span>
        <div className="hero__value" data-field="estimated-equity">
          {equity}
        </div>
        <div className="hero__delta">
          <span className={performance.positive ? "delta-pos" : "delta-neg"}>
            {moneyDelta(performance.delta)}
          </span>
          <span className="delta-divider">·</span>
          <span>{percentDelta(performance.percent)} {windowLabel}</span>
          <span className="delta-divider">·</span>
          <span>
            {performance.hasHistory
              ? `since first recorded snapshot ${windowLabel}`
              : "waiting for history in this window"}
          </span>
        </div>
      </div>
      <div className="hero__chart" data-hero-chart>
        <EquityChart points={performance.points} positive={performance.positive} />
      </div>
      <div className="hero__periods" aria-label="Portfolio chart range">
        {PORTFOLIO_PERIODS.map((option) => (
          <button
            key={option}
            type="button"
            className="period"
            data-period={option}
            aria-pressed={period === option}
            onClick={() => selectPeriod(option)}
          >
            {option}
          </button>
        ))}
      </div>
    </section>
  );
}

function RiskHero({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const severity = riskSeverity(snapshot);
  const tone = riskTone(snapshot);
  const color =
    tone === "danger" ? "var(--neg)" : tone === "warn" ? "var(--warn)" : "var(--ai)";
  const rejectionCount =
    snapshot?.daily_report?.risk_report?.rejection_count ?? 0;
  const rejectionText =
    rejectionCount === 1
      ? "1 rejection today"
      : `${rejectionCount} rejections today`;
  const rules =
    snapshot?.daily_report?.risk_report?.rejection_rules?.join(", ") ||
    "no rules firing";
  const killSwitch = Boolean(snapshot?.kill_switch_enabled);
  const killClass = killSwitch ? "pill pill--danger" : "pill pill--ai pill--armed";
  const killLabel = killSwitch ? "Kill switch ON" : "Kill switch OFF";

  return (
    <section className="hero" aria-label="Risk severity">
      <div className="hero__lead">
        <span className="hero__label">
          {glossary("Risk State", "risk_state")}
        </span>
        <div className="hero__value" style={{ color }}>
          <span data-field="risk-severity">{severity}</span>
        </div>
        <div className="hero__delta">
          <span>{rejectionText}</span>
          <span className="delta-divider">·</span>
          <span className="mono">{rules}</span>
          <span className="delta-divider">·</span>
          <span className={killClass} aria-label={killLabel}>
            {killLabel}
          </span>
        </div>
      </div>
      <p className="microcopy">
        The {glossary("kill switch", "kill_switch")} is the one button that
        stops all paper trading. Press it whenever you want — it cannot affect
        real money.
      </p>
    </section>
  );
}

function TodaySummary({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const rejected =
    snapshot?.daily_report?.rejected_signal_report?.rejected_signals ?? [];
  return (
    <Surface
      eyebrow="What happened today"
      title="A plain-English summary"
      pill={<Pill tone="ai">for beginners</Pill>}
      extraClass="surface--today hide-in-tech"
    >
      <ul className="today-bullets">
        <li>
          <span className="today-bullets__dot" />
          We reviewed the current paper runtime snapshot today.
        </li>
        <li>
          <span className="today-bullets__dot" />
          {rejected.length
            ? `${rejected.length} trade ${rejected.length === 1 ? "was" : "were"} blocked by safety rules.`
            : "No trades were blocked by the safety system."}
        </li>
        <li>
          <span className="today-bullets__dot" />
          The AI can explain and summarize, but it cannot trade on its own.
        </li>
      </ul>
    </Surface>
  );
}

function MetricStats({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const risk = snapshot?.daily_report?.risk_report;
  const realized = Number(snapshot?.realized_pnl ?? 0);
  const activeCount = snapshot?.active_strategy_definition ? 1 : 0;
  const cashDetail = snapshot?.managed_capital
    ? `Broker cash; model target is ${money(snapshot.managed_target_equity ?? snapshot.managed_capital)}`
    : "Broker cash available to the paper strategy";
  const stats = [
    {
      label: "Broker cash",
      value: <span data-field="cash">{money(snapshot?.cash)}</span>,
      detail: cashDetail,
    },
    {
      label: "Day P&L",
      value: <span data-field="realized-pnl">{money(snapshot?.realized_pnl)}</span>,
      detail: (
        <>
          Open orders: <span data-field="open-orders">{snapshot?.open_orders ?? 0}</span>
        </>
      ),
      tone: realized > 0 ? "pos" : realized < 0 ? "neg" : "",
    },
    {
      label: "Risk",
      value: riskSeverity(snapshot),
      detail: `${risk?.rejection_count ?? 0} rejections`,
      tone: riskTone(snapshot),
    },
    {
      label: "Running strategies",
      value: String(activeCount || 1),
      detail: "fake-money only",
      tone: "ai",
    },
  ];
  return <StatRow stats={stats} ariaLabel="Portfolio metrics" />;
}

function RiskStats({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const risk = snapshot?.daily_report?.risk_report;
  const alerts = snapshot?.alerts ?? [];
  const rejections = risk?.rejection_count ?? 0;
  const stats = [
    {
      label: "How worried we are",
      value: riskSeverity(snapshot),
      detail: `${risk?.risk_decisions ?? 0} trades checked today`,
      tone: riskTone(snapshot),
    },
    {
      label: glossary("Trades blocked", "rejected_signals"),
      value: String(rejections),
      detail: rejections ? "Paper orders refused today" : "All paper orders cleared",
      tone: rejections ? "warn" : "",
    },
    {
      label: "Active warnings",
      value: String(alerts.length),
      detail: alerts.length ? "Operator review needed" : "Runtime is quiet",
      tone: alerts.length ? "warn" : "",
    },
    {
      label: glossary("Drawdown", "drawdown"),
      value: "—",
      detail: "No history yet",
    },
  ];
  return <StatRow stats={stats} ariaLabel="Risk metrics" />;
}

function LatestDecisions({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const trades = snapshot?.daily_report?.trade_explanations ?? [];
  const rejectedFallback =
    trades.length > 0
      ? []
      : snapshot?.daily_report?.rejected_signal_report?.rejected_signals ?? [];
  const decisions = [
    ...trades.map(decisionFromTradeExplanation),
    ...rejectedFallback.map(decisionFromRejectedSignal),
  ];
  return (
    <Surface
      eyebrow={glossary("Today's decisions", "daily_report")}
      title="What the strategy did today"
      pill={
        <Pill tone={decisions.length ? "ai" : "ghost"}>
          {decisions.length} reviewed
        </Pill>
      }
    >
      {decisions.length ? (
        <div className="row-list">
          {decisions.map((decision) => (
            <Row
              key={decision.orderId}
              primary={<strong>{decision.primary}</strong>}
              primarySub={decision.orderId}
              meta={decision.meta}
              value={decision.status}
              valueTone={decision.valueTone}
              note={decision.note}
              tone={decision.tone}
            />
          ))}
        </div>
      ) : (
        <Empty>
          No trade decisions reviewed yet today. They appear here after the daily
          runtime cycle scores each candidate.
        </Empty>
      )}
    </Surface>
  );
}

type DecisionRow = {
  orderId: string;
  primary: string;
  meta: string;
  status: string;
  valueTone: string;
  note: string;
  tone?: string;
};

function decisionFromTradeExplanation(trade: TradeExplanation): DecisionRow {
  const status = enumText(trade.status, "reviewed").toUpperCase();
  const side = enumText(trade.side, "BUY").toUpperCase();
  const accepted = trade.accepted;
  const brokerState = trade.broker_submitted
    ? "broker submitted"
    : "not broker submitted";
  const filled = trade.fill_ids?.length ? ` · ${trade.fill_ids.length} fill(s)` : "";
  return {
    orderId: trade.order_id,
    primary: `${trade.symbol} ${accepted ? status : "BLOCKED"}`,
    meta: `${side} ${trade.quantity} · ${brokerState}${filled}`,
    status,
    valueTone: accepted ? "pos" : "warn",
    note:
      trade.explanation ??
      trade.signal_rationale ??
      "Daily report reviewed this paper decision.",
    tone: accepted ? "" : "warn",
  };
}

function decisionFromRejectedSignal(signal: RejectedSignal): DecisionRow {
  return {
    orderId: signal.order_id,
    primary: `${signal.symbol} BLOCKED`,
    meta: signal.rule,
    status: "REJECTED",
    valueTone: "warn",
    note: humanizeRejection(signal.rule, signal.message),
    tone: "warn",
  };
}

function AiSummary({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const summary = snapshot?.daily_report?.ai_summary;
  const evidenceCount = summary?.evidence?.length ?? 0;
  const evidenceLabel =
    evidenceCount === 1 ? "1 source" : `${evidenceCount} sources`;
  return (
    <Surface
      eyebrow={glossary("What the AI did", "ai_daily_memo")}
      title="AI is a copilot, not an oracle"
      pill={
        <Pill tone={summary?.summary ? "ai" : "ghost"}>
          {summary?.summary ? "REVIEWED" : "PENDING"}
        </Pill>
      }
    >
      <div className="memo">
        {summary?.summary ??
          "The AI has not published a memo yet today. It is still gathering evidence."}
        <small>AI copilot · daily report evidence · paper authority only</small>
      </div>
      <div className="k-list">
        <KRow
          label="Evidence"
          value={summary?.summary ? evidenceLabel : "pending"}
        />
        <KRow label="Authority" value="paper · manual approval" />
      </div>
    </Surface>
  );
}

function SystemStatus({
  snapshot,
  onRefresh,
}: {
  snapshot?: DashboardSnapshot;
  onRefresh: () => Promise<void>;
}) {
  const runtime = snapshot?.runtime_state;
  const cycle = recordValue(runtime?.last_cycle);
  return (
    <Surface
      eyebrow={glossary("System status", "runtime_proof")}
      title="What ran today"
      pill={
        <button className="pill pill--ai" type="button" onClick={() => void onRefresh()}>
          Refresh
        </button>
      }
    >
      <div className="k-list">
        <KRow label="Runtime" value={<span data-field="runtime-status">{runtime?.status ?? "awaiting"}</span>} />
        <KRow label="Trading authority" value={<span data-field="trading-authority">Daily close only</span>} />
        <KRow
          label="Prices refreshed"
          value={<span data-field="prices-refreshed">{yesNo(Boolean(cycle.prices_refreshed ?? runtime?.latest_prices?.status === "fresh"))}</span>}
        />
        <KRow label="Broker synced" value={<span data-field="broker-synced">{yesNo(Boolean(cycle.broker_synced ?? snapshot?.broker))}</span>} />
        <KRow label="Broker connection" value={<span data-field="broker-connection">{snapshot?.broker ?? "unknown"}</span>} />
        <KRow
          label="Active model"
          value={<span data-field="active-model-key">{runtime?.active_model_key ?? strategyKey(snapshot)}</span>}
        />
        <KRow label="Orders submitted" value={<span data-field="orders-submitted">{numberValue(cycle.orders_submitted, snapshot?.open_orders ?? 0)}</span>} />
        <KRow label="Fills applied" value={<span data-field="fills-applied">{numberValue(cycle.fills_applied, snapshot?.recent_fills?.length ?? 0)}</span>} />
        <KRow
          label="Reconciliation"
          value={
            <span data-field="reconciliation">
              {snapshot?.paper_report?.reconciliation?.reconciled
                ? "Reconciled"
                : "Mismatch"}
            </span>
          }
          valueClass={
            snapshot?.paper_report?.reconciliation?.reconciled ? "pos" : "neg"
          }
        />
      </div>
    </Surface>
  );
}

function PaperBoundary({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const liveSandbox = snapshot?.live_sandbox;
  const liveEnabled = Boolean(liveSandbox?.enabled);
  return (
    <Surface
      eyebrow={glossary("This is fake money", "paper_boundary")}
      title={liveEnabled ? "Paper plus live sandbox" : glossary("Live disabled", "live_disabled")}
      pill={<Pill tone={liveEnabled ? "warn" : "good"}>{liveEnabled ? "$100 sandbox" : "Paper only"}</Pill>}
    >
      <div className="k-list">
        <KRow label="Runtime mode" value={<span data-field="paper-boundary-mode">{snapshot?.mode ?? "Paper Trading"}</span>} />
        <KRow label="Money at risk" value={liveEnabled ? money(liveSandbox?.max_live_allocation) : "$0 real capital"} valueClass={liveEnabled ? "warn" : "pos"} />
        <KRow label="Blocked products" value="No margin, shorts, options" />
        <KRow label="Live readiness" value={<span data-field="live-readiness-status">{stringValue(snapshot?.live_readiness?.status, "disabled")}</span>} />
        <KRow label="Live sandbox" value={<span data-field="live-sandbox-boundary-status">{liveSandbox?.status ?? "disabled"}</span>} />
      </div>
    </Surface>
  );
}

function DataFeed({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const latest = latestPrices(snapshot);
  const quality = recordValue(snapshot?.daily_report?.data_quality_report);
  const status = stringValue(quality.status, "unavailable");
  const qualityTone =
    status === "failed"
      ? "danger"
      : status === "warning" || status === "unavailable"
        ? "warn"
        : "good";
  const provenance = recordValue(quality.provenance);
  const issues = arrayValue(quality.issues);

  return (
    <div className="grid-2">
      <Surface
        eyebrow={glossary("Latest Prices", "latest_prices")}
        title={
          <>
            Market data · <span data-field="price-feed">{latest.feed}</span>
          </>
        }
        pill={<Pill tone={latest.status === "fresh" ? "good" : "warn"}>{latest.status.toUpperCase()}</Pill>}
      >
        <div className="k-row">
          <span>Freshness</span>
          <strong>
            <span data-field="price-freshness" className="mono">
              {latest.status}
            </span>
          </strong>
        </div>
        <div className="row-list" data-latest-price-list>
          {latest.records.length ? (
            latest.records.map((record) => (
              <Row
                primary={<strong>{record.symbol}</strong>}
                primarySub={record.status}
                value={record.price}
                valueTone={record.tone}
                key={record.symbol}
              />
            ))
          ) : (
            <Empty>
              No live prices yet. Quotes appear once the market-data feed
              delivers its first snapshot of the day.
            </Empty>
          )}
        </div>
        <p className="microcopy" data-field="price-warning">
          {latest.warning}
        </p>
        <p className="microcopy">{snapshot?.data_feed_status ?? "Market data pending."}</p>
      </Surface>

      <Surface
        eyebrow={glossary("How good is the data?", "data_quality")}
        title={<span data-field="data-quality-status">{status}</span>}
        pill={
          <span className={`pill pill--${qualityTone}`} data-field="data-quality-chip">
            {status}
          </span>
        }
      >
        {quality.status ? (
          <>
            <p className="surface__summary" data-field="data-quality-summary">
              {stringValue(quality.summary, "Market-data quality status is unavailable.")}
            </p>
            <div className="k-split">
              <div className="k-list">
                <KRow label="Research usable" value={<span data-field="data-quality-research-usable">{yesNo(Boolean(quality.can_use_for_research))}</span>} />
                <KRow label="Trading usable" value={<span data-field="data-quality-trading-usable">{yesNo(Boolean(quality.can_use_for_trading))}</span>} />
                <KRow label="Warnings" value={<span data-field="data-quality-warnings" className="mono">{numberValue(quality.warnings, 0)}</span>} />
                <KRow label="Failures" value={<span data-field="data-quality-failures" className="mono">{numberValue(quality.failures, 0)}</span>} />
              </div>
              <div className="k-list">
                <KRow label="Dataset" value={<span data-field="data-quality-dataset">{stringValue(provenance.dataset_type, "unavailable")}</span>} />
                <KRow label="Symbols" value={<span data-field="data-quality-symbols">{symbolCount(provenance.symbols)}</span>} />
                <KRow label="Sources" value={<span data-field="data-quality-sources">{joinValues(provenance.sources)}</span>} />
                <KRow label="Feeds" value={<span data-field="data-quality-feeds">{joinValues(provenance.feeds)}</span>} />
                <KRow label="Window" value={<span data-field="data-quality-window">{qualityWindow(quality)}</span>} />
              </div>
            </div>
            <div className="k-row">
              <span>Quality Issues</span>
              <strong>{numberValue(quality.warnings, 0)} warning · {numberValue(quality.failures, 0)} failure</strong>
            </div>
            <div className="row-list" data-data-quality-issue-list>
              {issues.length ? (
                issues.slice(0, 4).map((issue, index) => {
                  const row = recordValue(issue);
                  const issueStatus = enumText(row.status, "warning");
                  return (
                    <Row
                      primary={<strong>{humanizeCode(stringValue(row.code, "data_quality_issue"))}</strong>}
                      primarySub={stringValue(row.message, "Data-quality issue requires review.")}
                      meta={stringValue(row.symbol, "dataset")}
                      tone={issueStatus === "failed" ? "danger" : "warn"}
                      key={index}
                    />
                  );
                })
              ) : (
                <Empty>No data-quality issues today. The market data passed every check.</Empty>
              )}
            </div>
          </>
        ) : (
          <Empty>
            No data-quality report yet. It will arrive after the next runtime
            cycle verifies the market data.
          </Empty>
        )}
      </Surface>
    </div>
  );
}

function Exposure({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const positions = snapshot?.paper_report?.ledger_snapshot?.positions ?? [];
  const exposures = positions.map((position) => ({
    symbol: position.symbol,
    value: exposureValue(position),
  }));
  const maxValue = Math.max(...exposures.map((item) => item.value), 1);
  const total = exposures.reduce((sum, item) => sum + item.value, 0);
  const largestShare = total ? (Math.max(...exposures.map((i) => i.value)) / total) * 100 : 0;

  return (
    <Surface
      eyebrow={glossary("Where your money is", "exposure")}
      title="Exposure by symbol"
      pill={
        <Pill tone={largestShare >= 60 ? "warn" : exposures.length ? "ai" : "ghost"}>
          {exposures.length ? `top ${largestShare.toFixed(0)}%` : "flat"}
        </Pill>
      }
    >
      {exposures.length ? (
        <>
          <div className="k-list">
            {exposures.map((item) => (
              <HBar
                key={item.symbol}
                label={item.symbol}
                value={item.value}
                maxValue={maxValue}
              />
            ))}
          </div>
          <p className="microcopy">
            Largest position anchors the scale. Cost basis = quantity × average
            cost. Live mark-to-market arrives with the next snapshot.
          </p>
        </>
      ) : (
        <Empty>
          No positions held, so there is no exposure to chart. Bars will appear
          once a strategy buys its first symbol.
        </Empty>
      )}
    </Surface>
  );
}

function RejectedSignals({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const rejected =
    snapshot?.daily_report?.rejected_signal_report?.rejected_signals ?? [];
  return (
    <Surface
      eyebrow={glossary("Trades the safety system blocked", "rejected_signals")}
      title="Rejected Signals"
      pill={
        <Pill tone={rejected.length ? "warn" : "good"}>
          {rejected.length ? `${rejected.length} blocked` : "clean"}
        </Pill>
      }
    >
      {rejected.length ? (
        <div className="row-list">
          {rejected.map((signal) => (
            <RejectedSignalRow signal={signal} key={signal.order_id} />
          ))}
        </div>
      ) : (
        <Empty>No trades were blocked today. The safety system is quiet.</Empty>
      )}
    </Surface>
  );
}

function RejectedSignalRow({ signal }: { signal: RejectedSignal }) {
  const ruleKey = RULE_GLOSSARY_KEYS[signal.rule];
  const rule = ruleKey ? glossary(signal.rule, ruleKey) : signal.rule;

  return (
    <Row
      primary={<strong className="mono">{rule}</strong>}
      primarySub={humanizeRejection(signal.rule, signal.message)}
      meta={
        <>
          <span className="mono">{signal.order_id}</span> · {signal.symbol}
        </>
      }
      tone="warn"
    />
  );
}

function Alerts({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const alerts = snapshot?.alerts ?? [];
  const hasError = alerts.some((alert) => alert.severity === "error");
  const tone = hasError ? "danger" : alerts.length ? "warn" : "good";
  const label = hasError ? "ERROR" : alerts.length ? "WARN" : "CLEAR";

  return (
    <Surface
      eyebrow={glossary("System warnings", "runtime_alerts")}
      title={<span data-field="alert-count">{alerts.length} active</span>}
      pill={<span className={`pill pill--${pillTone(tone)}`} data-field="alert-tone">{label}</span>}
    >
      <div className="row-list" data-alert-list>
        {alerts.length ? (
          alerts.map((alert) => <AlertRow alert={alert} key={alert.id} />)
        ) : (
          <Empty>
            No active alerts. The runtime is quiet — nothing needs your attention
            right now.
          </Empty>
        )}
      </div>
      <p className="microcopy">
        Alerts surface from the runtime journal. They never auto-dismiss — close
        the underlying condition first.
      </p>
    </Surface>
  );
}

function AlertRow({ alert }: { alert: DashboardAlert }) {
  return (
    <Row
      primary={<strong>{alert.title}</strong>}
      primarySub={alert.message}
      meta={alert.code}
      note={alert.evidence?.join(" / ")}
      tone={alert.severity === "error" ? "danger" : "warn"}
    />
  );
}

function OperatorControls({
  snapshot,
  pendingAction,
  onControl,
}: {
  snapshot?: DashboardSnapshot;
  pendingAction: OperatorControlAction | null;
  onControl: (action: OperatorControlAction) => Promise<void>;
}) {
  const controlState = snapshot?.control_state;
  const paused = Boolean(controlState?.paused);
  const killSwitch = Boolean(snapshot?.kill_switch_enabled);
  const stateText = paused ? "Paused" : "Armed";
  const stateTone = paused ? "warn" : "ai";
  const killPillTone = killSwitch ? "danger" : "ai";
  const killLabel = killSwitch ? "Kill ON" : "Kill OFF";
  const killClass = killSwitch ? "pill pill--danger" : "pill pill--ai pill--armed";
  const lastAction = snapshot?.last_control_result?.request?.action ?? "none";

  return (
    <Surface
      eyebrow={glossary("What you can do", "operator_controls")}
      title="Operator Controls"
      pill={<Pill tone={killPillTone}>{killLabel}</Pill>}
    >
      <div className="k-row">
        <span>Runtime</span>
        <strong>
          <span className={`pill pill--${stateTone}`} data-field="control-state-heading">{stateText}</span>
        </strong>
      </div>
      <div className="k-row">
        <span>Kill switch</span>
        <strong>
          <span className={killClass} data-field="paper-kill-switch-state">{killLabel}</span>
        </strong>
      </div>
      <div data-control-grid>
        <div className="btn-row">
          <ControlButton
            action="resume_runtime"
            label="Resume trading"
            disabled={!paused}
            pendingAction={pendingAction}
            onControl={onControl}
          />
          <ControlButton
            action="pause_runtime"
            label="Pause trading"
            disabled={paused}
            pendingAction={pendingAction}
            onControl={onControl}
          />
          <ControlButton
            action="force_reconciliation"
            label="Re-check vs broker"
            pendingAction={pendingAction}
            onControl={onControl}
          />
          <ControlButton
            action="generate_report"
            label="Save today's summary"
            pendingAction={pendingAction}
            onControl={onControl}
          />
        </div>
        <p className="microcopy" style={{ marginTop: 12 }}>
          Stopping paper trading halts every order. It&apos;s safe and reversible
          — no real money can be affected.
        </p>
        <div className="btn-row" style={{ marginTop: 8 }}>
          <ControlButton
            action="enable_paper_kill_switch"
            label="Stop all paper trading"
            disabled={killSwitch}
            danger
            pendingAction={pendingAction}
            onControl={onControl}
          />
          <ControlButton
            action="disable_paper_kill_switch"
            label="Re-enable trading"
            disabled={!killSwitch}
            pendingAction={pendingAction}
            onControl={onControl}
          />
        </div>
      </div>
      <div className="k-list">
        <KRow label="Last action" value={<span data-field="last-control-action">{lastAction}</span>} valueClass="mono" />
        <KRow label="Updated by" value={<span data-field="control-updated-by">{controlState?.updated_by ?? "system"}</span>} />
        <KRow
          label="Updated at"
          value={<span data-field="control-updated-at">{formatIso(controlState?.updated_at)}</span>}
          valueClass="mono"
        />
      </div>
    </Surface>
  );
}

function ActiveStrategyHero({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const definition = snapshot?.active_strategy_definition;
  if (!definition) {
    return (
      <Surface eyebrow="Active Model" title="No active strategy assigned">
        <Empty>
          No strategy is active yet. Assign one to start paper trading and this
          card will fill with its thesis.
        </Empty>
      </Surface>
    );
  }
  const cadence = enumText(definition.trading_cadence, "daily_close");
  const authority = enumText(definition.authority, "paper");
  const modelKey = `${definition.strategy_id ?? "strategy"}:${definition.version ?? "unknown"}`;
  return (
    <Surface
      eyebrow={glossary("Active Model", "active_model")}
      title={<span data-field="active-strategy-name">{definition.name}</span>}
      pill={<span className="pill pill--ai" data-field="active-strategy-authority">{authority}</span>}
    >
      <div className="hero__lead">
        <span className="hero__label">{glossary("Hypothesis", "hypothesis")}</span>
        <p className="surface__summary" data-field="active-strategy-hypothesis">
          {definition.hypothesis ?? "No hypothesis recorded for this strategy."}
        </p>
      </div>
      <div className="k-list">
        <KRow
          label="Strategy ID"
          value={<span data-field="active-strategy-id" className="mono">{modelKey}</span>}
        />
        <KRow
          label={glossary("Cadence", "cadence")}
          value={<span data-field="active-strategy-cadence">{cadence}</span>}
        />
      </div>
    </Surface>
  );
}

function StrategyStats({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const definition = snapshot?.active_strategy_definition;
  if (!definition) {
    return null;
  }
  const [scoreValue, scoreTone] = championScore(snapshot);
  const cadence = enumText(definition.trading_cadence, "daily_close");
  const universeCount = definition.universe?.length ?? 0;
  return (
    <StatRow
      ariaLabel="Active model metrics"
      stats={[
        {
          label: glossary("Score", "score"),
          value: <span className="mono">{scoreValue}</span>,
          detail: "Higher is better",
          tone: scoreTone,
        },
        {
          label: glossary("Cadence", "cadence"),
          value: <span className="mono">{cadence}</span>,
          detail: `Holds positions for ${definition.holding_period ?? "review window"}`,
        },
        {
          label: glossary("Universe", "universe"),
          value: (
            <span data-field="active-strategy-universe" className="mono">
              {universeCount} U.S. ETFs
            </span>
          ),
          detail: "What it can pick from",
          tone: "ai",
        },
        {
          label: glossary("Benchmark", "benchmark"),
          value: (
            <span data-field="active-strategy-benchmark" className="mono">
              {definition.benchmark ?? "SPY"}
            </span>
          ),
          detail: "Returns compared to this index",
        },
      ]}
    />
  );
}

function ModelArena({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const comparison = firstComparison(snapshot);
  if (comparison) {
    const champion = comparison.champion ?? {};
    const challenger = comparison.challenger ?? {};
    const championScore = Number(comparison.champion_score ?? 0);
    const challengerScore = Number(comparison.challenger_score ?? 0);
    const delta = Number(comparison.score_delta ?? challengerScore - championScore);
    const recommendation = enumText(comparison.recommendation, "hold");
    return (
      <Surface
        eyebrow={glossary("Model Arena", "model_arena")}
        title={glossary("Champion / Challenger", "champion_challenger")}
        pill={<Pill tone="ai">recommend · {recommendation}</Pill>}
      >
        <ScoreDuel
          leftLabel="Champion"
          leftValue={championScore}
          rightLabel="Challenger"
          rightValue={challengerScore}
        />
        <div hidden aria-hidden="true">
          <BarCompare
            leftLabel="Champion"
            leftValue={championScore}
            rightLabel="Challenger"
            rightValue={challengerScore}
          />
        </div>
        <div className="k-split">
          <div className="k-list">
            <KRow
              label="Champion"
              value={<span className="mono">{modelKey(champion)}</span>}
            />
            <KRow label="State" value={enumText(champion.state, "paper")} />
          </div>
          <div className="k-list">
            <KRow
              label="Challenger"
              value={<span className="mono">{modelKey(challenger)}</span>}
            />
            <KRow label="State" value={enumText(challenger.state, "validated")} />
          </div>
        </div>
        <p className="surface__summary">
          {comparison.rationale ??
            `Score delta ${delta >= 0 ? "+" : ""}${delta.toFixed(4)}. Promotion requires manual approval.`}
        </p>
        <p className="microcopy">
          Promotion requires manual approval. Challenger remains in research
          authority until reviewed.
        </p>
      </Surface>
    );
  }

  const cards = snapshot?.model_cards ?? [];
  const activeModelEvidence =
    cards.find(isActivePaperModelCard)?.evidence ?? null;
  return (
    <Surface
      eyebrow={glossary("Model Arena", "model_arena")}
      title="Paper authority / challenger"
      pill={<Pill tone="ai">active model locked</Pill>}
    >
      {cards.length ? (
        <div className="grid-2">
          {cards.map((card) => (
            <ModelArenaCard
              card={card}
              activeModelEvidence={activeModelEvidence}
              key={`${card.strategy_id}:${card.version}`}
              snapshot={snapshot}
            />
          ))}
        </div>
      ) : (
        <Empty>
          No paper-authority-vs-challenger comparisons yet. They appear once a new
          model is scored against the active one.
        </Empty>
      )}
    </Surface>
  );
}

function ModelArenaCard({
  card,
  activeModelEvidence,
  snapshot,
}: {
  card: DashboardModelCard;
  activeModelEvidence?: DashboardModelEvidence | null;
  snapshot?: DashboardSnapshot;
}) {
  const evidence = card.evidence ?? null;
  const modelKey = `${card.strategy_id}:${card.version}`;
  const isActive = isActivePaperModelCard(card);
  const shadow = shadowObservationForModel(snapshot, modelKey);
  const period = evidencePeriod(evidence);
  const excessReturn = evidence?.excess_return ?? evidence?.full_delta;
  const returnVsActive = modelReturnVsChampion(evidence, activeModelEvidence);
  const foldSummary =
    evidence?.positive_folds !== undefined &&
    evidence?.positive_folds !== null &&
    evidence?.fold_count !== undefined &&
    evidence?.fold_count !== null
      ? `${evidence.positive_folds}/${evidence.fold_count}`
      : "n/a";
  const source =
    evidence?.rank !== undefined && evidence?.rank !== null
      ? `#${evidence.rank} leaderboard`
      : evidence?.source === "full_comparison_only"
        ? "full comparison only"
        : evidence?.source ?? "missing";
  const trackingReturn = shadowTrackingReturn(shadow);
  return (
    <Surface
      eyebrow={card.label}
      title={<span className="mono">{modelKey}</span>}
      pill={
        <Pill tone={isActive ? "good" : "ai"}>
          {card.state.toUpperCase()}
        </Pill>
      }
    >
      <p className="surface__summary">{card.detail}</p>
      {evidence?.note ? <p className="microcopy">{evidence.note}</p> : null}
      <div className="k-list">
        <KRow label="Period" value={period} />
        <KRow
          label="Total return"
          value={
            <span className={toneClass(evidence?.net_total_return)}>
              {percentValue(evidence?.net_total_return)}
            </span>
          }
        />
        <KRow
          label={`Market (${evidence?.benchmark ?? "SPY"})`}
          value={percentValue(evidence?.benchmark_total_return)}
        />
        <KRow
          label="Beat market by"
          value={
            <span className={toneClass(excessReturn)}>
              {percentValue(excessReturn)}
            </span>
          }
        />
        <KRow
          label="Return vs paper model"
          value={
            isActive ? (
              "active paper authority"
            ) : (
              <span className={toneClass(returnVsActive)}>
                {percentValue(returnVsActive)}
              </span>
            )
          }
        />
        <KRow
          label="Worst drawdown"
          value={
            <span className={toneClass(evidence?.worst_drawdown, true)}>
              {percentValue(evidence?.worst_drawdown)}
            </span>
          }
        />
        <KRow
          label="Folds"
          value={`${foldSummary} · worst ${percentValue(evidence?.min_fold_delta)}`}
        />
        <KRow
          label="Research score"
          value={
            <span className="mono">
              {numberOrFallback(evidence?.risk_adjusted_score, "n/a")}
            </span>
          }
        />
        <KRow
          label="Trades"
          value={
            evidence?.trade_count !== undefined && evidence?.trade_count !== null
              ? `${evidence.trade_count} / ${evidence.decision_count ?? "?"} decisions`
              : "n/a"
          }
        />
        <KRow
          label="Evidence"
          value={
            evidence?.seen_count
              ? `${source} · seen ${evidence.seen_count}x`
              : source
          }
        />
        {evidence?.gate_status ? (
          <KRow label="Gate" value={evidence.gate_status} />
        ) : null}
        {shadow ? (
          <>
            <KRow label="Shadow equity" value={money(shadow.estimated_equity)} />
            <KRow
              label="Shadow move"
              value={
                <span className={toneClass(trackingReturn)}>
                  {percentValue(trackingReturn)}
                </span>
              }
            />
            <KRow label="Targets" value={targetSummary(shadow)} />
          </>
        ) : isActive ? (
          <>
            <KRow label="Paper equity" value={money(snapshot?.estimated_equity)} />
            <KRow
              label="Open paper positions"
              value={
                snapshot?.daily_report?.pnl_report?.open_position_symbols?.join(", ") ||
                "none"
              }
            />
          </>
        ) : null}
      </div>
    </Surface>
  );
}

function StrategyLogic({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const definition = snapshot?.active_strategy_definition;
  if (!definition) {
    return null;
  }
  return (
    <div className="grid-3" aria-label="Trade lifecycle logic">
      <Surface eyebrow={glossary("Signal", "signal_logic")} title="How it picks what to buy">
        <p className="surface__summary" data-field="active-strategy-signal">
          {definition.signal_logic ?? "Signal logic has not been documented."}
        </p>
      </Surface>
      <Surface eyebrow={glossary("Sizing", "sizing_logic")} title="How much it buys">
        <p className="surface__summary" data-field="active-strategy-sizing">
          {definition.sizing_logic ?? "Sizing logic has not been documented."}
        </p>
      </Surface>
      <Surface eyebrow={glossary("Exit", "exit_logic")} title="When it sells">
        <p className="surface__summary" data-field="active-strategy-exit">
          {definition.exit_logic ?? "Exit logic has not been documented."}
        </p>
      </Surface>
    </div>
  );
}

function FailureAndAi({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const definition = snapshot?.active_strategy_definition;
  if (!definition) {
    return null;
  }
  const failures = definition.failure_modes?.slice(0, 3) ?? [];
  const aiRoles = definition.ai_role?.slice(0, 3) ?? [];
  return (
    <div className="grid-2">
      <Surface
        eyebrow={glossary("Known Failure Modes", "failure_modes")}
        title="When this strategy misses"
        pill={<Pill tone="warn">{failures.length} documented</Pill>}
      >
        <HonestRows
          values={failures}
          empty="No known failure modes recorded for this strategy. The model definition has not listed scenarios where it tends to underperform."
          tone="warn"
          attrs="data-active-strategy-failure-list"
        />
      </Surface>
      <Surface
        eyebrow={glossary("AI Role", "ai_role")}
        title="What the copilot helps with"
        pill={<Pill tone="ai">advisory only</Pill>}
      >
        <HonestRows
          values={aiRoles}
          empty="No AI assistance described for this strategy. The copilot is not currently advising on any part of the decision loop."
          tone="ai"
          attrs="data-active-strategy-ai-role-list"
        />
      </Surface>
    </div>
  );
}

function PaperHero({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const positions = positionsFrom(snapshot);
  const label = positions.length === 1 ? "open position" : "open positions";
  return (
    <section className="hero" aria-label="Paper holdings">
      <div className="hero__lead">
        <span className="hero__label">Holdings</span>
        <div className="hero__value">
          <span data-field="position-count">{positions.length}</span>
        </div>
        <div className="hero__delta">
          <span>{label} held</span>
          <span className="delta-divider">·</span>
          <span>fake-money ledger</span>
        </div>
      </div>
      <p className="microcopy">Paper mode only. No live-money actions.</p>
    </section>
  );
}

function PaperStats({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const positions = positionsFrom(snapshot);
  const realized = Number(snapshot?.realized_pnl ?? 0);
  const cashDetail = snapshot?.managed_capital
    ? `Paper account cash; model target is ${money(snapshot.managed_target_equity ?? snapshot.managed_capital)}`
    : "Paper account cash available to the strategy";
  return (
    <StatRow
      ariaLabel="Paper portfolio metrics"
      stats={[
        {
          label: "Broker cash",
          value: money(snapshot?.cash),
          detail: cashDetail,
        },
        {
          label: glossary("Open orders", "open_orders"),
          value: String(snapshot?.open_orders ?? 0),
          detail: "Sent to the broker, not yet filled",
          tone: snapshot?.open_orders ? "ai" : "",
        },
        {
          label: glossary("Realized P&L", "realized_pnl"),
          value: money(snapshot?.realized_pnl),
          detail: "From positions you've already closed",
          tone: realized > 0 ? "pos" : realized < 0 ? "neg" : "",
        },
        {
          label: "Positions",
          value: String(positions.length),
          detail: "Different symbols you currently hold",
        },
      ]}
    />
  );
}

function PositionsLedger({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const positions = positionsFrom(snapshot);
  const fillsBySymbol = new Map<string, Fill[]>();
  for (const fill of snapshot?.recent_fills ?? []) {
    fillsBySymbol.set(fill.symbol, [...(fillsBySymbol.get(fill.symbol) ?? []), fill]);
  }
  return (
    <Surface
      eyebrow="Holdings ledger"
      title="Positions"
      pill={<Pill tone={positions.length ? "ai" : "ghost"}>{positions.length ? `${positions.length} held` : "FLAT"}</Pill>}
    >
      <div className="row-list" data-position-list>
        {positions.length ? (
          positions.map((position) => {
            const relatedFills = fillsBySymbol.get(position.symbol) ?? [];
            return (
              <Row
                key={position.symbol}
                primary={<strong>{position.symbol}</strong>}
                primarySub={
                  <>
                    avg <span className="mono">{money(position.average_cost)}</span>
                  </>
                }
                meta={
                  <>
                    <span className="mono">{position.quantity} sh</span>
                    <PositionSparkline position={position} fills={relatedFills} />
                  </>
                }
                value={money(String(exposureValue(position)))}
              />
            );
          })
        ) : (
          <Empty>
            No positions held yet. They will appear here after a buy order fills
            at the next daily-close window.
          </Empty>
        )}
      </div>
    </Surface>
  );
}

function RecentFills({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const fills = snapshot?.recent_fills ?? [];
  return (
    <Surface
      eyebrow="Activity"
      title={<>Recent Fills · <span data-field="fill-count" className="mono">{fills.length}</span></>}
      pill={<Pill tone={fills.length ? "ai" : "ghost"}>{fills.length} today</Pill>}
    >
      <div className="row-list" data-fill-list>
        {fills.length ? (
          fills.map((fill, index) => <FillRow fill={fill} key={fill.order_id ?? index} />)
        ) : (
          <Empty>
            No trades placed today. Strategies look for opportunities at market
            close (4pm ET) and only act when a candidate clears every safety
            check.
          </Empty>
        )}
      </div>
    </Surface>
  );
}

function OpenOrders({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const openCount = snapshot?.open_orders ?? 0;
  return (
    <Surface
      eyebrow="Activity"
      title="Open Orders"
      pill={<Pill tone={openCount ? "ai" : "ghost"}>{openCount ? `${openCount} working` : "Idle"}</Pill>}
    >
      {openCount ? (
        <div className="k-list">
          <KRow label="Working" value={<span className="mono">{openCount}</span>} />
          <KRow label="Authority" value="Daily close only" />
          <KRow label="Next window" value="scheduled" />
        </div>
      ) : (
        <Empty>
          No orders are working right now. Strategies only place orders during
          the scheduled daily-close window.
        </Empty>
      )}
      <p className="microcopy">
        Strategies place orders at the daily close window only.
      </p>
    </Surface>
  );
}

function StatementReview({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const report = snapshot?.statement_reconciliation;
  const statement = recordValue(report?.statement);
  const issues = arrayValue(report?.issues);
  const reconciled = Boolean(report?.reconciled);
  const hasReport = Boolean(report);
  return (
    <Surface
      eyebrow={glossary("Broker statement vs our records", "statement_review")}
      title={<span data-field="statement-status">{hasReport ? (reconciled ? "Reconciled" : "Mismatch") : "Awaiting Statement"}</span>}
      pill={
        <span className={`pill pill--${hasReport ? (reconciled ? "good" : "danger") : "warn"}`} data-field="statement-chip">
          {hasReport ? (reconciled ? "Clean" : "Review") : "Post-run"}
        </span>
      }
    >
      <div className="k-list">
        <KRow label="Statement" value={<span data-field="statement-id" className="mono">{stringValue(statement.statement_id, "not loaded")}</span>} />
        <KRow label="Provider" value={<span data-field="statement-provider">{stringValue(statement.provider, "unknown")}</span>} />
        <KRow label="Issues" value={<span data-field="statement-issues" className="mono">{hasReport ? issues.length : "unknown"}</span>} />
        <KRow label="Report" value={<span data-field="statement-path">{snapshot?.statement_reconciliation_path ?? "not written"}</span>} />
      </div>
      <div className="row-list" data-statement-issue-list>
        {issues.length ? (
          issues.slice(0, 4).map((issue, index) => {
            const row = recordValue(issue);
            const issueType = enumText(row.issue_type, "statement_issue");
            return (
              <Row
                key={index}
                primary={<strong>{humanizeCode(issueType.toLowerCase())}</strong>}
                primarySub={stringValue(row.message, "Statement mismatch requires review.")}
                meta={stringValue(row.symbol, "account")}
                tone="danger"
              />
            );
          })
        ) : (
          <Empty>No statement differences above tolerance.</Empty>
        )}
      </div>
      <p className="microcopy" data-field="statement-caveat">
        Paper/research-only review. Not filing-grade tax accounting.
      </p>
    </Surface>
  );
}

function AuditTrail({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const report = snapshot?.daily_report;
  const metadata = report?.report_metadata;
  const evidenceSources = metadata?.evidence_sources?.length ?? 0;
  const tracedOrders =
    report?.trade_explanations?.filter((trade) => Boolean(trade.ledger_trace))
      .length ?? 0;
  return (
    <Surface
      eyebrow={glossary("Where the numbers came from", "audit_trail")}
      title="Audit Trail"
      pill={<Pill tone="ai">{evidenceSources} sources</Pill>}
    >
      <div className="k-list">
        <KRow label="Fills traced" value={<span className="mono">{report?.fill_report?.length ?? 0}</span>} />
        <KRow label="Operator actions" value={<span className="mono">{report?.operator_actions?.length ?? 0}</span>} />
        <KRow label="Runtime events" value={<span className="mono">{report?.runtime_events?.length ?? 0}</span>} />
        <KRow label="Trace coverage" value={<span className="mono">{tracedOrders}</span>} />
        <KRow label="Benchmark" value={benchmarkStatus(report)} />
      </div>
    </Surface>
  );
}

function TaxEstimate({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const tax = snapshot?.daily_report?.tax_report;
  const available = Boolean(tax?.tax_estimate_available);
  return (
    <Surface
      eyebrow="Accounting"
      title={glossary("Tax Estimate", "accounting")}
      pill={<span className={`pill pill--${available ? "good" : "ghost"}`} data-field="tax-estimate-state">{available ? "available" : "estimate only"}</span>}
    >
      <div className="k-split">
        <div className="k-list">
          <KRow label={glossary("Open lots", "tax_lots")} value={<span data-field="tax-active-lots" className="mono">{tax?.active_lot_count ?? 0}</span>} />
          <KRow label="Closed lots" value={<span data-field="tax-realized-lots" className="mono">{tax?.realized_lot_count ?? 0}</span>} />
          <KRow label={glossary("Lot method", "fifo")} value={<span data-field="tax-lot-method" className="mono">{enumText(tax?.lot_method, "fifo").toUpperCase()}</span>} />
          <KRow label="Estimated tax" value={<span data-field="tax-estimated-tax">{available ? money(tax?.estimated_tax) : "unavailable"}</span>} />
        </div>
        <div className="k-list">
          <KRow label={glossary("Short-term gains", "short_long_term")} value={<span data-field="tax-short-term-gains">{money(tax?.short_term_realized_gains)}</span>} />
          <KRow label="Long-term gains" value={<span data-field="tax-long-term-gains">{money(tax?.long_term_realized_gains)}</span>} />
          <KRow label="Total gains" value={<span data-field="tax-total-gains">{money(tax?.total_realized_gains)}</span>} />
        </div>
      </div>
      <p className="microcopy">Research estimate only. Not filing-grade tax accounting.</p>
    </Surface>
  );
}

function ResearchHero({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const nightly = snapshot?.nightly_learning;
  const comparison = nightly?.comparisons?.[0];
  const championScore = Number(comparison?.champion_score ?? 0);
  const challengerScore = Number(comparison?.challenger_score ?? 0);
  const delta = challengerScore - championScore;
  const confidence = nightly?.recommendations?.[0]?.confidence;
  const waiting = !nightly?.recommendations?.length;
  return (
    <section className="hero" aria-label="Nightly Learning">
      <div className="hero__lead">
        <span className="hero__label">{glossary("Nightly Learning", "nightly_learning")}</span>
        <div className="hero__value mono">
          <span className={delta >= 0 ? "ai-c" : "neg"}>{delta >= 0 ? "+" : ""}{delta.toFixed(4)}</span>
        </div>
        <div className="hero__delta">
          <span>{glossary("Score delta", "score_delta")} · how much better the candidate looks</span>
          <span className="delta-divider">·</span>
          <span>current {championScore.toFixed(4)} · candidate {challengerScore.toFixed(4)}</span>
          <span className="delta-divider">·</span>
          <Pill tone={waiting ? "ghost" : "ai"}>{waiting ? "Awaiting nightly run" : "Observed, not promoted"}</Pill>
        </div>
      </div>
      <div aria-label="Champion challenger comparison">
        <ScoreDuel
          leftLabel="Champion"
          leftValue={championScore}
          rightLabel="Challenger"
          rightValue={challengerScore}
        />
      </div>
      <div hidden aria-hidden="true">
        <BarCompare
          leftLabel="Champion"
          leftValue={championScore}
          rightLabel="Challenger"
          rightValue={challengerScore}
        />
      </div>
      <div className="hero__delta">
        <span className="eyebrow">AI Copilot</span>
        <Confidence score={confidence} />
        <span className="delta-divider">·</span>
        <span>manual review is required before any model authority changes.</span>
      </div>
      <span className="hide-in-tech" hidden>AI copilot confidence</span>
      <p className="microcopy">
        {waiting
          ? "AI copilot is waiting for evidence. AI copilot confidence will surface here once a nightly run completes - manual review is required before any model authority changes."
          : `AI copilot confidence ${confidence?.toFixed(2) ?? "0.00"}; manual review is required before any model authority changes.`}
      </p>
    </section>
  );
}

function LearningLoopStatus({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const cycle = snapshot?.autonomous_learning;
  const service = snapshot?.autonomous_learning_service;
  const leader = cycle?.top_candidates?.[0];
  const status = cycle?.status ?? "waiting";
  const serviceStatus = service?.service_status ?? "not running";
  const serviceLive = serviceStatus === "idle" ||
    serviceStatus === "running" ||
    serviceStatus === "running_cycle";
  const tone =
    status === "completed"
      ? "good"
      : status === "failed"
        ? "danger"
        : status === "blocked"
          ? "warn"
          : "ghost";
  return (
    <Surface
      eyebrow="Self-Feeding Loop"
      title={
        <span data-field="autonomous-learning-status">
          {cycle ? `Autonomous cycle · ${status}` : "Autonomous cycle · waiting"}
        </span>
      }
      pill={<Pill tone={tone}>{cycle ? status : "waiting"}</Pill>}
    >
      <div className="k-list">
        <KRow
          label="Service"
          value={
            <ServiceStateIndicator
              live={serviceLive}
              status={serviceStatus}
            />
          }
        />
        <KRow
          label="Heartbeat"
          value={
            <span data-field="autonomous-learning-heartbeat">
              {formatIso(service?.heartbeat_at)}
            </span>
          }
        />
        <KRow
          label="Current task"
          value={
            <span data-field="autonomous-learning-task">
              {humanizeCode(service?.current_task ?? "idle")}
            </span>
          }
        />
        <KRow
          label="Current hypothesis"
          value={
            <span data-field="autonomous-learning-current-hypothesis">
              {humanizeCode(
                service?.current_historical_hypothesis_id ?? "none",
              )}
            </span>
          }
        />
        <KRow
          label="Current lane"
          value={
            <span data-field="autonomous-learning-current-lane">
              {humanizeCode(service?.current_historical_lane ?? "idle")}
            </span>
          }
        />
        <KRow
          label="Last hypothesis"
          value={
            <span data-field="autonomous-learning-last-hypothesis">
              {humanizeCode(
                service?.last_historical_hypothesis_id ??
                  cycle?.hypothesis_id ??
                  "none",
              )}
            </span>
          }
        />
        <KRow
          label="Next hypothesis"
          value={
            <span data-field="autonomous-learning-next-hypothesis">
              {humanizeCode(
                service?.next_historical_hypothesis_id ?? "pending",
              )}
            </span>
          }
        />
        <KRow
          label="Next lane"
          value={
            <span data-field="autonomous-learning-next-lane">
              {humanizeCode(service?.next_historical_lane ?? "pending")}
            </span>
          }
        />
        <KRow
          label="Last run"
          value={
            <span data-field="autonomous-learning-run">
              {cycle?.run_id ?? "not run"}
            </span>
          }
        />
        <KRow
          label="Candidate rows"
          value={
            <span className="mono" data-field="autonomous-learning-candidates">
              {numberValue(cycle?.candidate_count, 0)}
            </span>
          }
        />
        <KRow
          label="Leader"
          value={
            <span data-field="autonomous-learning-leader">
              {leader?.model_key ?? cycle?.recommended_challenger_model_key ?? "none"}
            </span>
          }
        />
        <KRow
          label="Full delta"
          value={
            <span
              className={numberValue(leader?.full_delta, 0) >= 0 ? "pos" : "neg"}
              data-field="autonomous-learning-delta"
            >
              {percentValue(leader?.full_delta)}
            </span>
          }
        />
        <KRow
          label="Manual approval"
          value={
            <span data-field="autonomous-learning-approval">
              {yesNo(Boolean(cycle?.manual_approval_required ?? true))}
            </span>
          }
        />
        <KRow
          label="Promotion gate"
          value={
            <span data-field="autonomous-learning-promotion-gate">
              {humanizeCode(service?.promotion_gate?.status ?? "waiting")}
            </span>
          }
        />
        <KRow
          label="Next historical"
          value={
            <span data-field="autonomous-learning-next-historical">
              {formatIso(service?.next_historical_experiment_due_at ?? undefined)}
            </span>
          }
        />
        <KRow
          label="Next fresh"
          value={
            <span data-field="autonomous-learning-next-fresh">
              {formatIso(service?.next_fresh_market_data_due_at ?? undefined)}
            </span>
          }
        />
        <KRow
          label="Report"
          value={
            <span data-field="autonomous-learning-report">
              {cycle?.artifact_paths?.markdown ?? "not written"}
            </span>
          }
        />
      </div>
      <p className="microcopy" data-field="autonomous-learning-summary">
        {service?.policy_summary ??
          cycle?.summary ??
          "The self-feeding learning loop has not produced a cycle report yet."}
      </p>
      {cycle?.next_actions?.length ? (
        <div className="row-list" data-autonomous-learning-actions>
          {cycle.next_actions.slice(0, 3).map((action, index) => (
            <Row
              key={`${index}-${action}`}
              primary={<strong>Next action</strong>}
              primarySub={action}
            />
          ))}
        </div>
      ) : null}
    </Surface>
  );
}

function CandidateReadiness({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const readiness = snapshot?.autonomous_learning?.candidate_readiness;
  const artifacts = snapshot?.autonomous_learning?.artifact_paths ?? {};
  const promotionQualified = readiness?.promotion_qualified ?? [];
  const rawAlpha = readiness?.raw_alpha_watchlist ?? [];
  const lowDrawdown = readiness?.low_drawdown_watchlist ?? [];
  const fragile = readiness?.fragile_watchlist ?? [];
  const pilotStatus = readiness?.pilot_status ?? "research_only";
  const pilotCandidate = readiness?.pilot_candidate_model_key ?? "none";
  const topQualified = promotionQualified[0];
  const topRawAlpha = rawAlpha[0];
  return (
    <Surface
      eyebrow="Friday Readiness"
      title="Candidate readiness"
      pill={
        <Pill tone={pilotStatus === "manual_pilot_review_eligible" ? "warn" : "ai"}>
          {humanizeCode(pilotStatus)}
        </Pill>
      }
    >
      <div className="grid-2">
        <div className="k-list">
          <KRow
            label="Pilot candidate"
            value={<span className="mono">{pilotCandidate}</span>}
          />
          <KRow
            label="Promotion qualified"
            value={<span className="mono">{promotionQualified.length}</span>}
          />
          <KRow
            label="Raw alpha watchlist"
            value={<span className="mono">{rawAlpha.length}</span>}
          />
          <KRow
            label="Low drawdown watchlist"
            value={<span className="mono">{lowDrawdown.length}</span>}
          />
          <KRow
            label="Fragile watchlist"
            value={<span className="mono">{fragile.length}</span>}
          />
          <KRow
            label="Readiness report"
            value={<span>{artifacts.candidate_readiness_markdown ?? "not written"}</span>}
          />
        </div>
        <div className="k-list">
          <KRow
            label="Best qualified"
            value={<span className="mono">{topQualified?.model_key ?? "none"}</span>}
          />
          <KRow
            label="Qualified delta"
            value={
              <span className={toneClass(topQualified?.full_delta)}>
                {percentValue(topQualified?.full_delta)}
              </span>
            }
          />
          <KRow
            label="Best raw alpha"
            value={<span className="mono">{topRawAlpha?.model_key ?? "none"}</span>}
          />
          <KRow
            label="Raw alpha delta"
            value={
              <span className={toneClass(topRawAlpha?.full_delta)}>
                {percentValue(topRawAlpha?.full_delta)}
              </span>
            }
          />
          <KRow
            label="Raw alpha fold"
            value={percentValue(topRawAlpha?.min_fold_delta)}
          />
          <KRow
            label="Experiment queue"
            value={<span>{artifacts.experiment_queue_markdown ?? "not written"}</span>}
          />
        </div>
      </div>
      <p className="microcopy">
        {readiness?.summary ?? "No candidate-readiness report has been written yet."}
      </p>
    </Surface>
  );
}

function ResearchMemo({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const nightly = snapshot?.nightly_learning;
  const confidence = nightly?.recommendations?.[0]?.confidence;
  const recCount = nightly?.recommendations?.length ?? 0;
  const activeState = nightly ? (nightly.active_model_unchanged ? "unchanged" : "review") : "unchanged";
  return (
    <Surface
      eyebrow={glossary("Lab Notebook", "research_memo")}
      title="Research Memo · Active model unchanged"
      pill={<Pill tone={nightly ? (nightly.active_model_unchanged ? "good" : "warn") : "ghost"}>{nightly ? "No active mutation" : "Awaiting evidence"}</Pill>}
    >
      <div className="memo">
        {nightly?.research_memo ??
          "Nightly learning has not run yet for this always-on session. The active paper model remains locked under operator authority."}
        <small>Research only · active model unchanged · operator approval required</small>
      </div>
      <div className="k-list">
        <KRow label={glossary("AI confidence", "ai_confidence")} value={<Confidence score={confidence} />} />
        <KRow label="Active model state" value={<span className={activeState === "unchanged" ? "pos" : "warn-c"}>{activeState}</span>} />
        <KRow label="Recommendations" value={<span className="mono">{recCount}</span>} />
      </div>
    </Surface>
  );
}

function WalkForwardStrip({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const nightly = snapshot?.nightly_learning;
  const championSeries = scoresFromEvaluation(nightly?.champion_evaluation);
  if (championSeries.length < 2 || !nightly?.champion_evaluation) {
    return null;
  }
  const challenger = nightly.candidate_evaluations?.[0];
  const challengerSeries = scoresFromEvaluation(challenger);
  return (
    <section className="stat-row" aria-label="Walk-forward score trends">
      <WalkForwardCard
        label="Champion walk-forward"
        sub={modelKey(nightly.champion_evaluation.model)}
        series={championSeries}
        aggregate={Number(nightly.champion_evaluation.aggregate_score ?? 0)}
      />
      {challenger && challengerSeries.length >= 2 ? (
        <WalkForwardCard
          label="Challenger walk-forward"
          sub={modelKey(challenger.model)}
          series={challengerSeries}
          aggregate={Number(challenger.aggregate_score ?? 0)}
        />
      ) : null}
      <div className="stat stat--ai">
        <div className="stat__label">Fold coverage</div>
        <div className="stat__value">
          <span className="mono">{championSeries.length}</span>
        </div>
        <div className="stat__detail">Walk-forward folds evaluated tonight</div>
      </div>
    </section>
  );
}

function SystemHealth({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const health = snapshot?.health_report;
  const checks = health?.checks ?? [];
  const incidents = health?.incidents ?? [];
  const healthStatus = health?.status ?? "unknown";
  const tone = healthTone(healthStatus);
  return (
    <Surface
      eyebrow="Runtime Health"
      title={<>System health · <span data-field="health-status">{healthStatus}</span></>}
      pill={<span className={`pill pill--${tone}`} data-field="health-incident-count">{incidents.length === 1 ? "1 incident" : `${incidents.length} incidents`}</span>}
    >
      <p className="surface__summary" data-field="health-summary">
        {health?.summary ?? "No runtime health report attached."}
      </p>
      <p className="microcopy" data-field="health-report-path">
        Incident review: {snapshot?.health_report_path ?? "not written"}
      </p>
      <div className="grid-2">
        <div>
          <div className="k-row">
            <span>Health Checks</span>
            <strong data-numeric="1">{checks.length}</strong>
          </div>
          <div className="row-list" data-health-check-list>
            {checks.length ? (
              checks.map((check) => (
                <Row
                  primary={<strong>{check.name}</strong>}
                  primarySub={check.message}
                  value={check.status}
                  valueTone={check.status === "healthy" ? "pos" : check.status === "degraded" ? "warn" : "neg"}
                  key={check.name}
                />
              ))
            ) : (
              <Empty>
                No health checks have run yet. They will appear here once the
                daily runtime cycle completes its system probes.
              </Empty>
            )}
          </div>
        </div>
        <div>
          <div className="k-row">
            <span>{glossary("Active incidents", "incident_command")}</span>
            <strong data-numeric="1">{incidents.length}</strong>
          </div>
          <div className="row-list" data-incident-list>
            {incidents.length ? (
              incidents.map((incident, index) => {
                const status = enumText(incident.status, "unknown");
                return (
                  <Row
                    primary={<strong>{incident.title ?? "Runtime incident"}</strong>}
                    primarySub={incident.summary ?? ""}
                    meta={status}
                    note={incident.suggested_action}
                    tone={status === "critical" ? "danger" : status === "degraded" ? "warn" : ""}
                    key={index}
                  />
                );
              })
            ) : (
              <Empty>No incidents open. The system has nothing to flag right now.</Empty>
            )}
          </div>
        </div>
      </div>
    </Surface>
  );
}

function DailyMemo({ snapshot }: { snapshot?: DashboardSnapshot }) {
  return (
    <Surface
      eyebrow="AI Daily Memo"
      title="Reviewed, paper-only"
      pill={<Pill tone="ai">REVIEWED</Pill>}
    >
      <div className="memo">
        {snapshot?.nightly_learning?.research_memo ??
          "Nightly learning has not produced a memo for this trading day yet."}
        <small>Reviewed by operator · paper authority only · no autonomous changes</small>
      </div>
    </Surface>
  );
}

function CompletionAudit({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const audit = snapshot?.completion_audit;
  const passed = Boolean(audit?.passed);
  const failed = numberValue(audit?.failed_count, 0);
  const tone = passed ? "good" : failed ? "danger" : "warn";
  return (
    <Surface
      eyebrow={glossary("Health check evidence", "functional_readiness")}
      title={<span data-field="completion-status">{stringValue(audit?.status, "Awaiting Audit")}</span>}
      pill={<span className={`pill pill--${tone}`} data-field="completion-chip">{passed ? "Ready" : audit ? "Evidence" : "Review"}</span>}
    >
      <div className="k-list">
        <KRow label="Proven" value={<span data-field="completion-proven" className="mono">{numberValue(audit?.proven_count, 0)}</span>} />
        <KRow label="Missing" value={<span data-field="completion-missing" className="mono">{audit ? numberValue(audit.missing_count, 0) : "unknown"}</span>} />
        <KRow label="Failed" value={<span data-field="completion-failed" className="mono">{audit ? numberValue(audit.failed_count, 0) : "unknown"}</span>} />
        <KRow label="External proof" value={<span data-field="completion-external" className="mono">{audit ? numberValue(audit.external_required_count, 0) : "required"}</span>} />
        <KRow label="Report path" value={<span data-field="completion-path">{stringValue(audit?.markdown_path, "not written")}</span>} />
      </div>
      <p className="microcopy" data-field="completion-summary">
        {stringValue(audit?.summary, "Run the functional completion audit after validation and soak evidence exists.")}
      </p>
    </Surface>
  );
}

function FinalAcceptance({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const report = snapshot?.final_acceptance;
  const accepted = Boolean(report?.accepted_for_functional_paper_app);
  const checks = arrayValue(report?.checks);
  const passed = checks.filter((check) => enumText(recordValue(check).status, "") === "passed").length;
  return (
    <Surface
      eyebrow={glossary("Ready for real money?", "final_acceptance")}
      title={<span data-field="final-acceptance-status">{stringValue(report?.status, "Awaiting Signoff")}</span>}
      pill={<span className={`pill pill--${accepted ? "good" : "danger"}`} data-field="final-acceptance-chip">{report ? (accepted ? "Accepted" : "Blocked") : "Not final"}</span>}
    >
      <div className="k-list">
        <KRow label="Accepted" value={<span data-field="final-acceptance-accepted">{yesNo(accepted)}</span>} />
        <KRow label="Checks" value={<span data-field="final-acceptance-checks" className="mono">{passed}/{checks.length}</span>} />
        <KRow label="Signoff" value={<span data-field="final-acceptance-signoff">{stringValue(report?.signoff_path, "missing")}</span>} />
        <KRow label="Report path" value={<span data-field="final-acceptance-path">{stringValue(report?.markdown_path, "not written")}</span>} />
      </div>
      <p className="microcopy" data-field="final-acceptance-summary">
        {stringValue(report?.summary, "Run final acceptance after operator signoff and reviewed Alpaca Paper evidence.")}
      </p>
    </Surface>
  );
}

function ReportsAndLearning({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const nightly = snapshot?.nightly_learning;
  const activeModelUnchanged = nightly?.active_model_unchanged ?? true;
  const reportPath =
    snapshot?.runtime_state?.daily_report_path ??
    snapshot?.daily_report?.report_metadata?.report_path ??
    "not written";
  return (
    <Surface
      eyebrow={glossary("Daily report status", "reports_and_learning")}
      title={<span data-field="report-status">{reportHeading(snapshot)}</span>}
      pill={<Pill tone={activeModelUnchanged ? "ai" : "warn"}>{activeModelUnchanged ? "Model locked" : "Mutation pending"}</Pill>}
    >
      <div className="k-list">
        <KRow label="Daily report" value={<span data-field="daily-report-state">{reportPath !== "not written" ? "written" : "snapshot"}</span>} />
        <KRow label="Report path" value={<span data-field="daily-report-path">{reportPath}</span>} />
        <KRow label="Trading day" value={<span data-field="trading-day" className="mono">{snapshot?.daily_report?.trading_day ?? "unknown"}</span>} />
        <KRow label="Nightly learning" value={<span data-field="learning-state">{nightly ? "complete" : "waiting"}</span>} />
        <KRow label="Learning memo" value={<span data-field="learning-memo-path">{snapshot?.nightly_learning_path ?? "not written"}</span>} />
        <KRow label="Active mutation" value={<span data-field="active-mutation-state">{activeModelUnchanged ? "blocked" : "review"}</span>} />
      </div>
    </Surface>
  );
}

function LiveReadiness({ snapshot }: { snapshot?: DashboardSnapshot }) {
  const report = snapshot?.live_readiness;
  const checks = arrayValue(report?.checks);
  const passed = checks.filter((check) => Boolean(recordValue(check).passed)).length;
  const limits = recordValue(report?.limits);
  const approved = arrayValue(report?.approved_model_keys);
  return (
    <Surface
      eyebrow={glossary("Ready for live trading?", "live_readiness")}
      title={<span data-field="live-readiness-panel-status">{stringValue(report?.status, "disabled")}</span>}
      pill={<Pill tone="warn">Live disabled</Pill>}
    >
      <div className="k-list">
        <KRow label="Checks passed" value={<span data-field="live-readiness-checks" className="mono">{passed}/{checks.length}</span>} />
        <KRow label="Max order" value={<span data-field="live-max-order" className="mono">{report ? money(stringValue(limits.max_order_notional, "0")) : "unavailable"}</span>} />
        <KRow label="Approved models" value={<span data-field="live-approved-models" className="mono">{approved.length}</span>} />
      </div>
      <div className="surface__foot">
        Live trading is intentionally off. The copilot has no path to enable it.
      </div>
    </Surface>
  );
}

function ControlButton({
  action,
  label,
  disabled = false,
  danger = false,
  pendingAction,
  onControl,
}: {
  action: OperatorControlAction;
  label: string;
  disabled?: boolean;
  danger?: boolean;
  pendingAction: OperatorControlAction | null;
  onControl: (action: OperatorControlAction) => Promise<void>;
}) {
  const pending = pendingAction === action;
  return (
    <button
      className={danger ? "btn btn--danger" : "btn"}
      data-control-action={action}
      disabled={disabled || pendingAction !== null}
      type="button"
      onClick={() => void onControl(action)}
    >
      {pending ? "Sending..." : label}
    </button>
  );
}

function LiveControlButton({
  action,
  label,
  disabled = false,
  danger = false,
  pendingAction,
  onControl,
}: {
  action: LiveSandboxControlAction;
  label: string;
  disabled?: boolean;
  danger?: boolean;
  pendingAction: LiveSandboxControlAction | null;
  onControl: (action: LiveSandboxControlAction) => Promise<void>;
}) {
  const pending = pendingAction === action;
  return (
    <button
      className={danger ? "btn btn--danger" : "btn"}
      data-live-control-action={action}
      disabled={disabled || pendingAction !== null}
      type="button"
      onClick={() => void onControl(action)}
    >
      {pending ? "Sending..." : label}
    </button>
  );
}

function HonestRows({
  values,
  empty,
  tone,
  attrs,
}: {
  values: string[];
  empty: string;
  tone: string;
  attrs: string;
}) {
  const attrName = attrs.split("=")[0];
  return (
    <div className="row-list" {...{ [attrName]: "" }}>
      {values.length ? (
        values.map((value) => (
          <Row primary={<small>{value}</small>} tone={tone} key={value} />
        ))
      ) : (
        <Empty>{empty}</Empty>
      )}
    </div>
  );
}

function ScoreDuel({
  leftLabel,
  leftValue,
  rightLabel,
  rightValue,
}: {
  leftLabel: string;
  leftValue: number;
  rightLabel: string;
  rightValue: number;
}) {
  const delta = rightValue - leftValue;
  const absMax = Math.max(Math.abs(leftValue), Math.abs(rightValue), 0.0001);
  const leftPct = (Math.abs(leftValue) / absMax) * 100;
  const rightPct = (Math.abs(rightValue) / absMax) * 100;
  const winner = delta > 0 ? "right" : delta < 0 ? "left" : "";
  return (
    <div className="duel" role="img" aria-label="Score comparison">
      <div
        className={`duel__side duel__side--left ${winner === "left" ? "duel__side--winner" : ""}`}
      >
        <div className="duel__label">{leftLabel}</div>
        <div className="duel__score mono">{leftValue.toFixed(4)}</div>
        <div className="duel__bar">
          <div className="duel__fill duel__fill--left" style={{ width: `${leftPct.toFixed(1)}%` }} />
        </div>
      </div>
      <div className="duel__pivot">
        <div className="duel__delta-label">delta</div>
        <div className={`duel__delta ${delta > 0 ? "pos" : delta < 0 ? "neg" : ""} mono`}>
          {delta >= 0 ? "+" : ""}
          {delta.toFixed(4)}
        </div>
        <div className="duel__hint">
          {delta === 0 ? "no change" : `${winner === "left" ? leftLabel : rightLabel} leads`}
        </div>
      </div>
      <div
        className={`duel__side duel__side--right ${winner === "right" ? "duel__side--winner" : ""}`}
      >
        <div className="duel__label">{rightLabel}</div>
        <div className="duel__score mono">{rightValue.toFixed(4)}</div>
        <div className="duel__bar">
          <div className="duel__fill duel__fill--right" style={{ width: `${rightPct.toFixed(1)}%` }} />
        </div>
      </div>
    </div>
  );
}

function BarCompare({
  leftLabel,
  leftValue,
  rightLabel,
  rightValue,
}: {
  leftLabel: string;
  leftValue: number;
  rightLabel: string;
  rightValue: number;
}) {
  const values = [leftValue, rightValue];
  const absMax = Math.max(...values.map((value) => Math.abs(value)), 1);
  const hasNegative = values.some((value) => value < 0);
  const hasPositive = values.some((value) => value > 0);
  const baselineY = hasNegative && hasPositive ? 63 : hasNegative ? 18 : 110;
  const maxH = hasNegative && hasPositive ? 42 : hasNegative ? 80 : 88;
  return (
    <svg
      className="bar-compare"
      viewBox="0 0 200 140"
      role="img"
      aria-label="Champion challenger comparison"
      preserveAspectRatio="xMidYMid meet"
    >
      <line className="bar-baseline" x1="20" x2="180" y1={baselineY} y2={baselineY} />
      <g className="bar-chart">
        {[
          [leftLabel, leftValue, "bar bar-champ", 30],
          [rightLabel, rightValue, "bar bar-chal", 120],
        ].map(([label, rawValue, klass, rawX]) => {
          const value = Number(rawValue);
          const x = Number(rawX);
          const height = Math.max((Math.abs(value) / absMax) * maxH, 6);
          const y = value >= 0 ? baselineY - height : baselineY;
          const valueY = value >= 0 ? Math.max(11, y - 6) : Math.min(124, baselineY + height + 12);
          return (
            <g key={String(label)}>
              <rect className={String(klass)} x={x} y={y} width="50" height={height} rx="3" />
              <text className="bar-value" x={x + 25} y={valueY} textAnchor="middle">
                {value >= 0 ? "+" : ""}
                {value.toFixed(4)}
              </text>
              <text className="bar-label" x={x + 25} y="135" textAnchor="middle">
                {String(label)}
              </text>
            </g>
          );
        })}
      </g>
    </svg>
  );
}

function PositionSparkline({
  position,
  fills,
}: {
  position: Position;
  fills: Fill[];
}) {
  if (!fills.length) {
    return null;
  }
  const avg = Number(position.average_cost ?? 0);
  const latest = Number(fills[fills.length - 1]?.price ?? avg);
  const midpoint = (avg + latest) / 2;
  return (
    <>
      {" "}
      <span className="mono">
        <Sparkline
          values={[avg, (avg + midpoint) / 2, midpoint, (midpoint + latest) / 2, latest]}
          positive={latest >= avg}
          label={`${position.symbol} trend`}
        />
      </span>
    </>
  );
}

function FillRow({ fill }: { fill: Fill }) {
  const side = enumText(fill.side, "BUY").toUpperCase();
  return (
    <Row
      primary={<strong>{fill.symbol}</strong>}
      primarySub={fill.filled_at}
      meta={<Pill tone={side === "BUY" ? "good" : "danger"}>{side}</Pill>}
      value={<span className="mono">{fill.quantity} @ {money(fill.price)}</span>}
      valueTone={side === "BUY" ? "pos" : "neg"}
    />
  );
}

function WalkForwardCard({
  label,
  sub,
  series,
  aggregate,
}: {
  label: string;
  sub: string;
  series: number[];
  aggregate: number;
}) {
  const positive = aggregate >= 0;
  return (
    <div className="stat stat--with-spark">
      <div className="stat__label">{label}</div>
      <div className={`stat__value ${positive ? "pos" : "neg"}`} style={{ fontSize: "var(--t-h2)" }}>
        {aggregate >= 0 ? "+" : ""}
        {aggregate.toFixed(4)}
      </div>
      <Sparkline
        values={series}
        positive={positive}
        label={`${label} fold scores`}
        width={240}
        height={44}
        extraClass="spark--wide"
      />
      <div className="stat__detail">{sub}</div>
    </div>
  );
}

function Sparkline({
  values,
  positive = true,
  label = "trend",
  width = 80,
  height = 28,
  extraClass = "",
}: {
  values: number[];
  positive?: boolean;
  label?: string;
  width?: number;
  height?: number;
  extraClass?: string;
}) {
  const points = chartPoints(values, width, height, 2);
  const klass = `spark ${extraClass}`.trim();
  if (!points.length) {
    return <svg className={klass} viewBox={`0 0 ${width} ${height}`} aria-label={label} />;
  }
  const linePath = `M ${points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" L ")}`;
  const baselineY = height - 2;
  const areaPath = `${linePath} L ${points[points.length - 1][0].toFixed(1)} ${baselineY} L 2 ${baselineY} Z`;
  const dot = points[points.length - 1];
  const seriesClass = positive ? "pos" : "neg";
  return (
    <svg
      className={klass}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={label}
    >
      <path d={areaPath} className={`spark-fill ${seriesClass}`} />
      <path d={linePath} className={seriesClass} />
      <circle className={`spark-dot ${seriesClass}`} cx={dot[0]} cy={dot[1]} r="1.8" />
    </svg>
  );
}

function Confidence({ score }: { score?: number }) {
  const filled = score === undefined ? 0 : Math.max(0, Math.min(5, Math.round(score * 5)));
  const band = confidenceBand(score);
  return (
    <span className="confidence">
      <span className="conf-dots" aria-label="confidence">
        {[0, 1, 2, 3, 4].map((dot) => (
          <span className={dot < filled ? "on" : ""} key={dot} />
        ))}
      </span>{" "}
      <span className={`confidence__band ${confidenceBandClass(score)}`}>{band}</span>{" "}
      <span className="confidence__score mono">· {score === undefined ? "—" : score.toFixed(2)}</span>{" "}
      {glossary("", "ai_confidence")}
    </span>
  );
}

function Surface({
  eyebrow,
  title,
  pill,
  children,
  extraClass = "",
}: {
  eyebrow: React.ReactNode;
  title: React.ReactNode;
  pill?: React.ReactNode;
  children: React.ReactNode;
  extraClass?: string;
}) {
  const className = `surface ${extraClass}`.trim();
  return (
    <article className={className}>
      <div className="surface__head">
        <div className="surface__title">
          <span className="eyebrow">{eyebrow}</span>
          <h2>{title}</h2>
        </div>
        {pill}
      </div>
      <div className="surface__body">{children}</div>
    </article>
  );
}

function StatRow({
  stats,
  ariaLabel,
}: {
  stats: {
    label: React.ReactNode;
    value: React.ReactNode;
    detail: React.ReactNode;
    tone?: string;
  }[];
  ariaLabel: string;
}) {
  return (
    <section className="stat-row" aria-label={ariaLabel}>
      {stats.map((stat, index) => (
        <div className={`stat ${statClass(stat.tone)}`.trim()} key={index}>
          <div className="stat__label">{stat.label}</div>
          <div className="stat__value">{stat.value}</div>
          <div className="stat__detail">{stat.detail}</div>
        </div>
      ))}
    </section>
  );
}

function Row({
  primary,
  primarySub,
  meta,
  value,
  valueTone,
  note,
  tone,
}: {
  primary: React.ReactNode;
  primarySub?: React.ReactNode;
  meta?: React.ReactNode;
  value?: React.ReactNode;
  valueTone?: string;
  note?: React.ReactNode;
  tone?: string;
}) {
  const className = `row ${tone ? `row--${tone}` : ""} ${
    note ? "row--with-note" : ""
  }`.trim();
  return (
    <div className={className}>
      <div className="row__primary">
        {primary}
        {primarySub ? <small>{primarySub}</small> : null}
      </div>
      {meta ? <div className="row__meta">{meta}</div> : null}
      {value ? <div className={`row__value ${valueTone ?? ""}`}>{value}</div> : null}
      {note ? <div className="row__note">{note}</div> : null}
    </div>
  );
}

function KRow({
  label,
  value,
  valueClass,
}: {
  label: React.ReactNode;
  value: React.ReactNode;
  valueClass?: string;
}) {
  return (
    <div className="k-row">
      <span>{label}</span>
      <strong className={valueClass}>{value}</strong>
    </div>
  );
}

function HBar({
  label,
  value,
  maxValue,
}: {
  label: string;
  value: number;
  maxValue: number;
}) {
  const pct = Math.max(2, Math.min(100, (value / maxValue) * 100));
  return (
    <div className="h-bar">
      <span>{label}</span>
      <div className="h-bar__track">
        <div className="h-bar__fill" style={{ width: `${pct.toFixed(1)}%` }} />
      </div>
      <span className="h-bar__amt">{value.toLocaleString("en-US")}</span>
    </div>
  );
}

function Pill({
  tone,
  children,
}: {
  tone: string;
  children: React.ReactNode;
}) {
  return <span className={`pill pill--${pillTone(tone)}`}>{children}</span>;
}

function ServiceStateIndicator({
  live,
  status,
}: {
  live: boolean;
  status: string;
}) {
  const label = live
    ? "Autonomous learning service is running"
    : "Autonomous learning service is not running";
  return (
    <span
      aria-label={label}
      className={`service-state ${live ? "service-state--live" : "service-state--off"}`}
      data-field="autonomous-learning-service"
    >
      <span aria-hidden="true" className="service-state__dot" />
      <span>{humanizeCode(status)}</span>
    </span>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="empty">{children}</p>;
}

function Notice({
  title,
  message,
  tone,
}: {
  title: string;
  message: string;
  tone: "ai" | "danger";
}) {
  return (
    <article className="surface">
      <div className="surface__head">
        <div className="surface__title">
          <span className="eyebrow">{title}</span>
          <h2>{message}</h2>
        </div>
        <Pill tone={tone}>{tone === "danger" ? "ERROR" : "OK"}</Pill>
      </div>
    </article>
  );
}

const TOUR_STEPS = [
  {
    target: "[data-tour-anchor='hero']",
    title: "Your simulated portfolio",
    body: "This big number is your total - cash plus the value of every position you hold. It's all simulated. No real account is touched.",
  },
  {
    target: "[data-tour-anchor='mode']",
    title: "You're always in paper mode",
    body: "This badge sits in the top bar on every screen. It exists so you can never confuse a practice trade for a real one.",
  },
  {
    target: "[data-tour-anchor='kill']",
    title: "The kill switch stops everything",
    body: "The kill switch stops all paper trading. It cannot affect real capital because this dashboard has no live-money path.",
  },
];

function TourOverlay({
  open,
  step,
  onNext,
  onClose,
}: {
  open: boolean;
  step: number;
  onNext: () => void;
  onClose: () => void;
}) {
  const cardRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const item = TOUR_STEPS[step];
    if (!item) return;
    const target = document.querySelector<HTMLElement>(item.target);
    const card = cardRef.current;

    // Clear any prior spotlight, then highlight the current target and pin
    // the card to the same horizontal half so the user's eye finds both.
    document
      .querySelectorAll<HTMLElement>("[data-tour-spotlight]")
      .forEach((el) => {
        delete el.dataset.tourSpotlight;
      });

    if (!target || !card) return;
    target.dataset.tourSpotlight = "1";
    if (typeof target.scrollIntoView === "function") {
      target.scrollIntoView({ block: "center", behavior: "smooth" });
    }

    const rect = target.getBoundingClientRect();
    const onLeftHalf = rect.left + rect.width / 2 < window.innerWidth / 2;
    card.style.bottom = "24px";
    card.style.top = "auto";
    if (onLeftHalf) {
      card.style.left = "24px";
      card.style.right = "auto";
    } else {
      card.style.right = "24px";
      card.style.left = "auto";
    }

    return () => {
      delete target.dataset.tourSpotlight;
    };
  }, [open, step]);

  // Force-clear spotlights when the tour closes entirely.
  useEffect(() => {
    if (open) return;
    document
      .querySelectorAll<HTMLElement>("[data-tour-spotlight]")
      .forEach((el) => {
        delete el.dataset.tourSpotlight;
      });
  }, [open]);

  return (
    <div className="tour" data-tour hidden={!open} aria-hidden={!open}>
      <div className="tour__backdrop" data-tour-skip onClick={onClose} />
      {TOUR_STEPS.map((item, index) => {
        const active = index === step;
        return (
          <article
            ref={active ? cardRef : undefined}
            className="tour__card"
            data-tour-step={index + 1}
            data-tour-target={item.target}
            hidden={!active}
            key={item.title}
          >
            <header className="tour__head">
              <span className="eyebrow">Step {index + 1} of {TOUR_STEPS.length}</span>
              <button type="button" className="tour__skip" data-tour-skip aria-label="Skip tour" onClick={onClose}>×</button>
            </header>
            <h3>{item.title}</h3>
            <p>{item.body}</p>
            <footer className="tour__actions">
              <button type="button" className="tour__btn tour__btn--ghost" data-tour-skip onClick={onClose}>Skip tour</button>
              <button type="button" className="tour__btn tour__btn--primary" data-tour-next onClick={onNext}>
                {index === TOUR_STEPS.length - 1 ? "Done" : "Next"}
              </button>
            </footer>
          </article>
        );
      })}
    </div>
  );
}

function WhatsThisPanel({
  open,
  screen,
  onClose,
}: {
  open: boolean;
  screen: ScreenKey;
  onClose: () => void;
}) {
  const terms = glossaryTermsForScreen(screen);
  return (
    <aside
      className="whats-this"
      data-whats-this
      data-state={open ? "open" : "closed"}
      hidden={!open}
      aria-hidden={!open}
      aria-label="Glossary for this screen"
    >
      <div className="whats-this__backdrop" data-whats-this-close onClick={onClose} />
      <div className="whats-this__panel">
        <header className="whats-this__head">
          <div>
            <span className="whats-this__eyebrow">What&apos;s on this screen</span>
            <h3 className="whats-this__title" data-whats-this-title>{SCREEN_TITLES[screen]}</h3>
          </div>
          <button type="button" className="whats-this__close" data-whats-this-close aria-label="Close glossary panel" onClick={onClose}>×</button>
        </header>
        <div className="whats-this__body" data-whats-this-body>
          {terms.length ? (
            terms.map(([key, entry]) => (
              <div className="row" key={key}>
                <div className="row__primary">
                  <strong className="mono">{entry.term}</strong>
                  <small>{entry.definition}</small>
                </div>
              </div>
            ))
          ) : (
            <Empty>No technical terms on this screen.</Empty>
          )}
        </div>
        <footer className="whats-this__foot">
          <p className="microcopy">Definitions on this screen update as you navigate.</p>
        </footer>
      </div>
    </aside>
  );
}

function CommandPalette({
  open,
  query,
  results,
  selectedIndex,
  onQuery,
  onClose,
  onHover,
  onActivate,
}: {
  open: boolean;
  query: string;
  results: CommandResult[];
  selectedIndex: number;
  onQuery: (value: string) => void;
  onClose: () => void;
  onHover: (index: number) => void;
  onActivate: (result: CommandResult) => void;
}) {
  return (
    <div className="cmd" data-cmd hidden={!open} role="dialog" aria-modal="true" aria-label="Command palette">
      <div className="cmd__backdrop" data-cmd-close onClick={onClose} />
      <div className="cmd__panel" role="combobox" aria-expanded="true" aria-haspopup="listbox">
        <div className="cmd__head">
          <span className="cmd__icon" aria-hidden="true">⌘K</span>
          <input
            className="cmd__input"
            data-cmd-input
            type="text"
            placeholder="Jump to a screen, term, or symbol..."
            autoComplete="off"
            spellCheck={false}
            value={query}
            onChange={(event) => onQuery(event.target.value)}
          />
          <button type="button" className="cmd__esc" data-cmd-close onClick={onClose}>Esc</button>
        </div>
        <div className="cmd__results" data-cmd-results role="listbox" aria-label="Results">
          {results.length ? (
            results.map((result, index) => (
              <button
                className="cmd__row"
                role="option"
                data-cmd-row={index}
                aria-selected={index === selectedIndex}
                type="button"
                onMouseEnter={() => onHover(index)}
                onClick={() => onActivate(result)}
                key={`${result.type}:${result.id}`}
              >
                <span className="cmd__row-main">{result.label}</span>
                <span className="cmd__row-sub">{result.sub}</span>
              </button>
            ))
          ) : (
            <div className="cmd__empty">No matches. Try a screen name, glossary term, or symbol.</div>
          )}
        </div>
        <div className="cmd__hint">
          <span><kbd>↑</kbd><kbd>↓</kbd> navigate</span>
          <span><kbd>↵</kbd> open</span>
          <span><kbd>Esc</kbd> close</span>
        </div>
      </div>
    </div>
  );
}

function ShortcutsHelp({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const rows = [
    ["⌘K / Ctrl K / /", "Open command palette"],
    ["g h", "Go Home"],
    ["g m", "Go to Models"],
    ["g p", "Go to Paper Trading"],
    ["g r", "Go to Risk"],
    ["g l", "Go to Research Lab"],
    ["g a", "Go to AI Review"],
    ["g ?", "Go to Learn"],
    ["t", "Toggle Plain / Technical"],
    ["?", "Show this help"],
    ["Esc", "Close any open panel"],
  ];
  return (
    <div className="shortcuts" data-shortcuts hidden={!open} role="dialog" aria-modal="true" aria-label="Keyboard shortcuts">
      <div className="shortcuts__backdrop" data-shortcuts-close onClick={onClose} />
      <div className="shortcuts__panel">
        <header className="shortcuts__head">
          <h3>Keyboard shortcuts</h3>
          <button type="button" className="shortcuts__close" data-shortcuts-close aria-label="Close" onClick={onClose}>×</button>
        </header>
        <div className="shortcuts__body">
          {rows.map(([keys, label]) => (
            <div className="shortcut-row" key={keys}>
              <kbd>{keys}</kbd>
              <span>{label}</span>
            </div>
          ))}
        </div>
        <footer className="shortcuts__foot">
          <p className="microcopy">Press <kbd>?</kbd> any time to reopen this list.</p>
        </footer>
      </div>
    </div>
  );
}

type PortfolioChartPoint = {
  asOf: string;
  equity: number;
  timestamp: number;
};

type PortfolioPeriod = "1D" | "1W" | "1M" | "ALL";

const PORTFOLIO_PERIODS: readonly PortfolioPeriod[] = ["1D", "1W", "1M", "ALL"];

const PORTFOLIO_PERIOD_LABELS: Record<PortfolioPeriod, string> = {
  "1D": "today",
  "1W": "this week",
  "1M": "this month",
  ALL: "all time",
};

function isPortfolioPeriod(value: unknown): value is PortfolioPeriod {
  return (
    value === "1D" || value === "1W" || value === "1M" || value === "ALL"
  );
}

function portfolioPerformance(
  snapshot: DashboardSnapshot | undefined,
  period: PortfolioPeriod = "1D",
) {
  const all = portfolioChartPoints(snapshot);
  const points = filterPortfolioChartPoints(all, period, snapshot);
  const currentEquity =
    points.at(-1)?.equity ?? numericValue(snapshot?.estimated_equity) ?? 0;
  const baseline = points.length >= 2 ? points[0].equity : currentEquity;
  const delta = currentEquity - baseline;
  const percent = baseline === 0 ? 0 : (delta / baseline) * 100;
  return {
    delta,
    percent,
    positive: delta >= 0,
    hasHistory: points.length >= 2,
    points,
    allCount: all.length,
  };
}

function portfolioChartPoints(snapshot?: DashboardSnapshot): PortfolioChartPoint[] {
  // No same-day filter — return every point in the journal so the period
  // selector on the hero can choose its own window.
  const points =
    snapshot?.portfolio_history
      ?.map((point) => {
        const equity = numericValue(point.estimated_equity);
        const timestamp = Date.parse(point.as_of);
        if (equity === undefined || !Number.isFinite(timestamp)) {
          return undefined;
        }
        return {
          asOf: point.as_of,
          equity,
          timestamp,
        };
      })
      .filter((point): point is PortfolioChartPoint => point !== undefined) ?? [];
  const currentEquity = numericValue(snapshot?.estimated_equity);
  const currentTimestamp = snapshot?.generated_at
    ? Date.parse(snapshot.generated_at)
    : Number.NaN;
  const lastPoint = points.at(-1);
  if (
    currentEquity !== undefined &&
    Number.isFinite(currentTimestamp) &&
    lastPoint?.timestamp !== currentTimestamp
  ) {
    points.push({
      asOf: snapshot?.generated_at ?? "",
      equity: currentEquity,
      timestamp: currentTimestamp,
    });
  }
  return points.sort((left, right) => left.timestamp - right.timestamp);
}

function filterPortfolioChartPoints(
  points: PortfolioChartPoint[],
  period: PortfolioPeriod,
  snapshot: DashboardSnapshot | undefined,
): PortfolioChartPoint[] {
  if (period === "ALL" || points.length === 0) return points;
  const referenceTs =
    (snapshot?.generated_at ? Date.parse(snapshot.generated_at) : Number.NaN) ||
    points[points.length - 1].timestamp;
  if (!Number.isFinite(referenceTs)) return points;

  if (period === "1D") {
    // Calendar-day boundary in market timezone, so the "today" view always
    // resets at midnight ET regardless of when the user opens the dashboard.
    const todayKey = marketDateKey(new Date(referenceTs).toISOString());
    return points.filter((point) => marketDateKey(point.asOf) === todayKey);
  }

  const dayMs = 24 * 60 * 60 * 1000;
  const windowDays = period === "1W" ? 7 : 30;
  const cutoff = referenceTs - windowDays * dayMs;
  return points.filter((point) => point.timestamp >= cutoff);
}

function EquityChart({
  points,
  positive,
}: {
  points: PortfolioChartPoint[];
  positive: boolean;
}) {
  if (points.length < 2) {
    return (
      <div
        className="hero-chart__empty"
        data-testid="hero-equity-chart"
        role="img"
        aria-label="Paper equity history unavailable"
      >
        <span>No intraday equity history yet</span>
      </div>
    );
  }
  const chartWidth = 1200;
  const chartHeight = 300;
  const mappedPoints = chartPoints(
    points.map((point) => point.equity),
    chartWidth,
    chartHeight,
    14,
  );
  const lineClass = positive ? "line-pos" : "line-neg";
  const fillClass = positive ? "fill-pos" : "fill-neg";
  const dotClass = positive ? "end-dot" : "end-dot neg";
  const linePath = `M ${mappedPoints
    .map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`)
    .join(" L ")}`;
  const baselineY = chartHeight - 2;
  const firstPoint = mappedPoints[0];
  const lastPoint = mappedPoints[mappedPoints.length - 1];
  const areaPath = `${linePath} L ${lastPoint[0].toFixed(1)} ${baselineY} L ${firstPoint[0].toFixed(1)} ${baselineY} Z`;
  return (
    <svg
      className="area-chart"
      data-testid="hero-equity-chart"
      viewBox={`0 0 ${chartWidth} ${chartHeight}`}
      preserveAspectRatio="none"
      role="img"
      aria-label="Paper equity curve from recorded dashboard snapshots"
    >
      <defs>
        <linearGradient id="fill-pos" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--pos)" stopOpacity="0.24" />
          <stop offset="100%" stopColor="var(--pos)" stopOpacity="0.02" />
        </linearGradient>
        <linearGradient id="fill-neg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--neg)" stopOpacity="0.24" />
          <stop offset="100%" stopColor="var(--neg)" stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <path d={areaPath} className={fillClass} data-equity-area />
      <path d={linePath} className={lineClass} data-equity-line />
      <circle
        className={dotClass}
        cx={lastPoint[0]}
        cy={lastPoint[1]}
        r="4"
      />
    </svg>
  );
}

type CommandResult =
  | {
      type: "screen";
      id: string;
      label: string;
      sub: string;
      screen: ScreenKey;
    }
  | {
      type: "term";
      id: string;
      label: string;
      sub: string;
      screen: ScreenKey;
    }
  | {
      type: "action";
      id: string;
      label: string;
      sub: string;
      action:
        | "toggle-vocab"
        | "cycle-theme"
        | "start-tour"
        | "open-whats-this"
        | "show-shortcuts";
    };

const SCREEN_META: Record<ScreenKey, { label: string; sub: string }> = {
  overview: { label: "Overview", sub: "What's working, in plain English" },
  home: { label: "Home", sub: "Command Center" },
  strategies: { label: "Models", sub: "Active strategy + arena" },
  paper: { label: "Paper Trading", sub: "Positions · fills · taxes" },
  live: { label: "Live Sandbox", sub: "$100 cap · kill switch" },
  risk: { label: "Risk", sub: "Severity · exposures · kill switch" },
  research: { label: "Research Lab", sub: "Nightly learning · health" },
  reports: { label: "Reports", sub: "All research replays at a glance" },
  ai: { label: "AI Review", sub: "Governance · readiness" },
  learn: { label: "Learn", sub: "Plain-language reference" },
  model: { label: "Model Detail", sub: "Replay curve · market comparison" },
};

const ACTION_RESULTS: CommandResult[] = [
  {
    type: "action",
    id: "toggle-vocab",
    label: "Toggle Plain / Technical",
    sub: "Switch dashboard vocabulary",
    action: "toggle-vocab",
  },
  {
    type: "action",
    id: "cycle-theme",
    label: "Switch theme (Light / Dark / System)",
    sub: "Cycle through theme options",
    action: "cycle-theme",
  },
  {
    type: "action",
    id: "start-tour",
    label: "Take the dashboard tour",
    sub: "Open guided tour",
    action: "start-tour",
  },
  {
    type: "action",
    id: "open-whats-this",
    label: "Open What's-this for current screen",
    sub: "Screen glossary",
    action: "open-whats-this",
  },
  {
    type: "action",
    id: "show-shortcuts",
    label: "Show keyboard shortcuts",
    sub: "Keyboard help",
    action: "show-shortcuts",
  },
];

function buildCommandResults(
  query: string,
  snapshot?: DashboardSnapshot,
): CommandResult[] {
  const q = query.trim().toLowerCase();
  const screens = Object.entries(SCREEN_META).map(([screen, meta]) => ({
    type: "screen" as const,
    id: screen,
    label: meta.label,
    sub: meta.sub,
    screen: screen as ScreenKey,
  }));
  const terms = Object.entries(GLOSSARY).map(([id, entry]) => ({
    type: "term" as const,
    id,
    label: entry.term,
    sub: entry.definition,
    screen: screenFromHash(entry.link) ?? "home",
  }));
  const symbols = positionsFrom(snapshot).map((position) => ({
    type: "term" as const,
    id: `symbol:${position.symbol}`,
    label: position.symbol,
    sub: "Open paper position",
    screen: "paper" as ScreenKey,
  }));
  const all = [...screens, ...terms, ...symbols, ...ACTION_RESULTS];
  if (!q) {
    return all.slice(0, 12);
  }
  return all
    .map((result) => ({
      result,
      score:
        textScore(result.label, q) * 2 +
        textScore(result.sub, q) +
        (result.id.toLowerCase().includes(q) ? 2 : 0),
    }))
    .filter((item) => item.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 12)
    .map((item) => item.result);
}

function textScore(value: string, query: string) {
  const text = value.toLowerCase();
  if (text === query) return 10;
  if (text.startsWith(query)) return 6;
  if (text.includes(query)) return 3;
  return 0;
}

function glossaryTermsForScreen(screen: ScreenKey) {
  const hash = `#${screen}`;
  return Object.entries(GLOSSARY).filter(([, entry]) => entry.link === hash);
}

function glossary(text: string, key: string) {
  const entry = GLOSSARY[key];
  if (!entry) {
    return text;
  }
  if (!text) {
    return (
      <span className="glossary">
        <button
          type="button"
          className="glossary__btn glossary__btn--solo"
          aria-label={`What does ${entry.term} mean?`}
          tabIndex={0}
        >
          ?
        </button>
        <span className="glossary__pop" role="tooltip">
          <strong>{entry.term}</strong>
          <span>{entry.definition}</span>
        </span>
      </span>
    );
  }
  return (
    <span className="glossary">
      {text === entry.term ? (
        text
      ) : (
        <>
          <span className="g-plain">{text}</span>
          <span className="g-tech">{entry.term}</span>
        </>
      )}
      <button
        type="button"
        className="glossary__btn"
        aria-label={`What does ${entry.term} mean?`}
        tabIndex={0}
      >
        ?
      </button>
      <span className="glossary__pop" role="tooltip">
        <strong>{entry.term}</strong>
        <span>{entry.definition}</span>
      </span>
    </span>
  );
}

function exposureValue(position: Position) {
  return Math.abs(Number(position.quantity) * Number(position.average_cost ?? 0));
}

function positionsFrom(snapshot?: DashboardSnapshot) {
  return snapshot?.paper_report?.ledger_snapshot?.positions ?? [];
}

function strategyKey(snapshot?: DashboardSnapshot) {
  const strategy = snapshot?.active_strategy_definition;
  if (!strategy) {
    return "pending";
  }
  return `${strategy.strategy_id ?? strategy.name}:${strategy.version ?? "unknown"}`;
}

function firstComparison(snapshot?: DashboardSnapshot): ModelComparison | undefined {
  return (
    snapshot?.model_arena?.comparisons?.[0] ??
    snapshot?.nightly_learning?.comparisons?.[0]
  );
}

function championScore(snapshot?: DashboardSnapshot): [string, string] {
  const comparison = firstComparison(snapshot);
  if (comparison?.champion_score !== undefined) {
    const score = Number(comparison.champion_score);
    return [score.toFixed(4), score >= 0 ? "pos" : "neg"];
  }
  const card = snapshot?.model_cards?.[0];
  if (card) {
    return [Number(card.score).toFixed(4), Number(card.score) >= 0 ? "pos" : "neg"];
  }
  return ["—", ""];
}

function modelKey(model: { strategy_id?: string; version?: string } | undefined) {
  if (!model) {
    return "pending";
  }
  return `${model.strategy_id ?? "strategy"}:${model.version ?? "unknown"}`;
}

function riskSeverity(snapshot?: DashboardSnapshot) {
  return (snapshot?.daily_report?.risk_report?.severity ?? "OK").toUpperCase();
}

function riskTone(snapshot?: DashboardSnapshot) {
  const severity = riskSeverity(snapshot).toLowerCase();
  if (severity.includes("critical") || severity.includes("blocked")) {
    return "danger";
  }
  if (severity.includes("attention") || severity.includes("warning")) {
    return "warn";
  }
  return "ai";
}

function statClass(tone?: string) {
  if (tone === "pos" || tone === "good") return "stat--pos";
  if (tone === "neg" || tone === "danger") return "stat--neg";
  if (tone === "warn") return "stat--warn";
  if (tone === "ai") return "stat--ai";
  return "";
}

function pillTone(tone: string) {
  if (tone === "good") return "good";
  if (tone === "warn") return "warn";
  if (tone === "danger") return "danger";
  if (tone === "ai") return "ai";
  return "ghost";
}

function humanizeRejection(rule: string, message: string) {
  if (rule === "MAX_ORDERS_PER_DAY") {
    return "We didn't place this trade — you've already hit today's order limit.";
  }
  return message;
}

function enumText(value: unknown, fallback: string) {
  if (value === undefined || value === null || value === "") {
    return fallback;
  }
  if (typeof value === "object" && value !== null && "value" in value) {
    const nested = (value as { value?: unknown }).value;
    return nested === undefined || nested === null || nested === ""
      ? fallback
      : String(nested);
  }
  return String(value);
}

function stringValue(value: unknown, fallback: string) {
  if (value === undefined || value === null || value === "") {
    return fallback;
  }
  return String(value);
}

function numberValue(value: unknown, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function percentValue(value: unknown, fallback = "n/a") {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return fallback;
  }
  return `${parsed >= 0 ? "+" : ""}${(parsed * 100).toFixed(2)}%`;
}

function numberOrFallback(value: unknown, fallback: string) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toFixed(2) : fallback;
}

function evidencePeriod(evidence?: DashboardModelEvidence | null) {
  if (evidence?.comparison_start_date && evidence.comparison_end_date) {
    return `${evidence.comparison_start_date} to ${evidence.comparison_end_date}`;
  }
  return "full-period comparison unavailable";
}

function modelReturnVsChampion(
  evidence?: DashboardModelEvidence | null,
  championEvidence?: DashboardModelEvidence | null,
) {
  const modelReturn = Number(evidence?.net_total_return);
  const championReturn = Number(championEvidence?.net_total_return);
  if (Number.isFinite(modelReturn) && Number.isFinite(championReturn)) {
    return modelReturn - championReturn;
  }
  const modelDelta = Number(evidence?.excess_return ?? evidence?.full_delta);
  const championDelta = Number(
    championEvidence?.excess_return ?? championEvidence?.full_delta,
  );
  if (Number.isFinite(modelDelta) && Number.isFinite(championDelta)) {
    return modelDelta - championDelta;
  }
  return undefined;
}

function shadowObservationForModel(
  snapshot: DashboardSnapshot | undefined,
  modelKey: string,
): ShadowChallengerObservation | undefined {
  return snapshot?.shadow_challengers?.find((item) => item.model_key === modelKey);
}

function shadowTrackingReturn(shadow?: ShadowChallengerObservation) {
  const equity = Number(shadow?.estimated_equity);
  const previous = Number(shadow?.previous_estimated_equity);
  if (!Number.isFinite(equity) || !Number.isFinite(previous) || previous <= 0) {
    return undefined;
  }
  return equity / previous - 1;
}

function targetSummary(shadow: ShadowChallengerObservation) {
  const entries = Object.entries(shadow.targets ?? {});
  if (!entries.length) {
    return "cash / no target";
  }
  return entries
    .map(([symbol, weight]) => `${symbol} ${allocationValue(weight)}`)
    .join(", ");
}

function allocationValue(value: unknown) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return String(value);
  }
  return `${(parsed * 100).toFixed(1)}%`;
}

function toneClass(value: unknown, _drawdown = false) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return "";
  }
  return parsed >= 0 ? "pos" : "neg";
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function recordValue(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
}

function latestPrices(snapshot?: DashboardSnapshot) {
  const latest = recordValue(snapshot?.runtime_state?.latest_prices);
  const records = arrayValue(latest.records).map((raw) => {
    const record = recordValue(raw);
    return {
      symbol: stringValue(record.symbol, "UNKNOWN"),
      status: stringValue(record.status, "unknown"),
      price: stringValue(record.price, "unavailable"),
      tone: stringValue(record.tone, ""),
    };
  });
  return {
    status: stringValue(latest.status, "missing"),
    feed: stringValue(latest.feed ?? latest.source, snapshot?.data_feed_status ?? "unavailable"),
    warning: stringValue(
      latest.warning,
      "Latest prices have not refreshed yet.",
    ),
    records,
  };
}

function yesNo(value: boolean) {
  return value ? "yes" : "no";
}

function benchmarkStatus(report: DashboardSnapshot["daily_report"] | undefined) {
  const metadata = report?.report_metadata;
  return metadata?.evidence_sources?.length ? "available" : "unavailable";
}

function reportHeading(snapshot?: DashboardSnapshot) {
  if (snapshot?.daily_report?.report_metadata?.report_path) {
    return "Daily report written";
  }
  return "Daily report snapshot";
}

function humanizeCode(value: string) {
  return value
    .split(/[_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function joinValues(value: unknown) {
  if (!Array.isArray(value)) {
    return "unavailable";
  }
  return value.length ? value.map(String).join(", ") : "unavailable";
}

function symbolCount(value: unknown) {
  if (!Array.isArray(value) || !value.length) {
    return "unavailable";
  }
  return `${value.length} tracked`;
}

function qualityWindow(report: Record<string, unknown>) {
  const provenance = recordValue(report.provenance);
  if (provenance.start && provenance.end) {
    return `${String(provenance.start)} to ${String(provenance.end)}`;
  }
  return stringValue(report.generated_at, "unavailable");
}

function healthTone(status: string) {
  const lowered = status.toLowerCase();
  if (lowered.includes("healthy")) return "good";
  if (lowered.includes("degraded") || lowered.includes("warning")) return "warn";
  if (lowered.includes("critical") || lowered.includes("failed")) return "danger";
  return "ghost";
}

function scoresFromEvaluation(evaluation: NightlyLearningRun["champion_evaluation"] | undefined) {
  return (
    evaluation?.fold_results
      ?.map((fold) => Number(fold.metrics?.score))
      .filter((score) => Number.isFinite(score)) ?? []
  );
}

function liveSandboxHistoryPoint(
  snapshot?: DashboardSnapshot,
): LiveSandboxHistoryPoint | undefined {
  const sandbox = snapshot?.live_sandbox;
  const asOf =
    sandbox?.generated_at ??
    sandbox?.latest_cycle?.as_of ??
    snapshot?.generated_at;
  const timestamp = asOf ? Date.parse(asOf) : Number.NaN;
  const equity = numericValue(sandbox?.sandbox_equity);
  const deployed = numericValue(sandbox?.cap_deployed);
  const cash = numericValue(sandbox?.sandbox_cash);
  if (
    !asOf ||
    !Number.isFinite(timestamp) ||
    equity === undefined ||
    deployed === undefined ||
    cash === undefined
  ) {
    return undefined;
  }
  return {
    asOf,
    timestamp,
    equity,
    deployed,
    cash,
  };
}

function confidenceBand(score: number | undefined) {
  if (score === undefined) return "—";
  if (score < 0.4) return "Low";
  if (score < 0.7) return "Moderate";
  if (score < 0.9) return "High";
  return "Very high";
}

function confidenceBandClass(score: number | undefined) {
  if (score === undefined) return "";
  if (score < 0.4) return "confidence__band--low";
  if (score < 0.7) return "confidence__band--mod";
  if (score < 0.9) return "confidence__band--high";
  return "confidence__band--vhigh";
}

function chartPoints(values: number[], width: number, height: number, pad: number) {
  if (!values.length) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = max - min;
  const innerW = width - pad * 2;
  const innerH = height - pad * 2;
  return values.map((value, index) => {
    const x = (index / Math.max(values.length - 1, 1)) * innerW + pad;
    const y =
      spread === 0
        ? height / 2
        : height - pad - ((value - min) / spread) * innerH;
    return [x, y] as const;
  });
}

function numericValue(value: string | undefined) {
  if (value === undefined) {
    return undefined;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function marketDateKey(value: string) {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) {
    return undefined;
  }
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(timestamp));
}

function moneyDelta(value: number) {
  const sign = value < 0 ? "-" : "+";
  return `${sign}${money(String(Math.abs(value)))}`;
}

function percentDelta(value: number) {
  const sign = value < 0 ? "-" : "+";
  return `${sign}${Math.abs(value).toFixed(2)}%`;
}

function money(value: string | undefined) {
  if (value === undefined) {
    return "$0.00";
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return value;
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(parsed);
}

function formatIso(value: string | undefined) {
  if (!value) {
    return "pending";
  }
  return value;
}

function formatLiveChartTime(value: string | undefined) {
  if (!value) {
    return "pending";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en", {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function screenFromHash(hash: string): ScreenKey | null {
  const value = hash.replace(/^#\/?/, "").toLowerCase();
  if (value.startsWith("model")) return "model";
  const screen = value as ScreenKey;
  if (
    screen === "overview" ||
    screen === "home" ||
    screen === "strategies" ||
    screen === "paper" ||
    screen === "live" ||
    screen === "risk" ||
    screen === "research" ||
    screen === "reports" ||
    screen === "ai" ||
    screen === "learn"
  ) {
    return screen;
  }
  return null;
}

function modelSelectionFromHash(hash: string): ModelSelection | null {
  const value = hash.replace(/^#\/?/, "");
  if (!value.toLowerCase().startsWith("model")) {
    return null;
  }
  const queryIndex = value.indexOf("?");
  if (queryIndex === -1) {
    return null;
  }
  const params = new URLSearchParams(value.slice(queryIndex + 1));
  const modelKey = params.get("model_key");
  if (!modelKey) {
    return null;
  }
  const universeId = params.get("universe_id") ?? undefined;
  return { modelKey, universeId };
}

function modelSelectionHash(selection: ModelSelection): string {
  const params = new URLSearchParams({ model_key: selection.modelKey });
  if (selection.universeId) {
    params.set("universe_id", selection.universeId);
  }
  return `#model?${params.toString()}`;
}
