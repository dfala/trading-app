"""Runtime artifact secret scanning."""

from __future__ import annotations

import argparse
import os
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path

from trading_app.alpaca_credentials import normalize_alpaca_env_value
from trading_app.runtime.models import (
    RuntimePreflightStatus,
    RuntimeSecretScanFinding,
    RuntimeSecretScanReport,
)
from trading_app.runtime.persistence import RuntimePersistenceStore

_SECRET_ENV_NAMES = ("ALPACA_API_KEY", "ALPACA_SECRET_KEY")
_PLACEHOLDER_VALUES = {
    "",
    "...",
    "replace-with-paper-api-key",
    "replace-with-paper-secret-key",
}
_TEXT_SUFFIXES = {
    "",
    ".csv",
    ".html",
    ".json",
    ".jsonl",
    ".log",
    ".md",
    ".txt",
}


class RuntimeSecretScanner:
    """Scan local runtime artifacts for actual credential values."""

    def __init__(
        self,
        *,
        output_dir: Path | str = "data/runtime",
        env: Mapping[str, str] | None = None,
        persistence_store: RuntimePersistenceStore | None = None,
        min_secret_length: int = 8,
        scan_paths: Iterable[Path | str] = (),
        persist_report: bool = True,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.env = env if env is not None else os.environ
        self.persistence_store = persistence_store or RuntimePersistenceStore(
            self.output_dir
        )
        self.min_secret_length = min_secret_length
        self.scan_paths = tuple(Path(path) for path in scan_paths)
        self.persist_report = persist_report

    def scan(self, *, as_of: datetime | None = None) -> RuntimeSecretScanReport:
        now = as_of or datetime.now(tz=UTC)
        secrets = _secret_values(self.env, min_length=self.min_secret_length)
        findings: list[RuntimeSecretScanFinding] = []
        files_scanned = 0
        files_skipped = 0
        scan_roots = (self.output_dir, *self.scan_paths)
        seen_paths: set[Path] = set()

        for root in scan_roots:
            scanned, skipped, root_findings = _scan_root(
                root=root,
                secrets=secrets,
                seen_paths=seen_paths,
            )
            files_scanned += scanned
            files_skipped += skipped
            findings.extend(root_findings)

        passed = not findings
        report = RuntimeSecretScanReport(
            as_of=now,
            status=(
                RuntimePreflightStatus.PASSED
                if passed
                else RuntimePreflightStatus.FAILED
            ),
            passed=passed,
            output_dir=str(self.output_dir),
            scan_roots=tuple(str(root) for root in scan_roots),
            files_scanned=files_scanned,
            files_skipped=files_skipped,
            secret_names_checked=tuple(secrets),
            findings=tuple(findings),
            summary=_summary(
                passed=passed,
                files_scanned=files_scanned,
                files_skipped=files_skipped,
                findings=len(findings),
                secrets=len(secrets),
            ),
        )
        if self.persist_report:
            self.persistence_store.persist_secret_scan_report(report)
        return report


def render_secret_scan_text(report: RuntimeSecretScanReport) -> str:
    """Render a secret scan report without exposing secret values."""

    lines = [
        f"Secret scan status: {report.status.value}",
        f"Passed: {'yes' if report.passed else 'no'}",
        f"Output dir: {report.output_dir}",
        f"Scan roots: {', '.join(report.scan_roots) or report.output_dir}",
        f"Files scanned: {report.files_scanned}",
        f"Files skipped: {report.files_skipped}",
        f"Secret names checked: {', '.join(report.secret_names_checked) or 'none'}",
        report.summary,
        "",
        "Findings:",
    ]
    if not report.findings:
        lines.append("- None.")
    else:
        for finding in report.findings:
            lines.append(
                f"- {finding.path}:{finding.line_number} "
                f"{finding.secret_name}: {finding.message}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Scan local runtime artifacts for leaked credential values."""

    parser = argparse.ArgumentParser(description="Scan runtime artifacts for secrets.")
    parser.add_argument("--output-dir", default="data/runtime")
    parser.add_argument(
        "--include-path",
        action="append",
        default=[],
        help=(
            "Additional file or directory to scan, such as exported dashboard "
            "HTML or local log folders."
        ),
    )
    parser.add_argument("--no-persist", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = RuntimeSecretScanner(
        output_dir=args.output_dir,
        scan_paths=args.include_path,
        persist_report=not args.no_persist,
    ).scan()
    print(report.model_dump_json() if args.json else render_secret_scan_text(report))
    return 0 if report.passed else 1


def _secret_values(
    env: Mapping[str, str],
    *,
    min_length: int,
) -> dict[str, str]:
    values: dict[str, str] = {}
    for name in _SECRET_ENV_NAMES:
        value = normalize_alpaca_env_value(str(env.get(name, ""))) or ""
        if value in _PLACEHOLDER_VALUES:
            continue
        if len(value) < min_length:
            continue
        values[name] = value
    return values


def _scan_root(
    *,
    root: Path,
    secrets: dict[str, str],
    seen_paths: set[Path],
) -> tuple[int, int, list[RuntimeSecretScanFinding]]:
    if not root.exists():
        return 0, 1, []
    if root.is_file():
        return _scan_file(
            path=root,
            root=root.parent,
            secrets=secrets,
            seen_paths=seen_paths,
        )

    files_scanned = 0
    files_skipped = 0
    findings: list[RuntimeSecretScanFinding] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        scanned, skipped, file_findings = _scan_file(
            path=path,
            root=root,
            secrets=secrets,
            seen_paths=seen_paths,
        )
        files_scanned += scanned
        files_skipped += skipped
        findings.extend(file_findings)
    return files_scanned, files_skipped, findings


def _scan_file(
    *,
    path: Path,
    root: Path,
    secrets: dict[str, str],
    seen_paths: set[Path],
) -> tuple[int, int, list[RuntimeSecretScanFinding]]:
    resolved = path.resolve()
    if resolved in seen_paths:
        return 0, 0, []
    seen_paths.add(resolved)
    if path.suffix.lower() not in _TEXT_SUFFIXES:
        return 0, 1, []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return 0, 1, []
    return (
        1,
        0,
        _scan_text(
            path=path,
            root=root,
            text=text,
            secrets=secrets,
        ),
    )


def _scan_text(
    *,
    path: Path,
    root: Path,
    text: str,
    secrets: dict[str, str],
) -> list[RuntimeSecretScanFinding]:
    findings: list[RuntimeSecretScanFinding] = []
    try:
        relative_path = path.relative_to(root)
    except ValueError:
        relative_path = path
    for line_number, line in enumerate(text.splitlines(), start=1):
        for secret_name, secret_value in secrets.items():
            if secret_value not in line:
                continue
            findings.append(
                RuntimeSecretScanFinding(
                    path=str(relative_path),
                    line_number=line_number,
                    secret_name=secret_name,
                    message="Credential value appeared in a runtime artifact.",
                )
            )
    return findings


def _summary(
    *,
    passed: bool,
    files_scanned: int,
    files_skipped: int,
    findings: int,
    secrets: int,
) -> str:
    if not secrets:
        return (
            "No configured secret values were available to scan for; artifact scan "
            "completed without credential-value matching."
        )
    if passed:
        return (
            f"Scanned {files_scanned} text artifact(s), skipped {files_skipped}, "
            "and found no configured credential values."
        )
    return (
        f"Found {findings} credential leak finding(s) while scanning "
        f"{files_scanned} text artifact(s). Review and remove leaked artifacts."
    )


if __name__ == "__main__":
    raise SystemExit(main())
