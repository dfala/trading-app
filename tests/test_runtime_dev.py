from __future__ import annotations

from pathlib import Path

from trading_app.runtime import dev as runtime_dev


def test_load_env_file_parses_simple_local_env_values(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# local paper credentials",
                "ALPACA_API_KEY=key-from-file",
                "export ALPACA_SECRET_KEY='secret-from-file'",
                'APCA_API_BASE_URL="https://paper-api.alpaca.markets"',
            ]
        ),
        encoding="utf-8",
    )
    env: dict[str, str] = {}

    loaded = runtime_dev.load_env_file(env_file, environ=env)

    assert loaded
    assert env == {
        "ALPACA_API_KEY": "key-from-file",
        "ALPACA_SECRET_KEY": "secret-from-file",
        "APCA_API_BASE_URL": "https://paper-api.alpaca.markets",
    }


def test_load_env_file_preserves_existing_shell_values(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("ALPACA_API_KEY=key-from-file\n", encoding="utf-8")
    env = {"ALPACA_API_KEY": "key-from-shell"}

    runtime_dev.load_env_file(env_file, environ=env)

    assert env["ALPACA_API_KEY"] == "key-from-shell"


def test_dev_shortcut_loads_env_and_adds_monitor_only_flag(
    tmp_path: Path,
    monkeypatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "ALPACA_API_KEY=key-from-file",
                "ALPACA_SECRET_KEY=secret-from-file",
                "TRADING_APP_FEED=SIP",
                "TRADING_APP_DASHBOARD_PORT=9999",
            ]
        ),
        encoding="utf-8",
    )
    env: dict[str, str] = {}
    captured: dict[str, list[str]] = {}

    def fake_runtime_main(argv: list[str]) -> int:
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(runtime_dev.os, "environ", env)
    monkeypatch.setattr(runtime_dev, "run_alpaca_paper_main", fake_runtime_main)

    result = runtime_dev.main(
        [
            "--env-file",
            str(env_file),
            "--output-dir",
            str(tmp_path / "runtime"),
            "--no-dashboard",
        ]
    )

    assert result == 0
    assert env["ALPACA_API_KEY"] == "key-from-file"
    assert env["ALPACA_SECRET_KEY"] == "secret-from-file"
    assert captured["argv"] == [
        "--output-dir",
        str(tmp_path / "runtime"),
        "--no-dashboard",
        "--feed",
        "SIP",
        "--dashboard-port",
        "9999",
        "--monitor-only-dry-run-first",
        "--dashboard-port-auto-increment",
    ]
