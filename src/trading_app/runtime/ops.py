"""Local operations profile for the always-on paper runtime."""

from __future__ import annotations

import argparse
import shlex
from datetime import UTC, datetime
from html import escape
from pathlib import Path

from pydantic import Field

from trading_app.alpaca_credentials import alpaca_paper_boundary_violations
from trading_app.runtime.cli import parse_symbol_list
from trading_app.runtime.models import (
    RuntimeOperationsReadinessCheck,
    RuntimeOperationsReadinessReport,
    RuntimePreflightStatus,
)
from trading_app.runtime.paper import AlwaysOnPaperRuntimeConfig
from trading_app.runtime.persistence import RuntimePersistenceStore
from trading_app.schemas import DataFeed, TradingModel, validate_symbol

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
_ENV_TEMPLATE_EXPECTED_VALUES = {
    "ALPACA_API_KEY": "replace-with-paper-api-key",
    "ALPACA_SECRET_KEY": "replace-with-paper-secret-key",
    "ALPACA_LIVE_TRADING_ENABLED": "false",
}


class RuntimeArtifactLayout(TradingModel):
    root: str = Field(min_length=1)
    state_dir: str = Field(min_length=1)
    journal_dir: str = Field(min_length=1)
    reports_dir: str = Field(min_length=1)
    learning_dir: str = Field(min_length=1)


class RuntimeOperationsProfile(TradingModel):
    name: str = Field(default="alpaca-paper-local", min_length=1)
    mode: str = Field(default="Alpaca Paper", min_length=1)
    dashboard_url: str = Field(min_length=1)
    dashboard_local_only: bool
    feed: DataFeed
    symbols: tuple[str, ...]
    env_template_path: str = Field(default=".env.example", min_length=1)
    preflight_command: str = Field(min_length=1)
    monitor_only_dry_run_command: str = Field(min_length=1)
    startup_command: str = Field(min_length=1)
    dependency_setup_steps: tuple[str, ...]
    shutdown_steps: tuple[str, ...]
    emergency_stop_steps: tuple[str, ...]
    artifact_layout: RuntimeArtifactLayout
    process_supervision_recommendation: str = Field(min_length=1)
    warnings: tuple[str, ...] = ()


def build_operations_profile(
    *,
    output_dir: Path | str = "data/runtime",
    dashboard_host: str = "127.0.0.1",
    dashboard_port: int = 8765,
    feed: DataFeed = DataFeed.IEX,
    symbols: tuple[str, ...] | None = None,
) -> RuntimeOperationsProfile:
    """Return the recommended local operations profile for paper trading."""

    resolved_symbols = tuple(
        validate_symbol(symbol)
        for symbol in (symbols or AlwaysOnPaperRuntimeConfig().symbols)
    )
    output_path = Path(output_dir)
    dashboard_local_only = dashboard_host in _LOCAL_HOSTS
    warnings = []
    if feed == DataFeed.IEX:
        warnings.append("IEX/free data is development-grade.")
    if not dashboard_local_only:
        warnings.append("Dashboard host is not local-only; preflight should fail.")
    if not _is_ignored_runtime_path(output_path):
        warnings.append(
            "Runtime output should stay under an ignored local data folder."
        )

    symbol_arg = ",".join(resolved_symbols)
    base_args = (
        f"--symbols {symbol_arg} --feed {feed.value} "
        f"--output-dir {output_path} --dashboard-host {dashboard_host}"
    )
    return RuntimeOperationsProfile(
        dashboard_url=f"http://{dashboard_host}:{dashboard_port}",
        dashboard_local_only=dashboard_local_only,
        feed=feed,
        symbols=resolved_symbols,
        preflight_command=f"python -m trading_app.runtime.preflight {base_args}",
        monitor_only_dry_run_command=(
            f"python -m trading_app.runtime.dry_run {base_args}"
        ),
        startup_command=(
            "python -m trading_app.runtime.run_alpaca_paper "
            f"{base_args} --dashboard-port {dashboard_port} "
            "--monitor-only-dry-run-first"
        ),
        dependency_setup_steps=(
            "Install Python 3.12 or newer; do not run the paper runtime on "
            "older Python versions.",
            "Install uv if it is not already available.",
            "Run uv sync --dev from the project root.",
            "Run uv run pytest and uv run ruff check before supervised paper runs.",
            "Keep Alpaca credentials in the local shell or local env file only.",
        ),
        shutdown_steps=(
            "Use Ctrl+C in the terminal running the paper runtime.",
            "Confirm the dashboard stops responding on the local URL.",
            "Review data/runtime/state/latest-runtime-snapshot.json.",
            "Review data/runtime/journal/cycles.jsonl for the final cycle.",
            "Confirm no unexpected Alpaca paper orders were submitted.",
        ),
        emergency_stop_steps=(
            "Use the dashboard to enable the paper kill switch if controls are "
            "reachable.",
            "Use the dashboard to pause the runtime if controls are reachable.",
            "Stop the runtime process with Ctrl+C.",
            "Capture or load the latest Alpaca paper statement.",
            "Run statement reconciliation before allowing any new paper orders.",
            "Run post-run review and keep paper orders blocked until evidence "
            "is clean.",
        ),
        artifact_layout=RuntimeArtifactLayout(
            root=str(output_path),
            state_dir=str(output_path / "state"),
            journal_dir=str(output_path / "journal"),
            reports_dir=str(output_path / "reports"),
            learning_dir=str(output_path / "learning"),
        ),
        process_supervision_recommendation=(
            "Run manually first. After repeated clean paper soaks, use launchd on "
            "macOS or systemd on Linux to keep this same command alive."
        ),
        warnings=tuple(warnings),
    )


class RuntimeOperationsReadinessAuditor:
    """Audit local paper-runtime operating procedures and startup posture."""

    def __init__(
        self,
        *,
        output_dir: Path | str = "data/runtime",
        profile_output_dir: Path | str = "data/runtime",
        profile: RuntimeOperationsProfile | None = None,
        persistence_store: RuntimePersistenceStore | None = None,
        working_dir: Path | str = ".",
        persist_report: bool = True,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.profile_output_dir = Path(profile_output_dir)
        self.profile = profile
        self.store = persistence_store or RuntimePersistenceStore(self.output_dir)
        self.working_dir = Path(working_dir)
        self.persist_report = persist_report

    def audit(
        self, *, as_of: datetime | None = None
    ) -> RuntimeOperationsReadinessReport:
        now = as_of or datetime.now(tz=UTC)
        profile = self.profile or build_operations_profile(
            output_dir=self.profile_output_dir
        )
        checks = (
            _paper_only_profile_check(profile),
            _local_dashboard_check(profile),
            _artifact_layout_check(profile, self.working_dir),
            _dependency_setup_check(profile, self.working_dir),
            _env_template_check(self.working_dir / profile.env_template_path),
            _runbook_check(self.working_dir / "PAPER_RUNTIME_OPERATOR_RUNBOOK.md"),
            _emergency_stop_check(profile),
            _supervisor_template_check(profile, self.working_dir),
        )
        failures = sum(
            1 for check in checks if check.status == RuntimePreflightStatus.FAILED
        )
        status = (
            RuntimePreflightStatus.FAILED if failures else RuntimePreflightStatus.PASSED
        )
        report = RuntimeOperationsReadinessReport(
            as_of=now,
            status=status,
            passed=status == RuntimePreflightStatus.PASSED,
            output_dir=str(self.output_dir),
            dashboard_url=profile.dashboard_url,
            startup_command=profile.startup_command,
            checks=checks,
            summary=_operations_summary(status, failures),
        )
        if self.persist_report:
            markdown_path = write_operations_readiness_markdown_report(
                report,
                self.output_dir / "reports",
            )
            report = report.model_copy(update={"markdown_path": str(markdown_path)})
            self.store.persist_operations_readiness_report(
                report,
                markdown_path=markdown_path,
            )
        return report


def render_operations_profile_markdown(profile: RuntimeOperationsProfile) -> str:
    """Render the operations profile as operator-facing Markdown."""

    lines = [
        f"# Runtime Operations Profile: {profile.name}",
        "",
        "This profile is for Alpaca paper trading only. It does not enable live money.",
        "",
        "## Startup",
        "",
        "Recommended one-command startup:",
        "",
        "```bash",
        profile.startup_command,
        "```",
        "",
        "This command runs preflight, runs a monitor-only dry run, then starts the "
        "always-on paper runtime if the safety checks pass.",
        "",
        "## Dashboard",
        "",
        f"- URL: {profile.dashboard_url}",
        f"- Local-only: {'yes' if profile.dashboard_local_only else 'no'}",
        "",
        "## Artifact Layout",
        "",
        f"- Root: `{profile.artifact_layout.root}`",
        f"- State: `{profile.artifact_layout.state_dir}`",
        f"- Journal: `{profile.artifact_layout.journal_dir}`",
        f"- Reports: `{profile.artifact_layout.reports_dir}`",
        f"- Learning: `{profile.artifact_layout.learning_dir}`",
        "",
        "## Dependency Installation",
    ]
    lines.extend(f"- {step}" for step in profile.dependency_setup_steps)
    lines.extend(
        [
            "",
            "## Separate Checks",
            "",
            "```bash",
            profile.preflight_command,
            profile.monitor_only_dry_run_command,
            "```",
            "",
            "## Shutdown",
        ]
    )
    lines.extend(f"- {step}" for step in profile.shutdown_steps)
    lines.extend(
        [
            "",
            "## Emergency Stop",
        ]
    )
    lines.extend(f"- {step}" for step in profile.emergency_stop_steps)
    lines.extend(
        [
            "",
            "## Process Supervision",
            "",
            profile.process_supervision_recommendation,
            "",
            "## Warnings",
        ]
    )
    if profile.warnings:
        lines.extend(f"- {warning}" for warning in profile.warnings)
    else:
        lines.append("- No warnings.")
    return "\n".join(lines) + "\n"


def render_operations_readiness_text(
    report: RuntimeOperationsReadinessReport,
) -> str:
    """Render compact operations-readiness audit status."""

    lines = [
        f"Operations readiness status: {report.status.value}",
        f"Passed: {_yes_no(report.passed)}",
        f"Output dir: {report.output_dir}",
        f"Markdown report: {report.markdown_path or 'not written'}",
        f"Dashboard URL: {report.dashboard_url}",
        report.summary,
        "",
        "Checks:",
    ]
    for check in report.checks:
        evidence = "; ".join(check.evidence) if check.evidence else "no evidence"
        lines.append(f"- {check.name}: {check.status.value} - {check.message}")
        lines.append(f"  Evidence: {evidence}")
    return "\n".join(lines)


def render_operations_readiness_markdown(
    report: RuntimeOperationsReadinessReport,
) -> str:
    """Render operations-readiness audit Markdown."""

    lines = [
        "# Paper Runtime Operations Readiness Audit",
        "",
        "> Paper trading only. This audit does not install or start the runtime.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.status.value}`",
        f"- Passed: `{_yes_no(report.passed)}`",
        f"- Audited at: `{report.as_of.isoformat()}`",
        f"- Output directory: `{report.output_dir}`",
        f"- Dashboard URL: `{report.dashboard_url}`",
        "",
        "Startup command:",
        "",
        "```bash",
        report.startup_command,
        "```",
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


def write_operations_readiness_markdown_report(
    report: RuntimeOperationsReadinessReport,
    reports_dir: Path | str,
) -> Path:
    """Write operations-readiness Markdown and return its path."""

    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"operations-readiness-{_timestamp_id(report.as_of)}.md"
    path.write_text(render_operations_readiness_markdown(report), encoding="utf-8")
    return path


def render_launchd_plist(
    profile: RuntimeOperationsProfile,
    *,
    working_dir: Path | str,
    env_file: Path | str = ".env.local",
) -> str:
    """Render a macOS launchd template for the paper runtime."""

    workdir = Path(working_dir)
    env_path = _resolve_env_file(workdir, env_file)
    output_root = Path(profile.artifact_layout.root)
    log_dir = output_root / "logs"
    shell_command = (
        f"cd {shlex.quote(str(workdir))} && "
        f"set -a; [ -f {shlex.quote(str(env_path))} ] && "
        f". {shlex.quote(str(env_path))}; set +a; "
        f"exec {profile.startup_command}"
    )
    args = ("/bin/zsh", "-lc", shell_command)
    argument_xml = "\n".join(
        f"    <string>{escape(argument)}</string>" for argument in args
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.trading-app.alpaca-paper</string>
  <key>ProgramArguments</key>
  <array>
{argument_xml}
  </array>
  <key>WorkingDirectory</key>
  <string>{escape(str(workdir))}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <false/>
  <key>StandardOutPath</key>
  <string>{escape(str(log_dir / "launchd.out.log"))}</string>
  <key>StandardErrorPath</key>
  <string>{escape(str(log_dir / "launchd.err.log"))}</string>
</dict>
</plist>
"""


def render_systemd_unit(
    profile: RuntimeOperationsProfile,
    *,
    working_dir: Path | str,
    env_file: Path | str = ".env.local",
) -> str:
    """Render a Linux systemd user-service template for the paper runtime."""

    workdir = Path(working_dir)
    env_path = _resolve_env_file(workdir, env_file)
    return f"""[Unit]
Description=Trading App Alpaca Paper Runtime
After=network-online.target

[Service]
Type=simple
WorkingDirectory={workdir}
EnvironmentFile=-{env_path}
ExecStart={profile.startup_command}
Restart=on-failure
RestartSec=30
KillSignal=SIGINT
TimeoutStopSec=45

[Install]
WantedBy=default.target
"""


def write_supervisor_templates(
    profile: RuntimeOperationsProfile,
    output_dir: Path | str,
    *,
    working_dir: Path | str,
    env_file: Path | str = ".env.local",
) -> tuple[Path, Path]:
    """Write local process-supervisor templates and return their paths."""

    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    launchd_path = directory / "com.trading-app.alpaca-paper.plist"
    systemd_path = directory / "trading-app-alpaca-paper.service"
    launchd_path.write_text(
        render_launchd_plist(profile, working_dir=working_dir, env_file=env_file),
        encoding="utf-8",
    )
    systemd_path.write_text(
        render_systemd_unit(profile, working_dir=working_dir, env_file=env_file),
        encoding="utf-8",
    )
    return launchd_path, systemd_path


def main(argv: list[str] | None = None) -> int:
    """Print or write the local paper-runtime operations profile."""

    parser = argparse.ArgumentParser(description="Render runtime operations profile.")
    parser.add_argument("--symbols", default="")
    parser.add_argument("--feed", default=DataFeed.IEX.value)
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument("--dashboard-host", default="127.0.0.1")
    parser.add_argument("--dashboard-port", type=int, default=8765)
    parser.add_argument("--write", default="")
    parser.add_argument("--write-supervisor-dir", default="")
    parser.add_argument("--working-dir", default=str(Path.cwd()))
    parser.add_argument("--env-file", default=".env.local")
    parser.add_argument("--audit", action="store_true")
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    symbols = parse_symbol_list(args.symbols) if args.symbols else None
    try:
        profile = build_operations_profile(
            output_dir=args.output_dir,
            dashboard_host=args.dashboard_host,
            dashboard_port=args.dashboard_port,
            feed=DataFeed(args.feed.upper()),
            symbols=symbols,
        )
    except ValueError as error:
        parser.error(str(error))
    if args.audit:
        report = RuntimeOperationsReadinessAuditor(
            output_dir=args.output_dir,
            profile=profile,
            working_dir=args.working_dir,
            persist_report=not args.no_persist,
        ).audit()
        print(
            report.model_dump_json()
            if args.json
            else render_operations_readiness_text(report),
            end="\n",
        )
        return 0 if report.passed else 1
    text = (
        profile.model_dump_json()
        if args.json
        else render_operations_profile_markdown(profile)
    )
    if args.write:
        path = Path(args.write)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    if args.write_supervisor_dir:
        launchd_path, systemd_path = write_supervisor_templates(
            profile,
            args.write_supervisor_dir,
            working_dir=args.working_dir,
            env_file=args.env_file,
        )
        if not args.json:
            print(f"Supervisor templates written: {launchd_path}, {systemd_path}")
    return 0


def _paper_only_profile_check(
    profile: RuntimeOperationsProfile,
) -> RuntimeOperationsReadinessCheck:
    command = profile.startup_command
    safe = (
        profile.mode == "Alpaca Paper"
        and "run_alpaca_paper" in command
        and "--monitor-only-dry-run-first" in command
        and "--skip-preflight" not in command
        and "live" not in command.lower()
    )
    return _readiness_check(
        "paper_only_startup",
        safe,
        "Startup profile is paper-only and starts with monitor-only dry run.",
        "Startup profile is not clearly paper-only.",
        (
            f"mode={profile.mode}",
            f"monitor_only_first={'--monitor-only-dry-run-first' in command}",
            f"skip_preflight={'--skip-preflight' in command}",
        ),
    )


def _local_dashboard_check(
    profile: RuntimeOperationsProfile,
) -> RuntimeOperationsReadinessCheck:
    return _readiness_check(
        "local_dashboard_binding",
        profile.dashboard_local_only,
        "Dashboard binding is local-only.",
        "Dashboard binding is not local-only.",
        (f"dashboard_url={profile.dashboard_url}",),
    )


def _artifact_layout_check(
    profile: RuntimeOperationsProfile,
    working_dir: Path,
) -> RuntimeOperationsReadinessCheck:
    gitignore = working_dir / ".gitignore"
    gitignore_text = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    ignored = any(line.strip() == "data/" for line in gitignore_text.splitlines())
    layout_safe = (
        _is_ignored_runtime_path(Path(profile.artifact_layout.root)) and ignored
    )
    return _readiness_check(
        "artifact_layout",
        layout_safe,
        "Runtime artifacts are configured under an ignored local data folder.",
        "Runtime artifacts are not clearly isolated under ignored local data.",
        (
            f"root={profile.artifact_layout.root}",
            f"gitignore_data={'yes' if ignored else 'no'}",
        ),
    )


def _dependency_setup_check(
    profile: RuntimeOperationsProfile,
    working_dir: Path,
) -> RuntimeOperationsReadinessCheck:
    pyproject = working_dir / "pyproject.toml"
    python_version = working_dir / ".python-version"
    lockfile = working_dir / "uv.lock"
    pyproject_text = pyproject.read_text(encoding="utf-8") if pyproject.exists() else ""
    profile_text = " ".join(profile.dependency_setup_steps).lower()
    safe = (
        'requires-python = ">=3.12"' in pyproject_text
        and python_version.exists()
        and python_version.read_text(encoding="utf-8").strip().startswith("3.12")
        and lockfile.exists()
        and "uv sync --dev" in profile_text
        and "uv run pytest" in profile_text
        and "uv run ruff check" in profile_text
    )
    return _readiness_check(
        "dependency_setup",
        safe,
        "Dependency setup is documented and pinned to Python 3.12 with uv.",
        "Dependency setup is incomplete or not pinned to Python 3.12 with uv.",
        (
            f"pyproject={pyproject.exists()}",
            f"python_version={python_version.exists()}",
            f"uv_lock={lockfile.exists()}",
        ),
    )


def _env_template_check(path: Path) -> RuntimeOperationsReadinessCheck:
    if not path.exists():
        return _readiness_check(
            "env_template",
            False,
            "Environment template is safe.",
            "Environment template is missing.",
            (f"path={path}",),
        )
    text = path.read_text(encoding="utf-8")
    values = _env_template_values(text)
    assignment_gaps = _env_template_assignment_gaps(values)
    endpoint_violations = alpaca_paper_boundary_violations(values)
    safe = (
        not assignment_gaps
        and "key-present" not in text
        and "secret-present" not in text
        and not endpoint_violations
    )
    return _readiness_check(
        "env_template",
        safe,
        "Environment template uses placeholders and keeps live trading disabled.",
        "Environment template is missing required paper-only placeholders.",
        (
            f"path={path}",
            *tuple(f"assignment_gap={gap}" for gap in assignment_gaps),
            *tuple(
                f"endpoint_violation={violation}" for violation in endpoint_violations
            ),
        ),
    )


def _env_template_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        clean_name = name.strip()
        if clean_name.startswith("export "):
            clean_name = clean_name.split(None, 1)[1].strip()
        values[clean_name] = value.strip().strip('"').strip("'")
    return values


def _env_template_assignment_gaps(values: dict[str, str]) -> tuple[str, ...]:
    gaps: list[str] = []
    for name, expected in _ENV_TEMPLATE_EXPECTED_VALUES.items():
        actual = values.get(name)
        if actual is None:
            gaps.append(f"{name}=missing")
        elif actual != expected:
            gaps.append(f"{name}=not_placeholder")
    return tuple(gaps)


def _runbook_check(path: Path) -> RuntimeOperationsReadinessCheck:
    if not path.exists():
        return _readiness_check(
            "operator_runbook",
            False,
            "Operator runbook covers startup, shutdown, and recovery.",
            "Operator runbook is missing.",
            (f"path={path}",),
        )
    text = path.read_text(encoding="utf-8")
    required_phrases = (
        "python -m trading_app.runtime.run_alpaca_paper --monitor-only-dry-run-first",
        "python -m trading_app.runtime.preflight",
        "python -m trading_app.runtime.dry_run",
        "python -m trading_app.runtime.recovery --output-dir data/runtime",
        "python -m trading_app.runtime.review --output-dir data/runtime",
        "Dependency Installation",
        "Emergency Stop Procedure",
        "Stop The Runtime",
    )
    missing = tuple(phrase for phrase in required_phrases if phrase not in text)
    return _readiness_check(
        "operator_runbook",
        not missing,
        "Operator runbook covers startup, shutdown, review, and recovery.",
        "Operator runbook is missing required operating steps.",
        tuple(f"missing={phrase}" for phrase in missing) or (f"path={path}",),
    )


def _emergency_stop_check(
    profile: RuntimeOperationsProfile,
) -> RuntimeOperationsReadinessCheck:
    text = " ".join(profile.emergency_stop_steps).lower()
    required_terms = (
        "paper kill switch",
        "pause",
        "ctrl+c",
        "statement",
        "reconciliation",
        "post-run review",
    )
    missing = tuple(term for term in required_terms if term not in text)
    return _readiness_check(
        "emergency_stop_procedure",
        not missing,
        "Emergency stop procedure covers kill switch, pause, stop, and review.",
        "Emergency stop procedure is incomplete.",
        tuple(f"missing={term}" for term in missing)
        or (f"steps={len(profile.emergency_stop_steps)}",),
    )


def _supervisor_template_check(
    profile: RuntimeOperationsProfile,
    working_dir: Path,
) -> RuntimeOperationsReadinessCheck:
    launchd = render_launchd_plist(profile, working_dir=working_dir)
    systemd = render_systemd_unit(profile, working_dir=working_dir)
    combined = f"{launchd}\n{systemd}"
    safe = (
        "--monitor-only-dry-run-first" in combined
        and "--skip-preflight" not in combined
        and "127.0.0.1" in combined
        and "ALPACA_SECRET_KEY=" not in combined
        and "ALPACA_API_KEY=" not in combined
        and "run_alpaca_paper" in combined
    )
    return _readiness_check(
        "supervisor_templates",
        safe,
        "Supervisor templates are paper-only, local-dashboard, and secret-safe.",
        "Supervisor templates are not ready for paper-only review.",
        (
            f"launchd_bytes={len(launchd)}",
            f"systemd_bytes={len(systemd)}",
        ),
    )


def _readiness_check(
    name: str,
    passed: bool,
    passed_message: str,
    failed_message: str,
    evidence: tuple[str, ...] = (),
) -> RuntimeOperationsReadinessCheck:
    return RuntimeOperationsReadinessCheck(
        name=name,
        status=RuntimePreflightStatus.PASSED
        if passed
        else RuntimePreflightStatus.FAILED,
        message=passed_message if passed else failed_message,
        evidence=evidence,
    )


def _operations_summary(status: RuntimePreflightStatus, failures: int) -> str:
    if status == RuntimePreflightStatus.PASSED:
        return "Operations readiness passed; local paper startup posture is clean."
    return (
        f"Operations readiness found {failures} failed check(s). "
        "Fix the operating posture before a supervised paper run."
    )


def _is_ignored_runtime_path(path: Path) -> bool:
    return str(path) == "data" or str(path).startswith("data/")


def _resolve_env_file(working_dir: Path, env_file: Path | str) -> Path:
    path = Path(env_file)
    return path if path.is_absolute() else working_dir / path


def _timestamp_id(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%S")


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


if __name__ == "__main__":
    raise SystemExit(main())
