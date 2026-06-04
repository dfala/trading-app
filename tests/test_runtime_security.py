from __future__ import annotations

from datetime import UTC, datetime

from trading_app.runtime import (
    RuntimePersistenceStore,
    RuntimePreflightStatus,
    RuntimeSecretScanner,
    RuntimeSecretScanReport,
    render_secret_scan_text,
)
from trading_app.runtime.security import main as security_main

NOW = datetime(2026, 5, 29, 23, tzinfo=UTC)
ENV = {
    "ALPACA_API_KEY": "paper-key-value-123",
    "ALPACA_SECRET_KEY": "paper-secret-value-456",
}


def test_secret_scanner_passes_safe_artifacts_and_persists(tmp_path) -> None:
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "journal").mkdir(parents=True)
    (tmp_path / "state" / "latest-runtime-snapshot.json").write_text(
        '{"status":"running","credential":"ALPACA_API_KEY=present"}',
        encoding="utf-8",
    )
    (tmp_path / "journal" / "events.jsonl").write_text(
        '{"message":"credentials present but not rendered"}\n',
        encoding="utf-8",
    )

    report = RuntimeSecretScanner(
        output_dir=tmp_path,
        env=ENV,
        persistence_store=RuntimePersistenceStore(tmp_path),
    ).scan(as_of=NOW)

    assert report.passed
    assert report.status == RuntimePreflightStatus.PASSED
    assert report.files_scanned == 2
    assert report.secret_names_checked == ("ALPACA_API_KEY", "ALPACA_SECRET_KEY")
    assert not report.findings
    assert (tmp_path / "state" / "latest-secret-scan-report.json").exists()
    assert (tmp_path / "journal" / "secret-scans.jsonl").exists()


def test_secret_scanner_detects_leaks_without_rendering_secret_values(tmp_path) -> None:
    (tmp_path / "reports").mkdir(parents=True)
    (tmp_path / "reports" / "daily-report.md").write_text(
        "broker auth accidentally included paper-secret-value-456",
        encoding="utf-8",
    )

    report = RuntimeSecretScanner(
        output_dir=tmp_path,
        env=ENV,
        persistence_store=RuntimePersistenceStore(tmp_path),
        persist_report=False,
    ).scan(as_of=NOW)
    text = render_secret_scan_text(report)

    assert not report.passed
    assert report.status == RuntimePreflightStatus.FAILED
    assert report.findings[0].path == "reports/daily-report.md"
    assert report.findings[0].secret_name == "ALPACA_SECRET_KEY"
    assert "paper-secret-value-456" not in text
    assert "paper-key-value-123" not in text


def test_secret_scanner_normalizes_quoted_env_values_before_matching(
    tmp_path,
) -> None:
    (tmp_path / "reports").mkdir(parents=True)
    (tmp_path / "reports" / "daily-report.md").write_text(
        "broker auth accidentally included paper-secret-value-456",
        encoding="utf-8",
    )

    report = RuntimeSecretScanner(
        output_dir=tmp_path,
        env={
            "ALPACA_API_KEY": " 'paper-key-value-123' ",
            "ALPACA_SECRET_KEY": ' "paper-secret-value-456" ',
        },
        persist_report=False,
    ).scan(as_of=NOW)

    assert not report.passed
    assert report.secret_names_checked == ("ALPACA_API_KEY", "ALPACA_SECRET_KEY")
    assert report.findings[0].secret_name == "ALPACA_SECRET_KEY"


def test_secret_scanner_scans_extra_dashboard_or_log_paths(tmp_path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    dashboard_capture = tmp_path / "next-dashboard-capture.html"
    dashboard_capture.write_text(
        "<html>accidental paper-key-value-123 leak</html>",
        encoding="utf-8",
    )

    report = RuntimeSecretScanner(
        output_dir=runtime_dir,
        scan_paths=(dashboard_capture,),
        env=ENV,
        persist_report=False,
    ).scan(as_of=NOW)
    text = render_secret_scan_text(report)

    assert not report.passed
    assert report.files_scanned == 1
    assert report.findings[0].path == "next-dashboard-capture.html"
    assert report.findings[0].secret_name == "ALPACA_API_KEY"
    assert str(dashboard_capture) in report.scan_roots
    assert "paper-key-value-123" not in text


def test_secret_scanner_skips_binary_files(tmp_path) -> None:
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "state" / "binary.bin").write_bytes(b"\xff\x00\xff")

    report = RuntimeSecretScanner(
        output_dir=tmp_path,
        env=ENV,
        persist_report=False,
    ).scan(as_of=NOW)

    assert report.passed
    assert report.files_scanned == 0
    assert report.files_skipped == 1


def test_secret_scanner_ignores_placeholder_and_short_values(tmp_path) -> None:
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "state" / "example.json").write_text(
        '{"key":"replace-with-paper-api-key","short":"abc"}',
        encoding="utf-8",
    )

    report = RuntimeSecretScanner(
        output_dir=tmp_path,
        env={
            "ALPACA_API_KEY": "replace-with-paper-api-key",
            "ALPACA_SECRET_KEY": "abc",
        },
        persist_report=False,
    ).scan(as_of=NOW)

    assert report.passed
    assert report.secret_names_checked == ()
    assert "No configured secret values" in report.summary


def test_secret_scanner_ignores_quoted_placeholder_values(tmp_path) -> None:
    (tmp_path / "state").mkdir(parents=True)
    (tmp_path / "state" / "example.json").write_text(
        '{"key":"replace-with-paper-api-key"}',
        encoding="utf-8",
    )

    report = RuntimeSecretScanner(
        output_dir=tmp_path,
        env={
            "ALPACA_API_KEY": "'replace-with-paper-api-key'",
            "ALPACA_SECRET_KEY": '"replace-with-paper-secret-key"',
        },
        persist_report=False,
    ).scan(as_of=NOW)

    assert report.passed
    assert report.secret_names_checked == ()


def test_secret_scan_cli_returns_success_and_failure(
    tmp_path, monkeypatch, capsys
) -> None:
    clean_dir = tmp_path / "clean"
    leak_dir = tmp_path / "leak"
    clean_dir.mkdir()
    leak_dir.mkdir()
    (clean_dir / "safe.json").write_text('{"ok":true}', encoding="utf-8")
    (leak_dir / "bad.json").write_text(
        '{"secret":"paper-key-value-123"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("ALPACA_API_KEY", "paper-key-value-123")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "paper-secret-value-456")

    success = security_main(["--output-dir", str(clean_dir), "--json"])
    failure = security_main(["--output-dir", str(leak_dir), "--json", "--no-persist"])
    output = capsys.readouterr().out

    assert success == 0
    assert failure == 1
    assert '"passed":true' in output
    assert '"passed":false' in output
    assert "paper-key-value-123" not in output


def test_secret_scan_cli_accepts_extra_scan_paths(
    tmp_path,
    monkeypatch,
    capsys,
) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    exported_log = tmp_path / "runtime.log"
    exported_log.write_text("auth=paper-secret-value-456", encoding="utf-8")
    monkeypatch.setenv("ALPACA_API_KEY", "paper-key-value-123")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "paper-secret-value-456")

    failure = security_main(
        [
            "--output-dir",
            str(runtime_dir),
            "--include-path",
            str(exported_log),
            "--json",
            "--no-persist",
        ]
    )
    output = capsys.readouterr().out

    assert failure == 1
    assert '"findings"' in output
    assert "paper-secret-value-456" not in output


def test_secret_scan_report_model_does_not_require_secret_values() -> None:
    payload = {
        "as_of": NOW,
        "status": RuntimePreflightStatus.PASSED,
        "passed": True,
        "output_dir": "data/runtime",
        "files_scanned": 0,
        "files_skipped": 0,
        "secret_names_checked": ("ALPACA_API_KEY",),
        "findings": (),
        "summary": "No leaks.",
    }

    report = RuntimeSecretScanReport.model_validate(payload)

    assert report.passed
