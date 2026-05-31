"""Shared Alpaca credential resolution helpers."""

from __future__ import annotations

import os
from collections.abc import Mapping

ALPACA_API_KEY_ENV = "ALPACA_API_KEY"
ALPACA_SECRET_KEY_ENV = "ALPACA_SECRET_KEY"
ALPACA_LIVE_TRADING_FLAG_ENV = "ALPACA_LIVE_TRADING_ENABLED"
ALPACA_ENDPOINT_ENV_NAMES = (
    "ALPACA_API_BASE_URL",
    "APCA_API_BASE_URL",
    "ALPACA_BASE_URL",
)
_TRUTHY = {"1", "true", "yes", "on"}


def alpaca_credential_present(env: Mapping[str, str], name: str) -> bool:
    """Return true only when the credential exists and is not blank."""

    return bool(normalize_alpaca_env_value(env.get(name)))


def normalize_alpaca_env_value(value: str | None) -> str | None:
    """Normalize shell/env-file values by trimming whitespace and wrapping quotes."""

    if value is None:
        return None
    stripped = value.strip()
    if (
        len(stripped) >= 2
        and stripped[0] == stripped[-1]
        and stripped[0]
        in {
            "'",
            '"',
        }
    ):
        stripped = stripped[1:-1].strip()
    return stripped or None


def resolve_alpaca_credentials(
    *,
    api_key: str | None = None,
    secret_key: str | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[str, str]:
    """Resolve non-blank Alpaca credentials from explicit values or environment."""

    source = env if env is not None else os.environ
    resolved_api_key = normalize_alpaca_env_value(
        api_key if api_key is not None else source.get(ALPACA_API_KEY_ENV)
    )
    resolved_secret_key = normalize_alpaca_env_value(
        secret_key if secret_key is not None else source.get(ALPACA_SECRET_KEY_ENV)
    )
    if not resolved_api_key or not resolved_secret_key:
        raise ValueError("ALPACA_API_KEY and ALPACA_SECRET_KEY are required")
    return resolved_api_key, resolved_secret_key


def alpaca_paper_boundary_violations(
    env: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    """Return environment settings that would violate Alpaca paper-only mode."""

    source = env if env is not None else os.environ
    violations: list[str] = []
    live_flag = (
        normalize_alpaca_env_value(source.get(ALPACA_LIVE_TRADING_FLAG_ENV)) or ""
    ).lower()
    if live_flag in _TRUTHY:
        violations.append(f"{ALPACA_LIVE_TRADING_FLAG_ENV}=true")
    for name in ALPACA_ENDPOINT_ENV_NAMES:
        value = normalize_alpaca_env_value(source.get(name))
        if value and _looks_like_live_alpaca_endpoint(value):
            violations.append(f"{name}=live_endpoint")
    return tuple(violations)


def _looks_like_live_alpaca_endpoint(value: str) -> bool:
    normalized = value.strip().casefold()
    return (
        "api.alpaca.markets" in normalized
        and "paper-api.alpaca.markets" not in normalized
    )
