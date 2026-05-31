"""Generate the local operator dashboard HTML."""

from __future__ import annotations

from pathlib import Path

from trading_app.dashboard import build_demo_dashboard_snapshot, write_dashboard


def main() -> None:
    output_path = Path("dashboard/operator-dashboard.html")
    snapshot = build_demo_dashboard_snapshot()
    written = write_dashboard(snapshot, output_path)
    print(f"Operator dashboard written to {written.resolve()}")


if __name__ == "__main__":
    main()
