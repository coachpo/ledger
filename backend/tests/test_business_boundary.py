from __future__ import annotations

from pathlib import Path

import pytest

FORBIDDEN_IDENTIFIER_PARTS = (
    ("Trading", "Agents"),
    ("trading", "agents"),
    ("trading_", "agents"),
    ("trading", " ", "agents"),
)
SCANNED_ROOTS = ("backend/app", "frontend/src")
SCANNED_FILES = ("AGENTS.md", "README.md")
EXCLUDED_PARTS = {
    ".git",
    ".sisyphus",
    "frontend/dist",
    "frontend/node_modules",
    "backend/.venv",
    "__pycache__",
    ".pytest_cache",
    "playwright-report",
    "test-results",
}
FORBIDDEN_IDENTIFIERS = tuple("".join(parts) for parts in FORBIDDEN_IDENTIFIER_PARTS)


def _iter_scanned_files(repo_root: Path) -> list[Path]:
    scanned_files: list[Path] = []
    for root_name in SCANNED_ROOTS:
        root_path = repo_root / root_name
        if root_path.is_dir():
            scanned_files.extend(sorted(path for path in root_path.rglob("*") if path.is_file()))
    for file_name in SCANNED_FILES:
        file_path = repo_root / file_name
        if file_path.is_file():
            scanned_files.append(file_path)
    return [path for path in scanned_files if not _is_excluded(path, repo_root)]


def _is_excluded(path: Path, repo_root: Path) -> bool:
    relative_parts = path.relative_to(repo_root).parts
    relative_path = path.relative_to(repo_root).as_posix()
    return any(
        excluded in relative_parts
        or relative_path.startswith(excluded + "/")
        or relative_path == excluded
        for excluded in EXCLUDED_PARTS
    )


def _find_forbidden_matches(repo_root: Path) -> list[str]:
    matches: list[str] = []
    for path in _iter_scanned_files(repo_root):
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for line_number, line in enumerate(content.splitlines(), start=1):
            for identifier in FORBIDDEN_IDENTIFIERS:
                if identifier in line:
                    matches.append(f"{path.relative_to(repo_root)}:{line_number}: {line.strip()}")
                    break
    return matches


@pytest.mark.parametrize("identifier", FORBIDDEN_IDENTIFIERS)
def test_business_boundary_has_no_forbidden_identifiers(identifier: str) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    matches = [match for match in _find_forbidden_matches(repo_root) if identifier in match]
    assert matches == [], "\n".join(matches)
