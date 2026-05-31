"""Model-governance audit for recommendation-only nightly learning."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from trading_app.learning import ModelRegistryState, NightlyLearningRun
from trading_app.runtime.models import (
    RuntimeModelGovernanceCheck,
    RuntimeModelGovernanceReport,
    RuntimePreflightStatus,
    RuntimeSnapshot,
)
from trading_app.runtime.persistence import RuntimePersistenceStore

_AUTHORITY_RANK = {
    ModelRegistryState.IDEA: 0,
    ModelRegistryState.BACKTEST: 1,
    ModelRegistryState.VALIDATED: 2,
    ModelRegistryState.SHADOW: 3,
    ModelRegistryState.PAPER: 4,
    ModelRegistryState.CANDIDATE_LIVE: 5,
    ModelRegistryState.LIVE_LIMITED: 6,
    ModelRegistryState.LIVE_SCALED: 7,
    ModelRegistryState.PAUSED: 1,
    ModelRegistryState.RETIRED: 0,
}


class RuntimeModelGovernanceAuditor:
    """Audit that nightly learning remains advisory and approval-gated."""

    def __init__(
        self,
        *,
        output_dir: Path | str = "data/runtime",
        persistence_store: RuntimePersistenceStore | None = None,
        persist_report: bool = True,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.store = persistence_store or RuntimePersistenceStore(self.output_dir)
        self.persist_report = persist_report

    def audit(self, *, as_of: datetime | None = None) -> RuntimeModelGovernanceReport:
        now = as_of or datetime.now(tz=UTC)
        learning = _latest_learning_run(self.store)
        learning_path = self.store.read_learning_report_path()
        authority_increases = (
            _unreviewed_authority_increases(learning) if learning is not None else ()
        )
        checks = (
            _learning_present_check(learning),
            _active_model_unchanged_check(learning),
            _active_keys_unchanged_check(learning),
            _recommendations_manual_review_check(learning),
            _recommendation_evidence_check(learning),
            _authority_increase_check(authority_increases),
            _learning_markdown_boundary_check(learning_path),
        )
        failures = sum(
            1 for check in checks if check.status == RuntimePreflightStatus.FAILED
        )
        status = (
            RuntimePreflightStatus.FAILED if failures else RuntimePreflightStatus.PASSED
        )
        report = RuntimeModelGovernanceReport(
            as_of=now,
            status=status,
            passed=status == RuntimePreflightStatus.PASSED,
            output_dir=str(self.output_dir),
            learning_run_id=learning.id if learning is not None else None,
            checks=checks,
            recommendation_count=len(learning.recommendations)
            if learning is not None
            else 0,
            unreviewed_authority_increases=authority_increases,
            summary=_summary(status, failures),
        )
        if self.persist_report:
            markdown_path = write_model_governance_markdown_report(
                report,
                self.output_dir / "reports",
            )
            report = report.model_copy(update={"markdown_path": str(markdown_path)})
            self.store.persist_model_governance_report(
                report,
                markdown_path=markdown_path,
            )
        return report


def render_model_governance_text(report: RuntimeModelGovernanceReport) -> str:
    """Render compact model-governance audit status."""

    lines = [
        f"Model governance status: {report.status.value}",
        f"Passed: {_yes_no(report.passed)}",
        f"Output dir: {report.output_dir}",
        f"Markdown report: {report.markdown_path or 'not written'}",
        f"Learning run: {report.learning_run_id or 'missing'}",
        report.summary,
        "",
        "Checks:",
    ]
    for check in report.checks:
        evidence = "; ".join(check.evidence) if check.evidence else "no evidence"
        lines.append(f"- {check.name}: {check.status.value} - {check.message}")
        lines.append(f"  Evidence: {evidence}")
    return "\n".join(lines)


def render_model_governance_markdown(
    report: RuntimeModelGovernanceReport,
) -> str:
    """Render model-governance audit Markdown."""

    lines = [
        "# Paper Runtime Model Governance Audit",
        "",
        "> Nightly learning is advisory only. This audit does not promote models.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.status.value}`",
        f"- Passed: `{_yes_no(report.passed)}`",
        f"- Audited at: `{report.as_of.isoformat()}`",
        f"- Output directory: `{report.output_dir}`",
        f"- Learning run: `{report.learning_run_id or 'missing'}`",
        f"- Recommendations: `{report.recommendation_count}`",
        "- Unreviewed authority increases: "
        f"`{_join_or_none(report.unreviewed_authority_increases)}`",
        "",
        report.summary,
        "",
        "## Checks",
        "",
        "| Check | Status | Message | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    for check in report.checks:
        evidence = "<br>".join(check.evidence) if check.evidence else "No evidence"
        lines.append(
            "| "
            f"{_escape_table(check.name)} | "
            f"{check.status.value} | "
            f"{_escape_table(check.message)} | "
            f"{_escape_table(evidence)} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_model_governance_markdown_report(
    report: RuntimeModelGovernanceReport,
    reports_dir: Path | str,
) -> Path:
    """Write model-governance Markdown and return its path."""

    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"model-governance-{_timestamp_id(report.as_of)}.md"
    path.write_text(render_model_governance_markdown(report), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit recommendation-only model governance for paper runtime."
    )
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = RuntimeModelGovernanceAuditor(
        output_dir=args.output_dir,
        persist_report=not args.no_persist,
    ).audit()
    print(
        report.model_dump_json() if args.json else render_model_governance_text(report)
    )
    return 0 if report.passed else 1


def _latest_learning_run(store: RuntimePersistenceStore) -> NightlyLearningRun | None:
    recovered = store.recover()
    if recovered.nightly_learning is not None:
        return recovered.nightly_learning
    snapshot_path = store.state_dir / "latest-runtime-snapshot.json"
    if not snapshot_path.exists():
        return None
    snapshot = RuntimeSnapshot.model_validate_json(snapshot_path.read_text())
    return snapshot.nightly_learning


def _learning_present_check(
    learning: NightlyLearningRun | None,
) -> RuntimeModelGovernanceCheck:
    if learning is None:
        return _check(
            "learning_run_present",
            RuntimePreflightStatus.FAILED,
            "No nightly learning run was found.",
        )
    return _check(
        "learning_run_present",
        RuntimePreflightStatus.PASSED,
        "Nightly learning run is present.",
        (f"learning_run={learning.id}",),
    )


def _active_model_unchanged_check(
    learning: NightlyLearningRun | None,
) -> RuntimeModelGovernanceCheck:
    if learning is None:
        return _check(
            "active_model_unchanged",
            RuntimePreflightStatus.FAILED,
            "Active model evidence is unavailable.",
        )
    return _check(
        "active_model_unchanged",
        RuntimePreflightStatus.PASSED
        if learning.active_model_unchanged
        else RuntimePreflightStatus.FAILED,
        "Active model remained unchanged."
        if learning.active_model_unchanged
        else "Nightly learning changed the active model.",
        (f"active_model_unchanged={learning.active_model_unchanged}",),
    )


def _active_keys_unchanged_check(
    learning: NightlyLearningRun | None,
) -> RuntimeModelGovernanceCheck:
    if learning is None:
        return _check(
            "active_keys_unchanged",
            RuntimePreflightStatus.FAILED,
            "Active registry keys are unavailable.",
        )
    unchanged = (
        learning.registry_before.active_keys == learning.registry_after.active_keys
    )
    return _check(
        "active_keys_unchanged",
        RuntimePreflightStatus.PASSED if unchanged else RuntimePreflightStatus.FAILED,
        "Active registry keys remained unchanged."
        if unchanged
        else "Active registry keys changed during nightly learning.",
        (
            f"before={','.join(learning.registry_before.active_keys) or 'none'}",
            f"after={','.join(learning.registry_after.active_keys) or 'none'}",
        ),
    )


def _recommendations_manual_review_check(
    learning: NightlyLearningRun | None,
) -> RuntimeModelGovernanceCheck:
    if learning is None:
        return _check(
            "recommendations_manual_review",
            RuntimePreflightStatus.FAILED,
            "Recommendation review evidence is unavailable.",
        )
    missing = tuple(
        recommendation.model.key
        for recommendation in learning.recommendations
        if not recommendation.manual_review_required
    )
    return _check(
        "recommendations_manual_review",
        RuntimePreflightStatus.PASSED if not missing else RuntimePreflightStatus.FAILED,
        "All recommendations require manual review."
        if not missing
        else "One or more recommendations bypass manual review.",
        tuple(f"missing_manual_review={key}" for key in missing)
        or (f"recommendations={len(learning.recommendations)}",),
    )


def _recommendation_evidence_check(
    learning: NightlyLearningRun | None,
) -> RuntimeModelGovernanceCheck:
    if learning is None:
        return _check(
            "recommendation_evidence",
            RuntimePreflightStatus.FAILED,
            "Recommendation evidence is unavailable.",
        )
    missing = tuple(
        recommendation.model.key
        for recommendation in learning.recommendations
        if not recommendation.evidence or not recommendation.rationale
    )
    return _check(
        "recommendation_evidence",
        RuntimePreflightStatus.PASSED if not missing else RuntimePreflightStatus.FAILED,
        "All recommendations include rationale and evidence."
        if not missing
        else "One or more recommendations are missing rationale or evidence.",
        tuple(f"missing_evidence={key}" for key in missing)
        or (f"recommendations={len(learning.recommendations)}",),
    )


def _authority_increase_check(
    increases: tuple[str, ...],
) -> RuntimeModelGovernanceCheck:
    return _check(
        "unreviewed_authority_increases",
        RuntimePreflightStatus.PASSED
        if not increases
        else RuntimePreflightStatus.FAILED,
        "Nightly learning did not increase model authority."
        if not increases
        else "Nightly learning increased model authority without approval evidence.",
        tuple(f"increase={item}" for item in increases) or ("none",),
    )


def _learning_markdown_boundary_check(
    learning_path: Path | None,
) -> RuntimeModelGovernanceCheck:
    if learning_path is None:
        return _check(
            "learning_memo_boundary",
            RuntimePreflightStatus.FAILED,
            "Nightly learning Markdown memo is missing.",
        )
    if not learning_path.exists():
        return _check(
            "learning_memo_boundary",
            RuntimePreflightStatus.FAILED,
            "Nightly learning Markdown memo path does not exist.",
            (f"path={learning_path}",),
        )
    text = learning_path.read_text(encoding="utf-8")
    required = (
        "AI-assisted research is advisory only",
        "Live-money trading remains disabled",
    )
    missing = tuple(phrase for phrase in required if phrase not in text)
    return _check(
        "learning_memo_boundary",
        RuntimePreflightStatus.PASSED if not missing else RuntimePreflightStatus.FAILED,
        "Nightly learning memo states advisory and live-money boundaries."
        if not missing
        else "Nightly learning memo is missing governance boundary text.",
        tuple(f"missing={phrase}" for phrase in missing) or (f"path={learning_path}",),
    )


def _unreviewed_authority_increases(
    learning: NightlyLearningRun,
) -> tuple[str, ...]:
    before = {record.key: record.state for record in learning.registry_before.records}
    increases: list[str] = []
    for record in learning.registry_after.records:
        previous = before.get(record.key)
        previous_rank = _AUTHORITY_RANK[previous] if previous is not None else -1
        current_rank = _AUTHORITY_RANK[record.state]
        if (
            previous is None
            and current_rank > _AUTHORITY_RANK[ModelRegistryState.BACKTEST]
        ):
            increases.append(f"{record.key}:new->{record.state.value}")
        elif previous is not None and current_rank > previous_rank:
            increases.append(f"{record.key}:{previous.value}->{record.state.value}")
    return tuple(sorted(increases))


def _check(
    name: str,
    status: RuntimePreflightStatus,
    message: str,
    evidence: tuple[str, ...] = (),
) -> RuntimeModelGovernanceCheck:
    return RuntimeModelGovernanceCheck(
        name=name,
        status=status,
        message=message,
        evidence=evidence,
    )


def _summary(status: RuntimePreflightStatus, failures: int) -> str:
    if status == RuntimePreflightStatus.PASSED:
        return "Model governance passed; nightly learning remained advisory."
    return (
        f"Model governance found {failures} failed check(s). "
        "Do not promote or alter paper-trading authority until reviewed."
    )


def _timestamp_id(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S")


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _join_or_none(values: tuple[str, ...]) -> str:
    return ", ".join(values) if values else "none"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


if __name__ == "__main__":
    raise SystemExit(main())
