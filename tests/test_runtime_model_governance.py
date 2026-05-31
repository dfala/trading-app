from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from trading_app.learning import (
    CandidateSpec,
    ModelRegistry,
    ModelRegistryState,
    ModelVersionRecord,
    NightlyLearningConfig,
    NightlyLearningLoop,
)
from trading_app.runtime import (
    RuntimeModelGovernanceAuditor,
    RuntimePersistenceStore,
    RuntimePreflightStatus,
    render_model_governance_markdown,
    render_model_governance_text,
)
from trading_app.runtime.governance import main as governance_main
from trading_app.schemas import DailyBar, DataFeed
from trading_app.strategies.sector_momentum import MonthlySectorMomentumStrategy

NOW = datetime(2026, 5, 29, 23, tzinfo=UTC)


def test_model_governance_audit_passes_for_recommendation_only_learning(
    tmp_path,
) -> None:
    store = RuntimePersistenceStore(tmp_path)
    store.persist_learning_run(_learning_run(auto_shadow=False))

    report = RuntimeModelGovernanceAuditor(output_dir=tmp_path).audit(as_of=NOW)
    text = render_model_governance_text(report)
    markdown = render_model_governance_markdown(report)

    assert report.passed
    assert report.status == RuntimePreflightStatus.PASSED
    assert report.learning_run_id == "nightly-2026-05-29"
    assert report.recommendation_count == 1
    assert report.unreviewed_authority_increases == ()
    assert report.markdown_path is not None
    assert Path(report.markdown_path).exists()
    assert "Model governance status" in text
    assert "Paper Runtime Model Governance Audit" in markdown
    assert (tmp_path / "state" / "latest-model-governance-report.json").exists()
    assert (tmp_path / "journal" / "model-governance.jsonl").exists()


def test_model_governance_audit_fails_unreviewed_authority_increase(tmp_path) -> None:
    store = RuntimePersistenceStore(tmp_path)
    store.persist_learning_run(_learning_run(auto_shadow=True))

    report = RuntimeModelGovernanceAuditor(output_dir=tmp_path).audit(as_of=NOW)
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert report.status == RuntimePreflightStatus.FAILED
    assert report.unreviewed_authority_increases == (
        "monthly_sector_momentum:1.1.0:new->shadow",
    )
    assert by_name["unreviewed_authority_increases"].status == (
        RuntimePreflightStatus.FAILED
    )


def test_model_governance_cli_outputs_json_and_exit_codes(tmp_path, capsys) -> None:
    complete_dir = tmp_path / "complete"
    missing_dir = tmp_path / "missing"
    RuntimePersistenceStore(complete_dir).persist_learning_run(
        _learning_run(auto_shadow=False)
    )

    success = governance_main(["--output-dir", str(complete_dir), "--json"])
    failure = governance_main(["--output-dir", str(missing_dir), "--json"])
    output = capsys.readouterr().out

    assert success == 0
    assert failure == 1
    assert '"passed":true' in output
    assert '"passed":false' in output


def _learning_run(*, auto_shadow: bool):
    bars, benchmark = _learning_bars()
    registry = ModelRegistry()
    champion = registry.register(
        ModelVersionRecord(
            strategy_id="monthly_sector_momentum",
            version="1.0.0",
            state=ModelRegistryState.PAPER,
            parameters={
                "universe": ("AAA", "BBB"),
                "lookback_days": 5,
                "top_n": 1,
            },
            hypothesis="Baseline monthly sector momentum champion.",
            created_at=NOW,
            is_active=True,
        )
    )
    return NightlyLearningLoop(registry=registry).run(
        as_of=NOW,
        champion=champion,
        candidate_specs=(
            CandidateSpec(
                strategy_id="monthly_sector_momentum",
                version="1.1.0",
                parameters={
                    "universe": ("AAA", "BBB"),
                    "lookback_days": 3,
                    "top_n": 1,
                },
                hypothesis="Shorter lookback may adapt faster.",
                parent_version="1.0.0",
            ),
        ),
        strategy_factory=lambda params: MonthlySectorMomentumStrategy(**params),
        bars=bars,
        benchmark_bars=benchmark,
        config=NightlyLearningConfig(
            train_window_days=20,
            test_window_days=15,
            max_folds=2,
            min_score_delta_for_shadow=-1.0,
            min_average_excess_return=-1.0,
            max_drawdown_floor=-0.99,
            auto_shadow_approved_candidates=auto_shadow,
        ),
    )


def _learning_bars() -> tuple[tuple[DailyBar, ...], tuple[DailyBar, ...]]:
    bars: list[DailyBar] = []
    benchmark: list[DailyBar] = []
    for index, trading_day in enumerate(_business_days(date(2025, 1, 1), 80)):
        aaa_close = Decimal("100") + Decimal(index) * Decimal("0.25")
        bbb_close = Decimal("100") + Decimal(index) * Decimal("0.05")
        if index >= 40:
            bbb_close += Decimal(index - 39) * Decimal("0.70")
        spy_close = Decimal("100") + Decimal(index) * Decimal("0.10")
        bars.append(_bar("AAA", trading_day, aaa_close))
        bars.append(_bar("BBB", trading_day, bbb_close))
        benchmark.append(_bar("SPY", trading_day, spy_close))
    return tuple(bars), tuple(benchmark)


def _business_days(start: date, count: int) -> list[date]:
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _bar(symbol: str, trading_date: date, close: Decimal) -> DailyBar:
    return DailyBar(
        symbol=symbol,
        trading_date=trading_date,
        bar_at=datetime(
            trading_date.year,
            trading_date.month,
            trading_date.day,
            21,
            tzinfo=UTC,
        ),
        ingested_at=NOW,
        open_price=close,
        high_price=close,
        low_price=close,
        close_price=close,
        volume=Decimal("1000000"),
        source="model-governance-test",
        data_feed=DataFeed.IEX,
    )
