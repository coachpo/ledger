from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

MODEL_VISIBLE_RUNTIME_FORBIDDEN = (
    "reportId",
    "reportSlug",
    "reportName",
    "auditLinks",
    "/reports/",
    "download",
)
PROMPT_FORBIDDEN = (
    "report_id",
    "report_slug",
    "Report ID",
    "/reports/",
    "/api/v1/reports",
    "download",
)
FRONTEND_REMOVED_ARTIFACT_READ_RE = re.compile(r"\bartifact\.(?:reportId|slug|name)\b")
CANONICAL_MEMORY_STORE = "backend/app/services/memory_store.py"
MEMORY_ID_FORBIDDEN_PATTERNS = (
    re.compile(r"\bdef\s+(?:format|parse)_report_backed_memory_id\b"),
    re.compile(r"\bdef\s+report_id_from_memory_id\b"),
    re.compile(r"\bparse_report_backed_memory_id\b"),
    re.compile(r"\bformat_report_backed_memory_id\b"),
    re.compile(r"_MEMORY_ID_RE\b"),
    re.compile(r"re\.compile\(r?[\"']\^mem_"),
    re.compile(r"f[\"']mem_\{"),
    re.compile(r"\.removeprefix\([\"']mem_[\"']\)"),
    re.compile(r"\.split\([\"']mem_[\"']\)"),
)


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _python_node_source(relative_path: str, node_name: str) -> str:
    source = _read(relative_path)
    module = ast.parse(source, filename=relative_path)
    for node in ast.walk(module):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name == node_name:
            segment = ast.get_source_segment(source, node)
            if segment is None:
                raise AssertionError(f"Could not read source for {relative_path}:{node_name}")
            return segment
    raise AssertionError(f"Missing {node_name} in {relative_path}")


def _assert_fragments_absent(label: str, source: str, fragments: tuple[str, ...]) -> None:
    violations = [fragment for fragment in fragments if fragment in source]
    assert not violations, f"{label} leaked forbidden fragments: {violations}"


def _assert_no_forbidden_lines(
    label: str,
    source: str,
    fragments: tuple[str, ...],
) -> None:
    violations: list[str] = []
    for line_number, line in enumerate(source.splitlines(), start=1):
        if not any(fragment in line for fragment in fragments):
            continue
        if "not in" in line or "queryBy" in line or "FORBIDDEN" in line:
            continue
        violations.append(f"{line_number}: {line.strip()}")
    assert not violations, f"{label} has non-allowlisted leak strings: {violations}"


def _interface_body(source: str, name: str) -> str:
    match = re.search(rf"export interface {name}\b", source)
    assert match is not None, f"Missing TypeScript interface {name}"
    start = source.index("{", match.end())
    depth = 0
    for index in range(start, len(source)):
        character = source[index]
        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"Could not find body for TypeScript interface {name}")


def test_model_visible_runtime_write_contracts_do_not_leak_report_identity() -> None:
    result_contract = _python_node_source(
        "backend/app/agents/runtime_tools/memory.py",
        "RuntimeMemoryWriteResult",
    )
    _assert_fragments_absent(
        "RuntimeMemoryWriteResult",
        result_contract,
        MODEL_VISIBLE_RUNTIME_FORBIDDEN,
    )


def test_retired_report_memory_write_runtime_ballast_is_removed() -> None:
    forbidden_fragments = (
        "signaldeck.finance.reports.write",
        "signaldeck_reports_write",
        "report_memory_write_retired",
        "REPORT_MEMORY_WRITE",
        "RuntimeReportMemoryWriteResult",
    )
    production_files = sorted((BACKEND / "app").rglob("*.py"))
    violations: list[str] = []
    for path in production_files:
        relative_path = path.relative_to(ROOT)
        source = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(source.splitlines(), start=1):
            if any(fragment in line for fragment in forbidden_fragments):
                violations.append(f"{relative_path}:{line_number}: {line.strip()}")
    assert not violations, "retired report-memory write runtime ballast remains: " + repr(
        violations
    )


def test_prompt_context_sources_do_not_render_report_identity() -> None:
    prompt_sources = "\n\n".join(
        [
            _python_node_source(CANONICAL_MEMORY_STORE, "_render_prompt_text"),
            _read("backend/app/services/memory_context_service.py"),
        ]
    )
    _assert_no_forbidden_lines("memory prompt sources", prompt_sources, PROMPT_FORBIDDEN)


def test_postgres_memory_store_does_not_use_reports_as_substrate() -> None:
    store_source = _python_node_source(CANONICAL_MEMORY_STORE, "PostgresMemoryStore")
    _assert_fragments_absent(
        "PostgresMemoryStore",
        store_source,
        (
            "ReportBackedMemoryStore",
            "ReportRepository",
            "app.models.report",
            "report_id",
            "report_slug",
            "/reports/",
            "download",
        ),
    )


def test_core_memory_contracts_do_not_define_finance_shaped_fields() -> None:
    core_memory_source = _read("backend/app/schemas/memory.py")
    for node_name in ("MemoryEntryRead", "MemoryWriteRequest", "MemoryQuery"):
        node_source = _python_node_source("backend/app/schemas/memory.py", node_name)
        _assert_fragments_absent(
            node_name,
            node_source,
            (
                "ticker",
                "portfolio_slug",
                "portfolioSlug",
                "decision_summary",
                "decisionSummary",
                "benchmark_symbol",
                "benchmarkSymbol",
                "raw_return",
                "rawReturn",
                "alpha",
                "attributes",
                "tags",
                "audit_links",
                "auditLinks",
            ),
        )
    _assert_fragments_absent("core memory schema", core_memory_source, ("MemoryDecision",))


def test_admin_memory_dto_contracts_do_not_define_report_history_fields() -> None:
    for node_name in ("MemoryAdminListItemRead", "MemoryAdminEntryRead"):
        node_source = _python_node_source("backend/app/schemas/memory.py", node_name)
        _assert_fragments_absent(
            node_name,
            node_source,
            (
                "report_id",
                "reportId",
                "report_slug",
                "reportSlug",
                "report_name",
                "reportName",
                "raw_markdown",
                "rawMarkdown",
                "download_url",
                "downloadUrl",
                "report_history",
                "reportHistory",
            ),
        )


def test_frontend_run_memory_artifacts_do_not_read_removed_report_fields() -> None:
    run_types = _read("frontend/src/lib/types/run.ts")
    artifact_body = _interface_body(run_types, "RunMemoryArtifactRead")
    for field_name in ("reportId", "slug", "name"):
        assert field_name not in artifact_body

    for relative_path in (
        "frontend/src/pages/runs/detail.tsx",
        "frontend/src/pages/runs/detail.test.tsx",
    ):
        source = _read(relative_path)
        matches = FRONTEND_REMOVED_ARTIFACT_READ_RE.findall(source)
        assert not matches, f"{relative_path} reads removed artifact fields: {matches}"


def test_report_backed_memory_id_parsing_is_not_reintroduced() -> None:
    production_files = sorted((BACKEND / "app").rglob("*.py"))
    violations: list[str] = []
    for path in production_files:
        relative_path = path.relative_to(ROOT)
        source = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(source.splitlines(), start=1):
            if any(pattern.search(line) for pattern in MEMORY_ID_FORBIDDEN_PATTERNS):
                violations.append(f"{relative_path}:{line_number}: {line.strip()}")
    assert not violations, "mem_<report_id> parsing/formatting was reintroduced: " + repr(
        violations
    )
