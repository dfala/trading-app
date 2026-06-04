"""Local dashboard API and Next.js redirect server."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from trading_app.dashboard.model_performance import build_model_performance_payload
from trading_app.dashboard.snapshot import build_demo_dashboard_snapshot
from trading_app.runtime.models import OperatorControlRequest

DashboardSnapshotProvider = Callable[[], Any]
DashboardControlHandler = Callable[[OperatorControlRequest], Any]
DashboardHealthProvider = Callable[[], Any]
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
_REDIRECT_STATUSES = frozenset(
    {
        HTTPStatus.MOVED_PERMANENTLY,
        HTTPStatus.FOUND,
        HTTPStatus.SEE_OTHER,
        HTTPStatus.TEMPORARY_REDIRECT,
        HTTPStatus.PERMANENT_REDIRECT,
    }
)


def dashboard_response(
    path: str,
    *,
    method: str = "GET",
    body: str = "",
    snapshot_provider: DashboardSnapshotProvider | None = None,
    control_handler: DashboardControlHandler | None = None,
    health_provider: DashboardHealthProvider | None = None,
    dashboard_redirect_url: str | None = None,
) -> tuple[HTTPStatus, str, str]:
    """Return the body for a local dashboard route without binding a socket."""

    if dashboard_redirect_url and not is_local_dashboard_url(dashboard_redirect_url):
        raise ValueError("dashboard redirect URL must be local-only")

    provider = snapshot_provider or build_demo_dashboard_snapshot
    parsed_url = urlsplit(path)
    route_path = parsed_url.path
    if method == "POST":
        return control_response(
            route_path,
            body=body,
            control_handler=control_handler,
        )
    if method != "GET":
        return (
            HTTPStatus.METHOD_NOT_ALLOWED,
            "text/plain; charset=utf-8",
            "Method not allowed",
        )
    if route_path in {"/", "/dashboard"}:
        if dashboard_redirect_url:
            return (
                HTTPStatus.FOUND,
                "text/plain; charset=utf-8",
                dashboard_redirect_url,
            )
        return (
            HTTPStatus.GONE,
            "text/plain; charset=utf-8",
            "The Python-generated dashboard has moved to the Next.js operator "
            "dashboard. Start the Next app and configure a local dashboard "
            "redirect URL.",
        )
    if route_path == "/api/snapshot":
        try:
            body = snapshot_json(provider())
        except Exception as error:
            return _provider_error_response(
                "dashboard snapshot unavailable",
                error,
            )
        return (
            HTTPStatus.OK,
            "application/json; charset=utf-8",
            body,
        )
    if route_path == "/api/health":
        try:
            body = snapshot_json(_health_payload(provider, health_provider))
        except Exception as error:
            return _provider_error_response(
                "dashboard health unavailable",
                error,
            )
        return (
            HTTPStatus.OK,
            "application/json; charset=utf-8",
            body,
        )
    if route_path == "/api/model-performance":
        params = parse_qs(parsed_url.query)
        model_key = params.get("model_key", [""])[0]
        universe_id = params.get("universe_id", [None])[0]
        if not model_key:
            return (
                HTTPStatus.BAD_REQUEST,
                "application/json; charset=utf-8",
                json.dumps({"error": "model_key is required"}),
            )
        try:
            payload = build_model_performance_payload(
                model_key,
                universe_id=universe_id,
            )
        except ValueError as error:
            return (
                HTTPStatus.NOT_FOUND,
                "application/json; charset=utf-8",
                json.dumps({"error": str(error)}),
            )
        except Exception as error:
            return (
                HTTPStatus.INTERNAL_SERVER_ERROR,
                "application/json; charset=utf-8",
                json.dumps({"error": str(error)}),
            )
        return (
            HTTPStatus.OK,
            "application/json; charset=utf-8",
            snapshot_json(payload),
        )
    return HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", "Not found"


def control_response(
    path: str,
    *,
    body: str,
    control_handler: DashboardControlHandler | None = None,
) -> tuple[HTTPStatus, str, str]:
    """Handle a local dashboard control action without binding a socket."""

    if path != "/api/control":
        return HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8", "Not found"
    if control_handler is None:
        return (
            HTTPStatus.SERVICE_UNAVAILABLE,
            "application/json; charset=utf-8",
            '{"error":"control handler unavailable"}',
        )
    try:
        payload = json.loads(body or "{}")
        if not isinstance(payload, dict):
            raise ValueError("control payload must be an object")
        payload.setdefault("requested_at", datetime.now(tz=UTC).isoformat())
        payload.setdefault("requested_by", "local-dashboard")
        payload.setdefault("reason", "dashboard control")
        request = OperatorControlRequest.model_validate_json(json.dumps(payload))
        result = control_handler(request)
    except Exception as error:
        return (
            HTTPStatus.BAD_REQUEST,
            "application/json; charset=utf-8",
            json.dumps({"error": str(error)}),
        )
    return (
        HTTPStatus.OK,
        "application/json; charset=utf-8",
        snapshot_json(result),
    )


def snapshot_json(snapshot: Any) -> str:
    """Serialize a dashboard snapshot into JSON suitable for the browser."""

    if hasattr(snapshot, "model_dump"):
        return snapshot.model_dump_json()
    return json.dumps(snapshot)


def _provider_error_response(
    message: str,
    error: Exception,
) -> tuple[HTTPStatus, str, str]:
    return (
        HTTPStatus.SERVICE_UNAVAILABLE,
        "application/json; charset=utf-8",
        json.dumps(
            {
                "error": message,
                "detail": str(error),
            }
        ),
    )


def create_dashboard_server(
    host: str,
    port: int,
    *,
    snapshot_provider: DashboardSnapshotProvider | None = None,
    control_handler: DashboardControlHandler | None = None,
    health_provider: DashboardHealthProvider | None = None,
    dashboard_redirect_url: str | None = None,
    allow_public: bool = False,
) -> ThreadingHTTPServer:
    """Create a local-only dashboard server."""

    if not allow_public and not is_local_dashboard_host(host):
        raise ValueError("dashboard server must bind to a local-only host")
    if dashboard_redirect_url and not is_local_dashboard_url(dashboard_redirect_url):
        raise ValueError("dashboard redirect URL must be local-only")

    provider = snapshot_provider or build_demo_dashboard_snapshot

    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "TradingDashboard/0.1"

        def do_GET(self) -> None:  # noqa: N802
            status, content_type, body = dashboard_response(
                self.path,
                snapshot_provider=provider,
                health_provider=health_provider,
                dashboard_redirect_url=dashboard_redirect_url,
            )
            if status in _REDIRECT_STATUSES:
                self._write_redirect(status, body)
                return
            self._write_payload(status, content_type, body, no_store=True)

        def do_HEAD(self) -> None:  # noqa: N802
            status, content_type, body = dashboard_response(
                self.path,
                snapshot_provider=provider,
                health_provider=health_provider,
                dashboard_redirect_url=dashboard_redirect_url,
            )
            if status in _REDIRECT_STATUSES:
                self._write_redirect(status, body, include_body=False)
                return
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length else ""
            status, content_type, response_body = dashboard_response(
                self.path,
                method="POST",
                body=body,
                snapshot_provider=provider,
                control_handler=control_handler,
                health_provider=health_provider,
            )
            self._write_payload(status, content_type, response_body, no_store=True)

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

        def _write_payload(
            self,
            status: HTTPStatus,
            content_type: str,
            body: str,
            *,
            no_store: bool = False,
        ) -> None:
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            if no_store:
                self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _write_redirect(
            self,
            status: HTTPStatus,
            location: str,
            *,
            include_body: bool = True,
        ) -> None:
            body = f"Redirecting to {location}\n"
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Location", location)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            content_length = len(payload) if include_body else 0
            self.send_header("Content-Length", str(content_length))
            self.end_headers()
            if include_body:
                self.wfile.write(payload)

    return ThreadingHTTPServer((host, port), DashboardHandler)


def is_local_dashboard_host(host: str) -> bool:
    """Return whether a dashboard host keeps controls on the local machine."""

    return host in _LOCAL_HOSTS


def is_local_dashboard_url(url: str) -> bool:
    """Return whether a dashboard URL points only at the local machine."""

    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    return parsed.scheme == "http" and parsed.hostname in _LOCAL_HOSTS


def _health_payload(
    snapshot_provider: DashboardSnapshotProvider,
    health_provider: DashboardHealthProvider | None,
) -> Any:
    if health_provider is not None:
        return health_provider()
    snapshot = snapshot_provider()
    health = getattr(snapshot, "health_report", None)
    if health is not None:
        return health
    if isinstance(snapshot, dict) and snapshot.get("health_report") is not None:
        return snapshot["health_report"]
    return {"status": "ok"}


def main(argv: list[str] | None = None) -> int:
    """Run the local dashboard API and redirect server."""

    parser = argparse.ArgumentParser(
        description="Run the local dashboard API and Next.js redirect server."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--dashboard-redirect-url", default="http://127.0.0.1:3003/")
    parser.add_argument("--allow-public", action="store_true")
    args = parser.parse_args(argv)

    server = create_dashboard_server(
        args.host,
        args.port,
        dashboard_redirect_url=args.dashboard_redirect_url or None,
        allow_public=args.allow_public,
    )
    print(f"Dashboard running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
