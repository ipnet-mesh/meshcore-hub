#!/usr/bin/env python3
"""Render a consolidated CI summary into $GITHUB_STEP_SUMMARY.

Reads the JUnit XML files uploaded by the lint/frontend/test/e2e/build jobs
(downloaded with actions/download-artifact into per-artifact directories) plus
the workflow's ``needs`` context, and writes a Markdown summary covering job
results, test counts, backend coverage, failure details, and artifacts.

Usage: ci_summary.py [results_dir]   (default: results)

Environment:
  NEEDS_JSON           toJson(needs) from the workflow: {"<job>": {"result": ...}}
  GITHUB_STEP_SUMMARY  written when set, otherwise printed to stdout
"""

from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

RESULTS_DIR_DEFAULT = "results"
MAX_FAILURES_SHOWN = 10
MESSAGE_MAX_CHARS = 140

JOBS: list[dict[str, Optional[str]]] = [
    {"id": "lint", "label": "Lint", "junit": None},
    {
        "id": "frontend",
        "label": "Frontend (vitest)",
        "junit": "vitest-results/vitest-junit.xml",
    },
    {"id": "test", "label": "Backend (pytest)", "junit": "pytest-results/junit.xml"},
    {"id": "e2e", "label": "E2E (Playwright)", "junit": "playwright-report/junit.xml"},
    {"id": "build", "label": "Build", "junit": None},
]

COVERAGE_PATH = "pytest-results/coverage.xml"

RESULT_BADGES = {
    "success": "✅ pass",
    "failure": "❌ fail",
    "cancelled": "🚫 cancelled",
    "skipped": "⏭️ skipped",
}

ARTIFACTS = [
    ("pytest-results", "Backend: junit.xml, coverage.xml", "14 days"),
    ("vitest-results", "Frontend: vitest-junit.xml", "14 days"),
    ("playwright-report", "E2E: HTML report, traces, junit.xml", "14 days"),
    ("dist", "Python package (sdist + wheel)", "default"),
]


@dataclass
class TestResults:
    total: int = 0
    failed: int = 0
    skipped: int = 0
    duration_s: float = 0.0
    failures: list[tuple[str, str]] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return self.total - self.failed - self.skipped


def _duration_s(testcase: ET.Element) -> float:
    for attr, scale in (("time", 1.0), ("duration", 0.001)):
        raw = testcase.get(attr)
        if raw is None:
            continue
        try:
            return float(raw) * scale
        except ValueError:
            continue
    return 0.0


def _failure(testcase: ET.Element, node: ET.Element) -> tuple[str, str]:
    parts = [p for p in (testcase.get("classname"), testcase.get("name")) if p]
    name = " > ".join(parts)
    message = node.get("message") or node.text or ""
    message = " ".join(message.split())[:MESSAGE_MAX_CHARS].replace("|", "\\|")
    return name, message


def parse_junit(path: str) -> Optional[TestResults]:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None
    results = TestResults()
    for testcase in root.iter("testcase"):
        results.total += 1
        results.duration_s += _duration_s(testcase)
        failure = testcase.find("failure")
        if failure is None:
            failure = testcase.find("error")
        if failure is not None:
            results.failed += 1
            results.failures.append(_failure(testcase, failure))
        elif testcase.find("skipped") is not None:
            results.skipped += 1
    return results


def parse_coverage(path: str) -> Optional[float]:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return None
    raw = root.get("line-rate")
    if raw is None:
        return None
    try:
        return float(raw) * 100.0
    except ValueError:
        return None


def load_needs(raw: Optional[str]) -> dict[str, str]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    needs: dict[str, str] = {}
    for job_id, info in data.items():
        if isinstance(job_id, str) and isinstance(info, dict):
            result = info.get("result", "unknown")
            needs[job_id] = result if isinstance(result, str) else "unknown"
    return needs


def fmt_duration(seconds: float) -> str:
    if seconds <= 0:
        return "—"
    if seconds < 60:
        return f"{seconds:.1f}s"
    return f"{int(seconds // 60)}m {seconds % 60:.0f}s"


def render(results_dir: str, needs: dict[str, str]) -> str:
    suites: dict[str, Optional[TestResults]] = {}
    for job in JOBS:
        junit = job["junit"]
        suites[str(job["id"])] = (
            parse_junit(os.path.join(results_dir, str(junit))) if junit else None
        )

    lines: list[str] = ["## CI Summary", ""]

    not_ok = [
        str(job["label"])
        for job in JOBS
        if needs.get(str(job["id"]), "unknown") != "success"
    ]
    if not_ok:
        lines.append(
            f"**{len(not_ok)} of {len(JOBS)} jobs not passing:** {', '.join(not_ok)}"
        )
        lines.append("")

    lines.append("| Job | Result | Tests | Pass | Fail | Skip | Duration |")
    lines.append("|---|---|---:|---:|---:|---:|---:|")
    for job in JOBS:
        job_id = str(job["id"])
        result = RESULT_BADGES.get(needs.get(job_id, "unknown"), "❓ unknown")
        cells = [str(job["label"]), result]
        results = suites.get(job_id)
        if job["junit"] and results is None:
            cells.append("*no results*")
            cells.extend(["—"] * 4)
        elif results is None:
            cells.extend(["—"] * 5)
        else:
            cells.append(str(results.total))
            cells.append(str(results.passed))
            cells.append(str(results.failed))
            cells.append(str(results.skipped))
            cells.append(fmt_duration(results.duration_s))
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    coverage = parse_coverage(os.path.join(results_dir, COVERAGE_PATH))
    if coverage is not None:
        lines.append(f"**Backend coverage: {coverage:.1f}%**")
        lines.append("")

    all_failures: list[tuple[str, str, str]] = []
    for job in JOBS:
        job_id = str(job["id"])
        results = suites.get(job_id)
        if results is not None:
            all_failures.extend(
                (str(job["label"]), name, message) for name, message in results.failures
            )

    if all_failures:
        shown = all_failures[:MAX_FAILURES_SHOWN]
        lines.append(f"### ❌ Failures ({len(all_failures)})")
        lines.append("")
        for suite, name, message in shown:
            line = f"- **{suite}** `{name}`"
            if message:
                line += f" — {message}"
            lines.append(line)
        hidden = len(all_failures) - len(shown)
        if hidden > 0:
            lines.append(f"- … and {hidden} more")
        lines.append("")

    lines.append("### 📦 Artifacts")
    lines.append("")
    lines.append("| Artifact | Contents | Retention |")
    lines.append("|---|---|---|")
    for name, contents, retention in ARTIFACTS:
        lines.append(f"| `{name}` | {contents} | {retention} |")

    return "\n".join(lines) + "\n"


def main() -> int:
    results_dir = sys.argv[1] if len(sys.argv) > 1 else RESULTS_DIR_DEFAULT
    needs = load_needs(os.environ.get("NEEDS_JSON"))
    text = render(results_dir, needs)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
