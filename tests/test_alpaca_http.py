from __future__ import annotations

import pytest

from trading_app.alpaca_http import (
    ALPACA_HTTP_TIMEOUT_ENV,
    DEFAULT_ALPACA_HTTP_TIMEOUT_SECONDS,
    install_default_alpaca_http_timeout,
    resolve_alpaca_http_timeout_seconds,
)


def test_resolve_alpaca_http_timeout_defaults_when_unset() -> None:
    assert resolve_alpaca_http_timeout_seconds({}) == (
        DEFAULT_ALPACA_HTTP_TIMEOUT_SECONDS
    )


def test_resolve_alpaca_http_timeout_accepts_positive_env_value() -> None:
    assert resolve_alpaca_http_timeout_seconds({ALPACA_HTTP_TIMEOUT_ENV: "2.5"}) == 2.5


@pytest.mark.parametrize("value", ["0", "-1", "not-a-number"])
def test_resolve_alpaca_http_timeout_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError, match=ALPACA_HTTP_TIMEOUT_ENV):
        resolve_alpaca_http_timeout_seconds({ALPACA_HTTP_TIMEOUT_ENV: value})


def test_install_default_alpaca_http_timeout_adds_missing_timeout() -> None:
    client = FakeAlpacaClient()

    install_default_alpaca_http_timeout(client, timeout_seconds=3.0)
    response = client._session.request("GET", "https://example.test/v2/account")

    assert response == "ok"
    assert client._session.calls == [
        (
            ("GET", "https://example.test/v2/account"),
            {"timeout": 3.0},
        )
    ]
    assert client._session._trading_app_default_timeout_seconds == 3.0


def test_install_default_alpaca_http_timeout_preserves_explicit_timeout() -> None:
    client = FakeAlpacaClient()

    install_default_alpaca_http_timeout(client, timeout_seconds=3.0)
    client._session.request("GET", "https://example.test/v2/account", timeout=7.0)

    assert client._session.calls == [
        (
            ("GET", "https://example.test/v2/account"),
            {"timeout": 7.0},
        )
    ]


def test_install_default_alpaca_http_timeout_noops_without_sdk_session() -> None:
    install_default_alpaca_http_timeout(object(), timeout_seconds=3.0)


class FakeAlpacaClient:
    def __init__(self) -> None:
        self._session = FakeSession()


class FakeSession:
    def __init__(self) -> None:
        self.calls = []

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return "ok"
