from __future__ import annotations

from pathlib import Path

import pytest

from trading_app.runtime import (
    RuntimeOperationsProfile,
    RuntimeOperationsReadinessAuditor,
    RuntimePreflightStatus,
    build_operations_profile,
    render_launchd_plist,
    render_operations_profile_markdown,
    render_operations_readiness_markdown,
    render_operations_readiness_text,
    render_systemd_unit,
    write_supervisor_templates,
)
from trading_app.runtime.ops import main as ops_main
from trading_app.schemas import DataFeed


def test_operations_profile_defines_local_startup_and_artifact_layout() -> None:
    profile = build_operations_profile(
        output_dir="data/runtime",
        dashboard_host="127.0.0.1",
        dashboard_port=8765,
        feed=DataFeed.IEX,
        symbols=("SPY", "XLK"),
    )

    assert profile.mode == "Alpaca Paper"
    assert profile.dashboard_local_only
    assert profile.dashboard_url == "http://127.0.0.1:8765"
    assert "--monitor-only-dry-run-first" in profile.startup_command
    assert "python -m trading_app.runtime.run_alpaca_paper" in (profile.startup_command)
    assert any("uv sync --dev" in step for step in profile.dependency_setup_steps)
    assert any("Python 3.12" in step for step in profile.dependency_setup_steps)
    assert any("paper kill switch" in step for step in profile.emergency_stop_steps)
    assert any("post-run review" in step for step in profile.emergency_stop_steps)
    assert profile.artifact_layout.root == "data/runtime"
    assert profile.artifact_layout.state_dir == "data/runtime/state"
    assert profile.artifact_layout.journal_dir == "data/runtime/journal"
    assert profile.artifact_layout.reports_dir == "data/runtime/reports"
    assert profile.artifact_layout.learning_dir == "data/runtime/learning"
    assert "IEX/free data is development-grade." in profile.warnings


def test_operations_profile_flags_public_dashboard_binding() -> None:
    profile = build_operations_profile(dashboard_host="0.0.0.0")

    assert not profile.dashboard_local_only
    assert any("not local-only" in warning for warning in profile.warnings)


def test_operations_profile_markdown_is_operator_safe() -> None:
    markdown = render_operations_profile_markdown(build_operations_profile())

    assert "Recommended one-command startup" in markdown
    assert "Shutdown" in markdown
    assert "Dependency Installation" in markdown
    assert "uv sync --dev" in markdown
    assert "Emergency Stop" in markdown
    assert "paper kill switch" in markdown
    assert "data/runtime/state" in markdown
    assert "replace-with" not in markdown
    assert "ALPACA_SECRET_KEY=" not in markdown
    assert "live money" in markdown.lower()


def test_env_example_contains_placeholders_not_real_secrets() -> None:
    text = Path(".env.example").read_text(encoding="utf-8")

    assert "ALPACA_API_KEY=replace-with-paper-api-key" in text
    assert "ALPACA_SECRET_KEY=replace-with-paper-secret-key" in text
    assert "ALPACA_LIVE_TRADING_ENABLED=false" in text
    assert "paper-api.alpaca.markets" in text
    assert "APCA_API_BASE_URL=https://api.alpaca.markets" not in text
    assert "data/runtime" in text
    assert "key-present" not in text
    assert "secret-present" not in text


def test_local_env_secret_files_are_ignored() -> None:
    text = Path(".gitignore").read_text(encoding="utf-8")

    assert ".env" in text
    assert ".env.local" in text
    assert ".env.paper" in text
    assert ".env.*.local" in text
    assert "*.local.env" in text
    assert ".env.example" not in text


def test_operations_profile_cli_prints_and_writes(tmp_path, capsys) -> None:
    output_path = tmp_path / "ops-profile.md"

    printed_status = ops_main(["--symbols", "SPY,XLK", "--feed", "SIP"])
    printed = capsys.readouterr().out
    written_status = ops_main(["--symbols", "SPY,XLK", "--write", str(output_path)])
    written = output_path.read_text(encoding="utf-8")

    assert printed_status == 0
    assert "Runtime Operations Profile" in printed
    assert "SIP" in printed
    assert written_status == 0
    assert "Runtime Operations Profile" in written


def test_operations_profile_json_cli_is_schema_compatible(capsys) -> None:
    status = ops_main(["--json", "--symbols", "SPY"])
    payload = capsys.readouterr().out

    profile = RuntimeOperationsProfile.model_validate_json(payload)

    assert status == 0
    assert profile.symbols == ("SPY",)
    assert profile.dashboard_local_only


def test_operations_profile_cli_rejects_lowercase_symbols_without_normalizing(
    capsys,
) -> None:
    with pytest.raises(SystemExit) as error:
        ops_main(["--json", "--symbols", "spy"])
    output = capsys.readouterr()

    assert error.value.code == 2
    assert "symbol must be uppercase" in output.err


def test_supervisor_templates_are_paper_only_and_secret_safe(tmp_path) -> None:
    profile = build_operations_profile(
        output_dir="data/runtime",
        dashboard_host="127.0.0.1",
        dashboard_port=8765,
        symbols=("SPY",),
    )
    launchd = render_launchd_plist(
        profile,
        working_dir=Path.cwd(),
        env_file=".env.paper",
    )
    systemd = render_systemd_unit(
        profile,
        working_dir=Path.cwd(),
        env_file=".env.paper",
    )

    assert "com.trading-app.alpaca-paper" in launchd
    assert "Trading App Alpaca Paper Runtime" in systemd
    assert "python -m trading_app.runtime.run_alpaca_paper" in launchd
    assert "python -m trading_app.runtime.run_alpaca_paper" in systemd
    assert "--monitor-only-dry-run-first" in launchd
    assert "--monitor-only-dry-run-first" in systemd
    assert "127.0.0.1" in launchd
    assert "127.0.0.1" in systemd
    assert ".env.paper" in launchd
    assert ".env.paper" in systemd
    assert "ALPACA_SECRET_KEY=" not in launchd
    assert "ALPACA_SECRET_KEY=" not in systemd
    assert "ALPACA_API_KEY=" not in launchd
    assert "ALPACA_API_KEY=" not in systemd

    launchd_path, systemd_path = write_supervisor_templates(
        profile,
        tmp_path,
        working_dir=Path.cwd(),
        env_file=".env.paper",
    )

    assert launchd_path.name == "com.trading-app.alpaca-paper.plist"
    assert systemd_path.name == "trading-app-alpaca-paper.service"
    assert launchd_path.exists()
    assert systemd_path.exists()


def test_operations_profile_cli_writes_supervisor_templates(tmp_path, capsys) -> None:
    status = ops_main(
        [
            "--symbols",
            "SPY",
            "--write-supervisor-dir",
            str(tmp_path),
            "--working-dir",
            str(Path.cwd()),
            "--env-file",
            ".env.paper",
        ]
    )
    output = capsys.readouterr().out

    assert status == 0
    assert "Supervisor templates written" in output
    assert (tmp_path / "com.trading-app.alpaca-paper.plist").exists()
    assert (tmp_path / "trading-app-alpaca-paper.service").exists()


def test_operations_readiness_audit_passes_and_persists(tmp_path) -> None:
    report = RuntimeOperationsReadinessAuditor(output_dir=tmp_path).audit()
    text = render_operations_readiness_text(report)
    markdown = render_operations_readiness_markdown(report)

    assert report.passed
    assert report.status == RuntimePreflightStatus.PASSED
    assert report.dashboard_url == "http://127.0.0.1:8765"
    assert "--monitor-only-dry-run-first" in report.startup_command
    assert {check.name for check in report.checks} == {
        "paper_only_startup",
        "local_dashboard_binding",
        "artifact_layout",
        "dependency_setup",
        "env_template",
        "operator_runbook",
        "emergency_stop_procedure",
        "supervisor_templates",
    }
    assert report.markdown_path is not None
    assert Path(report.markdown_path).exists()
    assert "Operations readiness status" in text
    assert "Paper Runtime Operations Readiness Audit" in markdown
    assert (tmp_path / "state" / "latest-operations-readiness-report.json").exists()
    assert (tmp_path / "journal" / "operations-readiness.jsonl").exists()


def test_operations_readiness_audit_fails_public_dashboard(tmp_path) -> None:
    profile = build_operations_profile(dashboard_host="0.0.0.0")

    report = RuntimeOperationsReadinessAuditor(
        output_dir=tmp_path,
        profile=profile,
    ).audit()
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert by_name["local_dashboard_binding"].status == RuntimePreflightStatus.FAILED


def test_operations_readiness_audit_rejects_preflight_bypass(tmp_path) -> None:
    profile = build_operations_profile().model_copy(
        update={
            "startup_command": (
                "python -m trading_app.runtime.run_alpaca_paper "
                "--monitor-only-dry-run-first --skip-preflight"
            )
        }
    )

    report = RuntimeOperationsReadinessAuditor(
        output_dir=tmp_path,
        profile=profile,
    ).audit()
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert by_name["paper_only_startup"].status == RuntimePreflightStatus.FAILED
    assert any(
        "skip_preflight=True" in item for item in by_name["paper_only_startup"].evidence
    )


def test_operations_readiness_audit_rejects_live_endpoint_env_template(
    tmp_path,
) -> None:
    bad_env = tmp_path / "bad.env"
    bad_env.write_text(
        "\n".join(
            (
                "ALPACA_API_KEY=replace-with-paper-api-key",
                "ALPACA_SECRET_KEY=replace-with-paper-secret-key",
                "ALPACA_LIVE_TRADING_ENABLED=false",
                "export APCA_API_BASE_URL='https://api.alpaca.markets'",
            )
        ),
        encoding="utf-8",
    )
    profile = build_operations_profile().model_copy(
        update={"env_template_path": str(bad_env)}
    )

    report = RuntimeOperationsReadinessAuditor(
        output_dir=tmp_path / "runtime",
        profile=profile,
    ).audit()
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert by_name["env_template"].status == RuntimePreflightStatus.FAILED
    assert any(
        "endpoint_violation=APCA_API_BASE_URL=live_endpoint" in item
        for item in by_name["env_template"].evidence
    )


def test_operations_readiness_audit_rejects_active_secret_env_assignment(
    tmp_path,
) -> None:
    bad_env = tmp_path / "secret.env"
    bad_env.write_text(
        "\n".join(
            (
                "ALPACA_API_KEY=replace-with-paper-api-key",
                "ALPACA_SECRET_KEY=replace-with-paper-secret-key",
                "ALPACA_LIVE_TRADING_ENABLED=false",
                "ALPACA_API_KEY=paper-real-key",
            )
        ),
        encoding="utf-8",
    )
    profile = build_operations_profile().model_copy(
        update={"env_template_path": str(bad_env)}
    )

    report = RuntimeOperationsReadinessAuditor(
        output_dir=tmp_path / "runtime",
        profile=profile,
    ).audit()
    by_name = {check.name: check for check in report.checks}

    assert not report.passed
    assert by_name["env_template"].status == RuntimePreflightStatus.FAILED
    assert any(
        "assignment_gap=ALPACA_API_KEY=not_placeholder" in item
        for item in by_name["env_template"].evidence
    )


def test_operations_profile_cli_audit_outputs_json_and_exit_codes(capsys) -> None:
    success = ops_main(["--audit", "--json", "--no-persist"])
    failure = ops_main(
        [
            "--audit",
            "--dashboard-host",
            "0.0.0.0",
            "--json",
            "--no-persist",
        ]
    )
    output = capsys.readouterr().out

    assert success == 0
    assert failure == 1
    assert '"passed":true' in output
    assert '"passed":false' in output
