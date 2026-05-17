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
MEMORY_ID_OWNER = BACKEND / "app/services/report_backed_memory_store.py"
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


def _python_nodes_with_name_fragment(relative_path: str, fragment: str) -> list[str]:
    source = _read(relative_path)
    module = ast.parse(source, filename=relative_path)
    segments: list[str] = []
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef) and fragment in node.name:
            segment = ast.get_source_segment(source, node)
            if segment is not None:
                segments.append(segment)
    if not segments:
        raise AssertionError(f"Missing functions containing {fragment} in {relative_path}")
    return segments


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
        "backend/app/extensions/signaldeck_finance/runtime_types.py",
        "RuntimeReportMemoryWriteResult",
    )
    _assert_fragments_absent(
        "RuntimeReportMemoryWriteResult",
        result_contract,
        MODEL_VISIBLE_RUNTIME_FORBIDDEN,
    )

    runtime_tests = "\n\n".join(
        _python_nodes_with_name_fragment("backend/tests/test_runtime_tools.py", "reports_write")
    )
    _assert_no_forbidden_lines(
        "reports_write runtime tests",
        runtime_tests,
        MODEL_VISIBLE_RUNTIME_FORBIDDEN,
    )


def test_prompt_context_sources_do_not_render_report_identity() -> None:
    prompt_sources = "\n\n".join(
        [
            _python_node_source(
                "backend/app/services/report_backed_memory_store.py",
                "_prompt_snippet",
            ),
            _python_node_source(
                "backend/app/services/report_backed_memory_store.py",
                "_render_prompt_text",
            ),
            _read("backend/app/services/memory_context_service.py"),
        ]
    )
    _assert_no_forbidden_lines("memory prompt sources", prompt_sources, PROMPT_FORBIDDEN)


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


def test_report_backed_memory_store_owns_mem_id_parsing_and_formatting() -> None:
    production_files = sorted((BACKEND / "app").rglob("*.py"))
    violations: list[str] = []
    for path in production_files:
        if path == MEMORY_ID_OWNER:
            continue
        relative_path = path.relative_to(ROOT)
        source = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(source.splitlines(), start=1):
            if any(pattern.search(line) for pattern in MEMORY_ID_FORBIDDEN_PATTERNS):
                violations.append(f"{relative_path}:{line_number}: {line.strip()}")
    assert not violations, "mem_<report_id> parsing/formatting escaped store: " + repr(violations)
