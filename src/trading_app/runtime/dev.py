"""Local developer startup shortcut for the Alpaca paper runtime."""

from __future__ import annotations

import argparse
import os
import re
from collections.abc import MutableMapping, Sequence
from pathlib import Path

from trading_app.alpaca_credentials import normalize_alpaca_env_value
from trading_app.runtime.run_alpaca_paper import main as run_alpaca_paper_main

_DEFAULT_ENV_FILE = ".env"
_MONITOR_ONLY_FLAG = "--monitor-only-dry-run-first"
_DASHBOARD_PORT_AUTO_INCREMENT_FLAG = "--dashboard-port-auto-increment"
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ENV_RUNTIME_DEFAULTS = (
    ("TRADING_APP_SYMBOLS", "--symbols"),
    ("TRADING_APP_FEED", "--feed"),
    ("TRADING_APP_OUTPUT_DIR", "--output-dir"),
    ("TRADING_APP_STARTING_CASH", "--starting-cash"),
    ("TRADING_APP_MANAGED_CAPITAL", "--managed-capital"),
    ("TRADING_APP_MAX_PAPER_SYMBOL_ALLOCATION", "--max-paper-symbol-allocation"),
    (
        "TRADING_APP_MAX_PAPER_SEMICONDUCTOR_ALLOCATION",
        "--max-paper-semiconductor-allocation",
    ),
    (
        "TRADING_APP_INITIAL_PAPER_DEPLOYMENT_ALLOCATION",
        "--initial-paper-deployment-allocation",
    ),
    ("TRADING_APP_PAPER_EPOCH_STARTED_AT", "--paper-epoch-started-at"),
    ("TRADING_APP_DASHBOARD_HOST", "--dashboard-host"),
    ("TRADING_APP_DASHBOARD_PORT", "--dashboard-port"),
    ("TRADING_APP_OPERATOR_DASHBOARD_URL", "--dashboard-redirect-url"),
    ("TRADING_APP_ACTIVE_MODEL_KEY", "--active-model-key"),
    ("TRADING_APP_SHADOW_CHALLENGER_MODEL_KEY", "--shadow-challenger-model-key"),
    ("TRADING_APP_SHADOW_CHALLENGER_MODEL_KEYS", "--shadow-challenger-model-keys"),
    ("TRADING_APP_STRATEGY_SCHEDULE", "--strategy-schedule"),
)


def load_env_file(
    path: Path | str,
    *,
    environ: MutableMapping[str, str] | None = None,
    override: bool = False,
) -> bool:
    """Load simple KEY=VALUE pairs from a local env file."""

    env_path = Path(path)
    if not env_path.exists():
        return False

    target = environ if environ is not None else os.environ
    for line_number, line in enumerate(
        env_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        parsed = _parse_env_line(line, line_number=line_number, path=env_path)
        if parsed is None:
            continue
        key, value = parsed
        if override or key not in target:
            target[key] = value
    return True


def main(argv: Sequence[str] | None = None) -> int:
    """Start the local paper runtime with project-safe dev defaults."""

    parser = argparse.ArgumentParser(
        description="Start the local Alpaca paper runtime with safe defaults.",
        epilog=(
            "All other options are passed through to "
            "trading_app.runtime.run_alpaca_paper."
        ),
    )
    parser.add_argument(
        "--env-file",
        default=_DEFAULT_ENV_FILE,
        help="Local env file to load before startup. Defaults to .env.",
    )
    parser.add_argument(
        "--no-env-file",
        action="store_true",
        help="Do not load a local env file before startup.",
    )
    shortcut_args, runtime_args = parser.parse_known_args(argv)

    if not shortcut_args.no_env_file:
        load_env_file(shortcut_args.env_file)

    resolved_args = _with_env_runtime_defaults(runtime_args, os.environ)
    return run_alpaca_paper_main(_with_dev_flags(resolved_args))


def _with_dev_flags(args: list[str]) -> list[str]:
    resolved = [*args]
    if _MONITOR_ONLY_FLAG not in resolved:
        resolved.append(_MONITOR_ONLY_FLAG)
    if _DASHBOARD_PORT_AUTO_INCREMENT_FLAG not in resolved:
        resolved.append(_DASHBOARD_PORT_AUTO_INCREMENT_FLAG)
    return resolved


def _with_env_runtime_defaults(
    args: list[str],
    environ: MutableMapping[str, str],
) -> list[str]:
    existing_options = {arg.partition("=")[0] for arg in args if arg.startswith("--")}
    resolved = [*args]
    for env_name, option in _ENV_RUNTIME_DEFAULTS:
        value = normalize_alpaca_env_value(environ.get(env_name))
        if value and option not in existing_options:
            resolved.extend([option, value])
    return resolved


def _parse_env_line(
    line: str,
    *,
    line_number: int,
    path: Path,
) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped.removeprefix("export ").lstrip()

    key, separator, value = stripped.partition("=")
    if not separator:
        raise ValueError(f"{path}:{line_number}: expected KEY=VALUE")
    key = key.strip()
    if not _ENV_NAME.fullmatch(key):
        raise ValueError(f"{path}:{line_number}: invalid environment key {key!r}")
    return key, _strip_wrapping_quotes(value.strip())


def _strip_wrapping_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
