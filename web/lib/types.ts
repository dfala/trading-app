export type OperatorControlAction =
  | "pause_runtime"
  | "resume_runtime"
  | "enable_paper_kill_switch"
  | "disable_paper_kill_switch"
  | "force_reconciliation"
  | "generate_report";

export type Tone = "good" | "warn" | "danger" | "info" | string;

export type DashboardMetric = {
  label: string;
  value: string;
  detail: string;
  tone: Tone;
};

export type PortfolioHistoryPoint = {
  as_of: string;
  estimated_equity: string;
  cash?: string | null;
  realized_pnl?: string | null;
};

export type DashboardAlert = {
  id: string;
  created_at: string;
  severity: "info" | "warning" | "error" | string;
  code: string;
  title: string;
  message: string;
  evidence?: string[];
  resolved?: boolean;
};

export type OperatorControlState = {
  paused: boolean;
  paper_kill_switch_enabled: boolean;
  updated_at: string;
  updated_by: string;
  reason?: string;
};

export type HealthCheck = {
  name: string;
  status: string;
  message: string;
  checked_at?: string;
  evidence?: string[];
};

export type HealthReport = {
  status: string;
  summary: string;
  next_action?: string;
  checks?: HealthCheck[];
  incidents?: HealthIncident[];
};

export type RejectedSignal = {
  order_id: string;
  symbol: string;
  rule: string;
  message: string;
  checked_at?: string;
};

export type TradeExplanation = {
  order_id: string;
  strategy_id?: string;
  symbol: string;
  side: string | { value?: string };
  quantity: string;
  status: string | { value?: string };
  accepted: boolean;
  broker_submitted?: boolean;
  broker_order_id?: string | null;
  fill_ids?: string[];
  signal_rationale?: string;
  ledger_trace?: string[];
  explanation?: string;
  evidence?: string[];
};

export type Position = {
  symbol: string;
  quantity: string;
  average_cost?: string;
  realized_pnl?: string;
};

export type Fill = {
  order_id?: string;
  symbol: string;
  side: string | { value?: string };
  quantity: string;
  price: string;
  filled_at: string;
};

export type DashboardModelEvidence = {
  model_key: string;
  source: string;
  source_report?: string | null;
  benchmark?: string;
  comparison_start_date?: string | null;
  comparison_end_date?: string | null;
  comparison_generated_at?: string | null;
  rank?: number | null;
  comparison_rank?: number | null;
  universe_id?: string | null;
  strategy_name?: string | null;
  net_total_return?: number | null;
  benchmark_total_return?: number | null;
  excess_return?: number | null;
  full_delta?: number | null;
  stress_delta?: number | null;
  annualized_return?: number | null;
  annualized_volatility?: number | null;
  worst_drawdown?: number | null;
  risk_adjusted_score?: number | null;
  positive_folds?: number | null;
  fold_count?: number | null;
  min_fold_delta?: number | null;
  average_fold_delta?: number | null;
  turnover?: number | null;
  trade_count?: number | null;
  decision_count?: number | null;
  seen_count?: number | null;
  gate_status?: string | null;
  status?: string | null;
  latest_run_id?: string | null;
  note?: string | null;
};

export type DashboardModelCard = {
  label: string;
  strategy_id: string;
  version: string;
  state: string;
  score: number;
  detail: string;
  evidence?: DashboardModelEvidence | null;
};

export type ModelPerformancePoint = {
  trading_date: string;
  model_equity: number;
  benchmark_equity: number;
  model_return: number;
  benchmark_return: number;
  excess_return: number;
};

export type ModelPerformanceMetrics = {
  net_total_return: number;
  benchmark_total_return: number;
  excess_return: number;
  annualized_return: number;
  annualized_volatility: number;
  max_drawdown: number;
  turnover: number;
  trade_count: number;
  decision_count: number;
};

export type ModelStrategyProfile = {
  hypothesis: string;
  trading_cadence: string;
  holding_period: string;
  signal_logic: string;
  sizing_logic: string;
  exit_logic: string;
  invests_in: string[];
  failure_modes: string[];
  parameters: Record<string, string>;
};

export type ModelPerformanceResponse = {
  model_key: string;
  strategy_id: string;
  version: string;
  strategy_name: string;
  universe_id?: string | null;
  benchmark: string;
  data_feed: string;
  decision_frequency: string;
  execution_price: string;
  start_date: string;
  end_date: string;
  generated_at: string;
  source_report: string;
  source_run_id: string;
  source_rank?: number | null;
  source_research_score?: number | null;
  window_policy: string;
  available_window_count: number;
  strategy_profile?: ModelStrategyProfile | null;
  metrics: ModelPerformanceMetrics;
  points: ModelPerformancePoint[];
  error?: string;
};

export type StrategyDefinition = {
  name?: string;
  strategy_id?: string;
  version?: string;
  authority?: string | { value?: string };
  benchmark?: string;
  trading_cadence?: string | { value?: string };
  holding_period?: string;
  universe?: string[];
  hypothesis?: string;
  signal_logic?: string;
  sizing_logic?: string;
  exit_logic?: string;
  failure_modes?: string[];
  ai_role?: string[];
};

export type ModelRef = {
  strategy_id?: string;
  version?: string;
  state?: string | { value?: string };
};

export type ShadowOrderIntent = {
  symbol: string;
  side: string | { value?: string };
  quantity: string;
  estimated_price: string;
  estimated_notional: string;
  current_value: string;
  target_value: string;
};

export type ShadowChallengerObservation = {
  as_of: string;
  model_key: string;
  strategy_id: string;
  version: string;
  authority: string;
  latest_prices_fresh: boolean;
  broker_orders_submitted: boolean;
  targets: Record<string, string>;
  explanation: string;
  metadata?: Record<string, unknown>;
  orders?: ShadowOrderIntent[];
  ledger_snapshot?: {
    cash?: string;
    realized_pnl?: string;
    total_fees?: string;
    positions?: Position[];
  };
  estimated_equity: string;
  previous_estimated_equity?: string | null;
};

export type ModelComparison = {
  champion?: ModelRef;
  challenger?: ModelRef;
  champion_score?: number;
  challenger_score?: number;
  score_delta?: number;
  recommendation?: string | { value?: string };
  rationale?: string;
};

export type ModelArena = {
  comparisons?: ModelComparison[];
};

export type LearningRecommendation = {
  confidence?: number;
};

export type FoldResult = {
  metrics?: {
    score?: number;
  };
};

export type ModelEvaluation = {
  model?: ModelRef;
  aggregate_score?: number;
  fold_results?: FoldResult[];
};

export type NightlyLearningRun = {
  comparisons?: ModelComparison[];
  recommendations?: LearningRecommendation[];
  research_memo?: string;
  active_model_unchanged?: boolean;
  champion_evaluation?: ModelEvaluation;
  candidate_evaluations?: ModelEvaluation[];
};

export type AutonomousLearningCandidate = {
  rank?: number;
  universe_id?: string;
  model_key?: string;
  strategy_name?: string;
  full_delta?: number;
  stress_delta?: number | null;
  net_total_return?: number | null;
  benchmark_total_return?: number | null;
  annualized_return?: number | null;
  annualized_volatility?: number | null;
  turnover?: number | null;
  trade_count?: number;
  decision_count?: number;
  positive_folds?: number;
  fold_count?: number;
  min_fold_delta?: number;
  average_fold_delta?: number;
  worst_drawdown?: number;
  risk_adjusted_score?: number;
  gate_status?: string;
  status?: string;
};

export type AutonomousShadowArenaCandidate = {
  rank?: number;
  universe_id?: string;
  model_key?: string;
  strategy_name?: string;
  authority?: string;
  broker_orders_submitted?: boolean;
  virtual_starting_cash?: string;
  historical_virtual_equity?: string | null;
  historical_virtual_pnl?: string | null;
  full_delta?: number;
  stress_delta?: number | null;
  min_fold_delta?: number;
  worst_drawdown?: number;
  risk_adjusted_score?: number;
  gate_status?: string;
  status?: string;
  next_review_action?: string;
};

export type AutonomousShadowArena = {
  run_id?: string;
  generated_at?: string;
  arena_size?: number;
  broker_orders_submitted?: boolean;
  candidates?: AutonomousShadowArenaCandidate[];
  summary?: string;
};

export type AutonomousLearningLeaderboardEntry = {
  rank?: number;
  seen_count?: number;
  latest_run_id?: string;
  hypothesis_ids?: string[];
  universe_id?: string;
  model_key?: string;
  strategy_name?: string;
  full_delta?: number;
  net_total_return?: number | null;
  benchmark_total_return?: number | null;
  stress_delta?: number | null;
  min_fold_delta?: number;
  average_fold_delta?: number;
  worst_drawdown?: number;
  risk_adjusted_score?: number;
  positive_folds?: number;
  fold_count?: number;
  gate_status?: string;
  status?: string;
};

export type AutonomousLearningLeaderboard = {
  generated_at?: string;
  entry_count?: number;
  entries?: AutonomousLearningLeaderboardEntry[];
  summary?: string;
};

export type AutonomousCandidateReadiness = {
  run_id?: string;
  generated_at?: string;
  pilot_status?: string;
  pilot_candidate_model_key?: string | null;
  promotion_qualified?: AutonomousLearningCandidate[];
  raw_alpha_watchlist?: AutonomousLearningCandidate[];
  low_drawdown_watchlist?: AutonomousLearningCandidate[];
  fragile_watchlist?: AutonomousLearningCandidate[];
  gate_rules?: string[];
  summary?: string;
};

export type AutonomousLearningCycle = {
  run_id?: string;
  generated_at?: string;
  mode?: string;
  hypothesis_id?: string;
  status?: string;
  start_date?: string;
  end_date?: string;
  benchmark?: string;
  candidate_count?: number;
  completed_report_count?: number;
  skipped_count?: number;
  current_champion_model_key?: string;
  recommended_challenger_model_key?: string | null;
  top_candidates?: AutonomousLearningCandidate[];
  research_fingerprint?: string | null;
  tuning_mode?: boolean;
  shadow_arena?: AutonomousShadowArena | null;
  leaderboard?: AutonomousLearningLeaderboard | null;
  candidate_readiness?: AutonomousCandidateReadiness | null;
  artifact_paths?: Record<string, string>;
  manual_approval_required?: boolean;
  active_model_unchanged?: boolean;
  summary?: string;
  next_actions?: string[];
};

export type AutonomousLearningServiceState = {
  generated_at?: string;
  heartbeat_at?: string;
  service_status?: string;
  current_task?: string | null;
  active_run_id?: string | null;
  current_historical_hypothesis_id?: string | null;
  current_historical_fingerprint?: string | null;
  current_historical_lane?: string | null;
  last_historical_hypothesis_id?: string | null;
  last_historical_fingerprint?: string | null;
  last_historical_lane?: string | null;
  next_historical_hypothesis_id?: string | null;
  next_historical_fingerprint?: string | null;
  next_historical_lane?: string | null;
  historical_hypothesis_counts?: Record<string, number>;
  historical_fingerprint_counts?: Record<string, number>;
  historical_lane_counts?: Record<string, number>;
  dynamic_historical_backlog_enabled?: boolean;
  dynamic_historical_profile_count?: number;
  last_completed_task?: string | null;
  last_cycle_run_id?: string | null;
  last_cycle_status?: string | null;
  latest_recommended_challenger_model_key?: string | null;
  completed_cycle_count?: number;
  failed_cycle_count?: number;
  next_historical_experiment_due_at?: string | null;
  next_fresh_market_data_due_at?: string | null;
  last_error?: string | null;
  policy_summary?: string;
  promotion_gate?: {
    status?: string;
    candidate_model_key?: string | null;
    observation_count?: number;
    distinct_observation_dates?: number;
    manual_approval_required?: boolean;
    summary?: string;
  };
};

export type TaxReport = {
  tax_estimate_available?: boolean;
  active_lot_count?: number;
  realized_lot_count?: number;
  lot_method?: string | { value?: string };
  estimated_tax?: string;
  short_term_realized_gains?: string;
  long_term_realized_gains?: string;
  total_realized_gains?: string;
};

export type AIGovernanceSummary = {
  generated_by?: string;
  summary?: string;
  evidence?: string[];
  prohibited_actions?: string[];
};

export type DailyReport = {
  trading_day?: string;
  report_metadata?: {
    evidence_sources?: unknown[];
    report_path?: string;
  } | null;
  fill_report?: unknown[];
  operator_actions?: unknown[];
  runtime_events?: unknown[];
  trade_explanations?: TradeExplanation[];
  pnl_report?: {
    ending_cash?: string;
    estimated_equity?: string;
    realized_pnl?: string;
    unrealized_pnl?: string;
    open_positions?: number;
    open_position_symbols?: string[];
  };
  risk_report?: {
    severity?: string;
    risk_decisions?: number;
    approved_orders?: number;
    rejected_orders?: number;
    rejection_count?: number;
    rejection_rules?: string[];
    reconciliation_reconciled?: boolean;
    reconciliation_issue_count?: number;
  };
  rejected_signal_report?: {
    rejected_signals?: RejectedSignal[];
  };
  data_quality_report?: Record<string, unknown> | null;
  tax_report?: TaxReport;
  ai_summary?: AIGovernanceSummary;
};

export type HealthIncident = {
  title?: string;
  summary?: string;
  status?: string | { value?: string };
  suggested_action?: string;
};

export type DashboardSnapshot = {
  generated_at: string;
  mode: string;
  broker: string;
  data_feed_status: string;
  kill_switch_enabled: boolean;
  cash: string;
  estimated_equity: string;
  realized_pnl: string;
  managed_capital?: string | null;
  managed_target_equity?: string | null;
  portfolio_history?: PortfolioHistoryPoint[];
  open_orders: number;
  metrics: DashboardMetric[];
  recent_fills?: Fill[];
  model_cards?: DashboardModelCard[];
  model_arena?: ModelArena | null;
  nightly_learning?: NightlyLearningRun | null;
  latest_prices?: Record<string, unknown> | null;
  autonomous_learning?: AutonomousLearningCycle | null;
  autonomous_learning_service?: AutonomousLearningServiceState | null;
  nightly_learning_path?: string | null;
  alerts?: DashboardAlert[];
  control_state?: OperatorControlState | null;
  last_control_result?: {
    request?: {
      action?: string;
    };
  } | null;
  health_report?: HealthReport | null;
  health_report_path?: string | null;
  daily_report?: {
    pnl_report?: {
      ending_cash?: string;
      estimated_equity?: string;
      realized_pnl?: string;
      unrealized_pnl?: string;
      open_positions?: number;
      open_position_symbols?: string[];
    };
    risk_report?: {
      severity?: string;
      risk_decisions?: number;
      approved_orders?: number;
      rejected_orders?: number;
      rejection_count?: number;
      rejection_rules?: string[];
      reconciliation_reconciled?: boolean;
      reconciliation_issue_count?: number;
    };
    rejected_signal_report?: {
      rejected_signals?: RejectedSignal[];
    };
  } & DailyReport;
  shadow_challenger?: ShadowChallengerObservation | null;
  shadow_challengers?: ShadowChallengerObservation[];
  paper_report?: {
    ledger_snapshot?: {
      cash?: string;
      realized_pnl?: string;
      total_fees?: string;
      positions?: Position[];
    };
    reconciliation?: {
      reconciled?: boolean;
      issues?: unknown[];
    };
  };
  runtime_state?: {
    status?: string;
    active_model_key?: string;
    shadow_challenger?: ShadowChallengerObservation | null;
    shadow_challengers?: ShadowChallengerObservation[];
    daily_report_path?: string;
    last_cycle?: Record<string, unknown> | null;
    latest_prices?: {
      status?: string;
      source?: string;
      warning?: string | null;
    } | null;
  } | null;
  live_readiness?: Record<string, unknown> | null;
  completion_audit?: Record<string, unknown> | null;
  final_acceptance?: Record<string, unknown> | null;
  statement_reconciliation?: Record<string, unknown> | null;
  statement_reconciliation_path?: string | null;
  active_strategy_definition?: StrategyDefinition | null;
};

export type ControlResult = {
  status?: string;
  message?: string;
  control_state?: OperatorControlState;
  error?: string;
};

export type ReplayReportKind = "comparison" | "strategy" | "other";

export type ReplayReportMetricSnapshot = {
  strategy?: string;
  net?: string;
  benchmark?: string;
  delta?: string;
  maxDrawdown?: string;
  volatility?: string;
  turnover?: string;
  trades?: string;
  leakage?: string;
  championDelta?: string;
  championBaseline?: string;
  championRank?: string;
};

export type ReplayReportSummary = {
  id: string;
  title: string;
  fileName: string;
  relativePath: string;
  kind: ReplayReportKind;
  updatedAt: string;
  sizeBytes: number;
  runId?: string;
  range?: string;
  benchmark?: string;
  champion?: string;
  policy?: string;
  strategyCount?: number;
  skippedCount?: number;
  summary?: string;
  tags: string[];
  topMetric?: ReplayReportMetricSnapshot;
};

export type ReplayReportResponse = {
  reports: ReplayReportSummary[];
  selectedId?: string;
  selectedReport?: ReplayReportSummary;
  content?: string;
  error?: string;
};

export type ShadowEquityPoint = {
  as_of: string;
  equity: number;
};

export type ShadowModelSeries = {
  model_key: string;
  strategy_id?: string;
  version?: string;
  starting_equity: number;
  latest_equity: number;
  total_return: number;
  points: ShadowEquityPoint[];
};

export type ShadowHistoryResponse = {
  generated_at: string;
  source: string;
  models: ShadowModelSeries[];
  error?: string;
};
