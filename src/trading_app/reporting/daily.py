"""Daily paper-trading reports and grounded governance summaries."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from trading_app.market_data import MarketDataQualityReport
from trading_app.paper import PaperPortfolioReport
from trading_app.reporting.models import (
    AIGovernanceSummary,
    DailyBenchmarkReport,
    DailyFillDetail,
    DailyLearningRecommendationDetail,
    DailyLearningReport,
    DailyModelReport,
    DailyOperatorActionDetail,
    DailyPnlReport,
    DailyReportMetadata,
    DailyRiskReport,
    DailyRuntimeEventDetail,
    DailyTaxReport,
    DailyTradingReport,
    RejectedSignalDetail,
    RejectedSignalReport,
    ReportSeverity,
    TradeExplanation,
)
from trading_app.schemas import OrderStatus, PortfolioSnapshot
from trading_app.strategies import StrategyDefinition


class DailyReportGenerator:
    """Build a reviewable daily report from internal paper-trading state."""

    def build(
        self,
        paper_report: PaperPortfolioReport,
        *,
        generated_at: datetime,
        previous_snapshot: PortfolioSnapshot | None = None,
        data_quality_report: MarketDataQualityReport | None = None,
        operator_actions: tuple[Any, ...] = (),
        runtime_events: tuple[Any, ...] = (),
        nightly_learning: Any | None = None,
        benchmark_report: DailyBenchmarkReport | None = None,
        active_strategy_definition: StrategyDefinition | None = None,
        markdown_path: str | None = None,
    ) -> DailyTradingReport:
        model_reports = _model_reports(paper_report)
        pnl_report = _pnl_report(paper_report, previous_snapshot)
        risk_report = _risk_report(paper_report)
        tax_report = _tax_report(paper_report)
        fill_report = _fill_report(paper_report)
        rejected_signal_report = _rejected_signal_report(paper_report)
        trade_explanations = _trade_explanations(paper_report)
        operator_action_report = _operator_action_report(operator_actions)
        runtime_event_report = _runtime_event_report(runtime_events)
        learning_report = _learning_report(nightly_learning)
        resolved_benchmark_report = benchmark_report or _unavailable_benchmark_report()
        report_metadata = _report_metadata(
            paper_report=paper_report,
            generated_at=generated_at,
            markdown_path=markdown_path,
            data_quality_report=data_quality_report,
            operator_actions=operator_action_report,
            runtime_events=runtime_event_report,
            learning_report=learning_report,
            active_strategy_definition=active_strategy_definition,
        )
        report_without_summary = {
            "report_metadata": report_metadata,
            "trading_day": paper_report.as_of.date(),
            "model_reports": model_reports,
            "pnl_report": pnl_report,
            "risk_report": risk_report,
            "tax_report": tax_report,
            "fill_report": fill_report,
            "rejected_signal_report": rejected_signal_report,
            "trade_explanations": trade_explanations,
            "operator_actions": operator_action_report,
            "runtime_events": runtime_event_report,
            "learning_report": learning_report,
            "benchmark_report": resolved_benchmark_report,
            "data_quality_report": data_quality_report,
            "active_strategy_definition": active_strategy_definition,
        }
        ai_summary = GroundedGovernanceSummarizer().summarize(report_without_summary)
        return DailyTradingReport(
            report_metadata=report_metadata,
            trading_day=paper_report.as_of.date(),
            generated_at=generated_at,
            model_reports=model_reports,
            pnl_report=pnl_report,
            risk_report=risk_report,
            tax_report=tax_report,
            fill_report=fill_report,
            rejected_signal_report=rejected_signal_report,
            trade_explanations=trade_explanations,
            operator_actions=operator_action_report,
            runtime_events=runtime_event_report,
            learning_report=learning_report,
            benchmark_report=resolved_benchmark_report,
            ai_summary=ai_summary,
            reconciliation=paper_report.reconciliation,
            data_quality_report=data_quality_report,
            active_strategy_definition=active_strategy_definition,
        )


class GroundedGovernanceSummarizer:
    """Deterministic summary writer that only cites supplied report evidence."""

    generated_by = "grounded_governance_summarizer_v1"

    def summarize(self, report_parts: dict) -> AIGovernanceSummary:
        model_reports: tuple[DailyModelReport, ...] = report_parts["model_reports"]
        pnl_report: DailyPnlReport = report_parts["pnl_report"]
        risk_report: DailyRiskReport = report_parts["risk_report"]
        tax_report: DailyTaxReport = report_parts["tax_report"]
        fill_report: tuple[DailyFillDetail, ...] = report_parts["fill_report"]
        trade_explanations: tuple[TradeExplanation, ...] = report_parts[
            "trade_explanations"
        ]
        operator_actions: tuple[DailyOperatorActionDetail, ...] = report_parts[
            "operator_actions"
        ]
        runtime_events: tuple[DailyRuntimeEventDetail, ...] = report_parts[
            "runtime_events"
        ]
        learning_report: DailyLearningReport | None = report_parts.get(
            "learning_report"
        )
        rejected_signal_report: RejectedSignalReport = report_parts[
            "rejected_signal_report"
        ]
        data_quality_report: MarketDataQualityReport | None = report_parts.get(
            "data_quality_report"
        )
        active_strategy_definition: StrategyDefinition | None = report_parts.get(
            "active_strategy_definition"
        )

        submitted = sum(model.submitted_orders for model in model_reports)
        accepted = sum(model.accepted_orders for model in model_reports)
        rejected = sum(model.rejected_orders for model in model_reports)
        positions = pnl_report.open_positions
        risk_phrase = (
            "Risk requires attention"
            if risk_report.severity != ReportSeverity.OK
            else "Risk checks are clear"
        )
        if submitted == 0:
            opening = "No paper orders were submitted today."
        else:
            opening = (
                f"{submitted} paper order(s) were reviewed: "
                f"{accepted} accepted and {rejected} rejected."
            )
        summary = (
            f"{opening} Ending cash is {pnl_report.ending_cash}, estimated equity "
            f"is {pnl_report.estimated_equity}, and there are {positions} open "
            f"position(s). {risk_phrase}; {risk_report.rejection_count} risk "
            f"rejection(s) and {risk_report.reconciliation_issue_count} "
            "reconciliation issue(s) were recorded. "
            f"Realized paper tax lots total {tax_report.total_realized_gains}."
        )
        if fill_report:
            summary += f" {len(fill_report)} broker fill(s) were traced to the ledger."
        if operator_actions:
            summary += f" {len(operator_actions)} operator action(s) were recorded."
        if runtime_events:
            summary += f" {len(runtime_events)} runtime event(s) were captured."
        if learning_report is not None and learning_report.recommendations:
            summary += (
                f" Learning produced {len(learning_report.recommendations)} "
                "recommendation(s), with the active model still locked."
            )
        if data_quality_report is not None:
            summary += (
                f" Data quality status is {data_quality_report.status.value} "
                f"with {data_quality_report.failures} failure(s) and "
                f"{data_quality_report.warnings} warning(s)."
            )
        if active_strategy_definition is not None:
            summary += (
                f" Active model is {active_strategy_definition.strategy_id}:"
                f"{active_strategy_definition.version} with "
                f"{active_strategy_definition.authority.value} authority and "
                f"{active_strategy_definition.trading_cadence.value} cadence."
            )
        evidence = tuple(
            ["pnl_report", "risk_report", "reconciliation"]
            + (["tax_report"] if tax_report.realized_lot_count else [])
            + [f"fill:{fill.fill_id}" for fill in fill_report]
            + [f"order:{trade.order_id}" for trade in trade_explanations]
            + [
                f"rejection:{detail.order_id}:{detail.rule.value}"
                for detail in rejected_signal_report.rejected_signals
            ]
            + [
                f"operator_action:{action.action}:{action.requested_at.isoformat()}"
                for action in operator_actions
            ]
            + [
                f"runtime_event:{event.category}:{event.timestamp.isoformat()}"
                for event in runtime_events
            ]
            + (
                [
                    "learning_report",
                    *[
                        f"learning_recommendation:{item.model_key}:{item.action}"
                        for item in learning_report.recommendations
                    ],
                ]
                if learning_report is not None
                else []
            )
            + (["data_quality_report"] if data_quality_report is not None else [])
            + (
                [
                    "active_strategy_definition",
                    (
                        "active_model:"
                        f"{active_strategy_definition.strategy_id}:"
                        f"{active_strategy_definition.version}"
                    ),
                ]
                if active_strategy_definition is not None
                else []
            )
        )
        return AIGovernanceSummary(
            generated_by=self.generated_by,
            summary=summary,
            evidence=evidence,
            prohibited_actions=(
                "Do not invent trades that are absent from trade_explanations.",
                "Do not recommend live-money action from a paper daily report.",
                "Do not override risk decisions or reconciliation issues.",
                "Do not promote or mutate the active model from a daily report.",
            ),
        )


def render_markdown(report: DailyTradingReport) -> str:
    """Render a compact Markdown report for human review."""

    estimated_tax_text = (
        str(report.tax_report.estimated_tax)
        if report.tax_report.tax_estimate_available
        else "unavailable"
    )
    metadata = report.report_metadata
    markdown_path_text = (
        metadata.markdown_path
        if metadata is not None and metadata.markdown_path
        else "not written"
    )
    lines = [
        f"# Daily Trading Report - {report.trading_day.isoformat()}",
        "",
        "## Report Metadata",
        f"- Report id: {metadata.report_id if metadata else 'unavailable'}",
        f"- Schema version: {metadata.schema_version if metadata else 'unavailable'}",
        f"- Markdown path: {markdown_path_text}",
        "- Evidence sources: "
        + (
            ", ".join(metadata.evidence_sources)
            if metadata and metadata.evidence_sources
            else "none"
        ),
        "",
        "## AI Governance Summary",
        report.ai_summary.summary,
        "",
        "## Model Activity",
    ]
    if report.model_reports:
        lines.extend(
            [
                "| Strategy | Submitted | Accepted | Rejected | Filled | Symbols |",
                "| --- | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for model in report.model_reports:
            lines.append(
                "| "
                f"{model.strategy_id} | {model.submitted_orders} | "
                f"{model.accepted_orders} | {model.rejected_orders} | "
                f"{model.filled_orders} | {', '.join(model.symbols) or '-'} |"
            )
    else:
        lines.append("No strategy activity was recorded.")

    lines.extend(
        [
            "",
            "## Active Model Dossier",
            _active_model_markdown(report.active_strategy_definition),
            "",
            "## P&L",
            f"- Ending cash: {report.pnl_report.ending_cash}",
            f"- Estimated equity: {report.pnl_report.estimated_equity}",
            f"- Realized P&L: {report.pnl_report.realized_pnl}",
            f"- Unrealized P&L: {report.pnl_report.unrealized_pnl}",
            f"- Total fees: {report.pnl_report.total_fees}",
            "",
            "## Benchmark",
            _benchmark_markdown(report.benchmark_report),
            "",
            "## Risk",
            f"- Severity: {report.risk_report.severity.value}",
            f"- Risk decisions: {report.risk_report.risk_decisions}",
            f"- Rejections: {report.risk_report.rejection_count}",
            "- Reconciliation: "
            f"{'clean' if report.reconciliation.reconciled else 'issues'}",
            "",
            "## Reconciliation Details",
            _reconciliation_markdown(report.reconciliation),
            "",
            "## Tax Estimate",
            f"- Realized lots: {report.tax_report.realized_lot_count}",
            f"- Active lots: {report.tax_report.active_lot_count}",
            f"- Lot method: {report.tax_report.lot_method.value.upper()}",
            "- Short-term realized gains: "
            f"{report.tax_report.short_term_realized_gains}",
            f"- Long-term realized gains: {report.tax_report.long_term_realized_gains}",
            f"- Total realized gains: {report.tax_report.total_realized_gains}",
            f"- Estimated tax: {estimated_tax_text}",
            "- Notes: " + " ".join(report.tax_report.notes),
            "",
            "## Data Quality",
            _data_quality_markdown(report.data_quality_report),
            "",
            "## Rejected Signals",
        ]
    )
    if report.rejected_signal_report.rejected_signals:
        for detail in report.rejected_signal_report.rejected_signals:
            lines.append(
                f"- {detail.order_id} {detail.symbol}: "
                f"{detail.rule.value} - {detail.message}"
            )
    else:
        lines.append("No rejected signals.")

    lines.extend(["", "## Fills"])
    if report.fill_report:
        for fill in report.fill_report:
            lines.append(
                f"- {fill.fill_id}: {fill.symbol} {fill.side.value} "
                f"{fill.quantity} @ {fill.price}; commission {fill.commission}. "
                f"{fill.ledger_effect}"
            )
    else:
        lines.append("No fills were applied to the ledger.")

    lines.extend(["", "## Trade Explanations"])
    if report.trade_explanations:
        for explanation in report.trade_explanations:
            lines.append(
                f"- {explanation.order_id}: {explanation.explanation} "
                f"Fills: {', '.join(explanation.fill_ids) or '-'}; "
                f"Ledger: {', '.join(explanation.ledger_trace) or '-'}; "
                f"Evidence: {', '.join(explanation.evidence)}"
            )
    else:
        lines.append("No paper trades or rejected orders to explain.")

    lines.extend(["", "## Operator Actions"])
    if report.operator_actions:
        for action in report.operator_actions:
            lines.append(
                f"- {action.requested_at.isoformat()} {action.action} "
                f"by {action.requested_by}: {action.status}. {action.message}"
            )
    else:
        lines.append("No operator actions were recorded.")

    lines.extend(["", "## Runtime Events"])
    if report.runtime_events:
        for event in report.runtime_events:
            evidence = ", ".join(event.evidence) or "-"
            lines.append(
                f"- {event.timestamp.isoformat()} {event.severity} "
                f"{event.category}: {event.message} Evidence: {evidence}"
            )
    else:
        lines.append("No runtime events were recorded.")

    lines.extend(["", "## Learning Recommendations"])
    if report.learning_report is None:
        lines.append("Nightly learning has not run for this report.")
    elif report.learning_report.recommendations:
        lines.append(f"- Status: {report.learning_report.status}")
        lines.append(
            "- Active model unchanged: "
            f"{'yes' if report.learning_report.active_model_unchanged else 'no'}"
        )
        for recommendation in report.learning_report.recommendations:
            lines.append(
                f"- {recommendation.model_key}: {recommendation.action}. "
                f"{recommendation.rationale}"
            )
    else:
        lines.append(report.learning_report.research_memo)

    return "\n".join(lines) + "\n"


def _active_model_markdown(definition: StrategyDefinition | None) -> str:
    if definition is None:
        return "No active strategy definition was attached to this report."
    return "\n".join(
        [
            f"- Model: {definition.name}",
            f"- Key: {definition.strategy_id}:{definition.version}",
            f"- Authority: {definition.authority.value}",
            f"- Cadence: {definition.trading_cadence.value}",
            f"- Benchmark: {definition.benchmark}",
            f"- Universe: {', '.join(definition.universe)}",
            f"- Hypothesis: {definition.hypothesis}",
            f"- Signal logic: {definition.signal_logic}",
            f"- Sizing logic: {definition.sizing_logic}",
            f"- Exit logic: {definition.exit_logic}",
            f"- Holding period: {definition.holding_period}",
            "- Data requirements: " + " ".join(definition.data_requirements),
            "- Risk assumptions: " + " ".join(definition.risk_assumptions),
            "- Known failure modes: " + " ".join(definition.failure_modes),
            "- AI role: " + " ".join(definition.ai_role),
        ]
    )


def _benchmark_markdown(report: DailyBenchmarkReport | None) -> str:
    if report is None:
        return "- Benchmark comparison unavailable."
    if not report.comparison_available:
        return f"- {report.benchmark_symbol}: unavailable. {report.reason}"
    return "\n".join(
        [
            f"- Benchmark: {report.benchmark_symbol}",
            f"- Model return: {report.model_return}",
            f"- Benchmark return: {report.benchmark_return}",
            f"- Excess return: {report.excess_return}",
        ]
    )


def _data_quality_markdown(report: MarketDataQualityReport | None) -> str:
    if report is None:
        return "No market-data quality report was attached."
    lines = [
        f"- Status: {report.status.value}",
        f"- Research usable: {'yes' if report.can_use_for_research else 'no'}",
        f"- Trading usable: {'yes' if report.can_use_for_trading else 'no'}",
        f"- Warnings: {report.warnings}",
        f"- Failures: {report.failures}",
        f"- Sources: {', '.join(report.provenance.sources) or '-'}",
        f"- Feeds: {', '.join(feed.value for feed in report.provenance.feeds) or '-'}",
        "- Ingested window: "
        + _ingested_window_markdown(
            report.provenance.ingested_at_min,
            report.provenance.ingested_at_max,
        ),
    ]
    for issue in report.issues[:8]:
        symbol = f" {issue.symbol}" if issue.symbol else ""
        day = f" {issue.trading_date.isoformat()}" if issue.trading_date else ""
        lines.append(
            f"- {issue.status.value} {issue.code.value}{symbol}{day}: {issue.message}"
        )
    return "\n".join(lines)


def _reconciliation_markdown(report) -> str:
    if report.reconciled:
        return "No reconciliation issues were detected."
    lines = [
        "| Type | Symbol | Expected | Actual | Difference | Broker Order | Message |",
        "| --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for issue in report.issues:
        broker_order = issue.broker_order_id or "-"
        if issue.client_order_id:
            broker_order = f"{broker_order} / {issue.client_order_id}"
        if issue.provider_status:
            broker_order = f"{broker_order} ({issue.provider_status})"
        lines.append(
            "| "
            f"{_table_text(issue.issue_type.value)} | "
            f"{_table_text(issue.symbol or '-')} | "
            f"{issue.expected} | {issue.actual} | {issue.difference} | "
            f"{_table_text(broker_order)} | "
            f"{_table_text(issue.message)} |"
        )
    return "\n".join(lines)


def _ingested_window_markdown(
    ingested_at_min: datetime | None,
    ingested_at_max: datetime | None,
) -> str:
    if ingested_at_min is None or ingested_at_max is None:
        return "-"
    if ingested_at_min == ingested_at_max:
        return ingested_at_min.isoformat()
    return f"{ingested_at_min.isoformat()} to {ingested_at_max.isoformat()}"


def write_markdown_report(report: DailyTradingReport, output_dir: Path | str) -> Path:
    """Write a dated Markdown report and return its path."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    report_path = output_path / f"daily-report-{report.trading_day.isoformat()}.md"
    report_path.write_text(render_markdown(report), encoding="utf-8")
    return report_path


def _model_reports(
    paper_report: PaperPortfolioReport,
) -> tuple[DailyModelReport, ...]:
    grouped = defaultdict(list)
    for submission in paper_report.submissions:
        grouped[submission.strategy_id].append(submission)

    status_by_order_id = {
        status.order_id: status for status in paper_report.order_statuses
    }
    reports: list[DailyModelReport] = []
    for strategy_id, submissions in sorted(grouped.items()):
        reports.append(
            DailyModelReport(
                strategy_id=strategy_id,
                submitted_orders=len(submissions),
                accepted_orders=sum(1 for item in submissions if item.accepted),
                rejected_orders=sum(1 for item in submissions if not item.accepted),
                broker_submitted_orders=sum(
                    1 for item in submissions if item.broker_submitted
                ),
                filled_orders=sum(
                    1
                    for item in submissions
                    if status_by_order_id.get(item.order.id) is not None
                    and status_by_order_id[item.order.id].status == OrderStatus.FILLED
                ),
                symbols=tuple(sorted({item.order.symbol for item in submissions})),
                estimated_notional=sum(
                    (item.estimated_notional for item in submissions), Decimal("0")
                ),
            )
        )
    return tuple(reports)


def _report_metadata(
    *,
    paper_report: PaperPortfolioReport,
    generated_at: datetime,
    markdown_path: str | None,
    data_quality_report: MarketDataQualityReport | None,
    operator_actions: tuple[DailyOperatorActionDetail, ...],
    runtime_events: tuple[DailyRuntimeEventDetail, ...],
    learning_report: DailyLearningReport | None,
    active_strategy_definition: StrategyDefinition | None,
) -> DailyReportMetadata:
    evidence_sources = [
        "paper_portfolio_report",
        "internal_ledger_snapshot",
        "broker_reconciliation",
    ]
    if paper_report.fills:
        evidence_sources.append("broker_fills")
    if paper_report.risk_rejections:
        evidence_sources.append("risk_rejections")
    if data_quality_report is not None:
        evidence_sources.append("market_data_quality")
    if operator_actions:
        evidence_sources.append("operator_actions")
    if runtime_events:
        evidence_sources.append("runtime_events")
    if learning_report is not None:
        evidence_sources.append("nightly_learning")
    if active_strategy_definition is not None:
        evidence_sources.append("active_strategy_definition")
    return DailyReportMetadata(
        report_id=(
            f"daily-{paper_report.as_of.date().isoformat()}-"
            f"{generated_at.strftime('%H%M%S')}"
        ),
        generated_at=generated_at,
        markdown_path=markdown_path,
        evidence_sources=tuple(evidence_sources),
    )


def _pnl_report(
    paper_report: PaperPortfolioReport,
    previous_snapshot: PortfolioSnapshot | None,
) -> DailyPnlReport:
    snapshot = paper_report.ledger_snapshot
    broker_positions = {
        position.symbol: position
        for position in paper_report.broker_portfolio.positions
    }
    estimated_equity = snapshot.cash
    unrealized = Decimal("0")
    for position in snapshot.positions:
        broker_position = broker_positions.get(position.symbol)
        current_price = (
            broker_position.current_price
            if broker_position and broker_position.current_price is not None
            else position.average_cost
        )
        market_value = position.quantity * current_price
        estimated_equity += market_value
        unrealized += (current_price - position.average_cost) * position.quantity

    starting_cash = previous_snapshot.cash if previous_snapshot is not None else None
    cash_change = (
        snapshot.cash - previous_snapshot.cash
        if previous_snapshot is not None
        else None
    )
    return DailyPnlReport(
        starting_cash=starting_cash,
        ending_cash=snapshot.cash,
        cash_change=cash_change,
        estimated_equity=estimated_equity,
        realized_pnl=snapshot.realized_pnl,
        unrealized_pnl=unrealized,
        total_fees=snapshot.total_fees,
        open_positions=len(snapshot.positions),
        open_position_symbols=tuple(
            sorted(position.symbol for position in snapshot.positions)
        ),
    )


def _risk_report(paper_report: PaperPortfolioReport) -> DailyRiskReport:
    decisions = tuple(
        submission.risk_decision for submission in paper_report.submissions
    )
    rejection_rules = tuple(
        sorted(
            {rejection.rule for rejection in paper_report.risk_rejections},
            key=lambda rule: rule.value,
        )
    )
    rejected_orders = sum(1 for decision in decisions if not decision.approved)
    reconciliation_issue_count = len(paper_report.reconciliation.issues)
    severity = ReportSeverity.OK
    if rejected_orders or reconciliation_issue_count:
        severity = ReportSeverity.ATTENTION
    return DailyRiskReport(
        severity=severity,
        risk_decisions=len(decisions),
        approved_orders=sum(1 for decision in decisions if decision.approved),
        rejected_orders=rejected_orders,
        rejection_count=len(paper_report.risk_rejections),
        rejection_rules=rejection_rules,
        reconciliation_reconciled=paper_report.reconciliation.reconciled,
        reconciliation_issue_count=reconciliation_issue_count,
    )


def _tax_report(paper_report: PaperPortfolioReport) -> DailyTaxReport:
    summary = paper_report.tax_summary
    return DailyTaxReport(
        realized_lot_count=len(summary.realized_lots),
        active_lot_count=len(summary.active_lots),
        lot_method=summary.lot_method,
        short_term_realized_gains=summary.short_term_realized_gains,
        long_term_realized_gains=summary.long_term_realized_gains,
        total_realized_gains=summary.total_realized_gains,
        estimated_tax=summary.estimated_tax,
        estimated_after_tax_realized_gains=summary.estimated_after_tax_realized_gains,
        tax_estimate_available=summary.tax_estimate_available,
        realized_terms=tuple(sorted({lot.term for lot in summary.realized_lots})),
        notes=summary.notes,
    )


def _fill_report(paper_report: PaperPortfolioReport) -> tuple[DailyFillDetail, ...]:
    fills = sorted(paper_report.fills, key=lambda fill: (fill.filled_at, fill.id))
    return tuple(
        DailyFillDetail(
            fill_id=fill.id,
            order_id=fill.order_id,
            symbol=fill.symbol,
            side=fill.side,
            quantity=fill.quantity,
            price=fill.price,
            commission=fill.commission,
            filled_at=fill.filled_at,
            ledger_effect=(
                f"Applied to internal ledger as {fill.side.value} "
                f"{fill.quantity} {fill.symbol}."
            ),
        )
        for fill in fills
    )


def _operator_action_report(
    operator_actions: tuple[Any, ...],
) -> tuple[DailyOperatorActionDetail, ...]:
    details: list[DailyOperatorActionDetail] = []
    for item in operator_actions:
        request = _attr_or_key(item, "request")
        if request is None:
            continue
        requested_at = _attr_or_key(request, "requested_at")
        if requested_at is None:
            continue
        details.append(
            DailyOperatorActionDetail(
                action=_enum_text(_attr_or_key(request, "action"), "unknown"),
                requested_at=requested_at,
                requested_by=str(_attr_or_key(request, "requested_by") or "unknown"),
                status=_enum_text(_attr_or_key(item, "status"), "unknown"),
                message=str(_attr_or_key(item, "message") or "No message recorded."),
                reason=str(_attr_or_key(request, "reason") or ""),
            )
        )
    return tuple(details)


def _runtime_event_report(
    runtime_events: tuple[Any, ...],
) -> tuple[DailyRuntimeEventDetail, ...]:
    details: list[DailyRuntimeEventDetail] = []
    for item in runtime_events[-50:]:
        timestamp = _attr_or_key(item, "timestamp")
        if timestamp is None:
            continue
        evidence = _attr_or_key(item, "evidence") or ()
        details.append(
            DailyRuntimeEventDetail(
                timestamp=timestamp,
                severity=_enum_text(_attr_or_key(item, "severity"), "info"),
                category=str(_attr_or_key(item, "category") or "runtime"),
                message=str(_attr_or_key(item, "message") or "No message recorded."),
                evidence=tuple(str(value) for value in evidence),
            )
        )
    return tuple(details)


def _learning_report(nightly_learning: Any | None) -> DailyLearningReport | None:
    if nightly_learning is None:
        return None
    recommendations = []
    for item in _attr_or_key(nightly_learning, "recommendations") or ():
        model = _attr_or_key(item, "model")
        model_key = _attr_or_key(model, "key") if model is not None else None
        if model_key is None and model is not None:
            strategy_id = _attr_or_key(model, "strategy_id") or "unknown"
            version = _attr_or_key(model, "version") or "unknown"
            model_key = f"{strategy_id}:{version}"
        recommendations.append(
            DailyLearningRecommendationDetail(
                action=_enum_text(_attr_or_key(item, "action"), "watch"),
                model_key=str(model_key or "unknown"),
                manual_review_required=bool(
                    _attr_or_key(item, "manual_review_required") is not False
                ),
                rationale=str(
                    _attr_or_key(item, "rationale") or "No rationale recorded."
                ),
                evidence=tuple(
                    str(value) for value in (_attr_or_key(item, "evidence") or ())
                ),
            )
        )
    status = "complete"
    if not bool(_attr_or_key(nightly_learning, "active_model_unchanged") is not False):
        status = "requires_review"
    return DailyLearningReport(
        status=status,
        active_model_unchanged=bool(
            _attr_or_key(nightly_learning, "active_model_unchanged") is not False
        ),
        research_memo=str(
            _attr_or_key(nightly_learning, "research_memo")
            or "Nightly learning completed without a memo."
        ),
        recommendations=tuple(recommendations),
    )


def _unavailable_benchmark_report() -> DailyBenchmarkReport:
    return DailyBenchmarkReport(
        comparison_available=False,
        reason=(
            "No benchmark return evidence was supplied for this daily paper report."
        ),
    )


def _rejected_signal_report(
    paper_report: PaperPortfolioReport,
) -> RejectedSignalReport:
    details = tuple(
        RejectedSignalDetail(
            order_id=rejection.order_id,
            symbol=rejection.symbol,
            rule=rejection.rule,
            message=rejection.message,
            checked_at=rejection.checked_at,
        )
        for rejection in paper_report.risk_rejections
    )
    return RejectedSignalReport(rejected_signals=details)


def _trade_explanations(
    paper_report: PaperPortfolioReport,
) -> tuple[TradeExplanation, ...]:
    status_by_order_id = {
        status.order_id: status for status in paper_report.order_statuses
    }
    fills_by_order_id = defaultdict(list)
    for fill in paper_report.fills:
        fills_by_order_id[fill.order_id].append(fill)
    explanations: list[TradeExplanation] = []
    for submission in paper_report.submissions:
        status = status_by_order_id.get(submission.order.id)
        order_status = (
            status.status
            if status is not None
            else OrderStatus.NEW
            if submission.accepted
            else OrderStatus.REJECTED
        )
        fills = tuple(
            sorted(fills_by_order_id[submission.order.id], key=lambda item: item.id)
        )
        fill_ids = tuple(fill.id for fill in fills)
        broker_order_id = (
            submission.broker_order.broker_order_id
            if submission.broker_order is not None
            else None
        )
        ledger_trace = [f"order:{submission.order.id}"]
        evidence = [f"order:{submission.order.id}", "risk_decision"]
        if submission.broker_order is not None:
            evidence.append(f"broker_order:{submission.broker_order.broker_order_id}")
            ledger_trace.append(
                f"broker_order:{submission.broker_order.broker_order_id}"
            )
        if fills:
            for fill in fills:
                evidence.append(f"fill:{fill.id}")
                ledger_trace.append(f"fill:{fill.id}")
            ledger_trace.append("ledger:fill_applied")
        elif submission.accepted:
            ledger_trace.append("ledger:order_recorded")
        else:
            ledger_trace.append("ledger:not_recorded")
        if submission.accepted:
            text = (
                f"{submission.strategy_id} submitted a {submission.order.side.value} "
                f"order for {submission.order.quantity} {submission.order.symbol}. "
                f"Risk approved it, broker_submitted={submission.broker_submitted}, "
                f"and current status is {order_status.value}."
            )
        else:
            rules = ", ".join(
                rejection.rule.value
                for rejection in submission.risk_decision.rejections
            )
            text = (
                f"{submission.strategy_id} submitted a {submission.order.side.value} "
                f"order for {submission.order.quantity} {submission.order.symbol}. "
                f"Risk rejected it before broker submission because: {rules}."
            )
        explanations.append(
            TradeExplanation(
                order_id=submission.order.id,
                strategy_id=submission.strategy_id,
                symbol=submission.order.symbol,
                side=submission.order.side,
                quantity=submission.order.quantity,
                status=order_status,
                accepted=submission.accepted,
                broker_submitted=submission.broker_submitted,
                broker_order_id=broker_order_id,
                fill_ids=fill_ids,
                signal_rationale=(
                    f"{submission.strategy_id} generated this paper order"
                    + (
                        f" from signal {submission.order.signal_id}."
                        if submission.order.signal_id
                        else " from strategy target sizing; no standalone Signal "
                        "record was attached."
                    )
                ),
                ledger_trace=tuple(ledger_trace),
                explanation=text,
                evidence=tuple(evidence),
            )
        )
    return tuple(explanations)


def _attr_or_key(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        return item.get(name)
    return getattr(item, name, None)


def _enum_text(value: Any, fallback: str) -> str:
    if value is None:
        return fallback
    return str(getattr(value, "value", value))


def _table_text(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
