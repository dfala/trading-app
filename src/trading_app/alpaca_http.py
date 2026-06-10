"""HTTP safeguards for Alpaca SDK clients."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

ALPACA_HTTP_TIMEOUT_ENV = "TRADING_APP_ALPACA_HTTP_TIMEOUT_SECONDS"
DEFAULT_ALPACA_HTTP_TIMEOUT_SECONDS = 10.0


def resolve_alpaca_http_timeout_seconds(
    env: Mapping[str, str] | None = None,
) -> float:
    source = env or os.environ
    raw_value = source.get(ALPACA_HTTP_TIMEOUT_ENV)
    if raw_value is None or not raw_value.strip():
        return DEFAULT_ALPACA_HTTP_TIMEOUT_SECONDS

    try:
        timeout = float(raw_value)
    except ValueError as error:
        raise ValueError(
            f"{ALPACA_HTTP_TIMEOUT_ENV} must be a positive number of seconds"
        ) from error
    if timeout <= 0:
        raise ValueError(
            f"{ALPACA_HTTP_TIMEOUT_ENV} must be a positive number of seconds"
        )
    return timeout


def install_default_alpaca_http_timeout(
    client: Any,
    *,
    timeout_seconds: float | None = None,
) -> None:
    """Add a default requests timeout to Alpaca SDK clients when possible."""

    session = getattr(client, "_session", None)
    request = getattr(session, "request", None)
    if session is None or not callable(request):
        return

    timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else resolve_alpaca_http_timeout_seconds()
    )
    if timeout <= 0:
        raise ValueError("timeout_seconds must be positive")

    original_request = getattr(session, "_trading_app_original_request", None)
    if original_request is None:
        original_request = request
        setattr(session, "_trading_app_original_request", original_request)

    def request_with_default_timeout(*args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("timeout", timeout)
        return original_request(*args, **kwargs)

    setattr(session, "request", request_with_default_timeout)
    setattr(session, "_trading_app_default_timeout_seconds", timeout)
