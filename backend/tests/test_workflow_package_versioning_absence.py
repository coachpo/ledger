from pathlib import Path

FORBIDDEN_WORKFLOW_PACKAGE_VERSIONING_TOKENS = (
    "workflow_package_versions",
    "latest_version_id",
    "/versions",
    "createVersion",
    "latestVersion",
    "packageVersion",
    "workflow_package_version_id",
    "WorkflowPackageVersion",
    "workflowPackageVersion",
    "targetVersion",
    "missingPackageVersion",
    "changedPackageVersionArtifact",
    "packageVersionAvailable",
)

ROOT = Path(__file__).resolve().parents[2]
SCAN_TARGETS = (
    ROOT / "backend" / "app",
    ROOT / "backend" / "tests",
    ROOT / "frontend" / "src",
    ROOT / "frontend" / "e2e",
    ROOT / "docs",
    ROOT / "README.md",
    ROOT / "backend" / "README.md",
)
INTENTIONAL_NEGATIVE_ASSERTION_FILES = {
    ROOT / "backend" / "tests" / "test_workflow_package_versioning_absence.py",
    ROOT / "backend" / "tests" / "test_workflow_package_api.py",
    ROOT / "backend" / "tests" / "test_workflow_package_openapi.py",
    ROOT / "backend" / "tests" / "test_workflow_package_models.py",
    ROOT / "backend" / "tests" / "test_workflow_package_db_upgrades.py",
    ROOT / "backend" / "tests" / "test_workflow_package_runtime_api.py",
    ROOT / "backend" / "tests" / "test_runtime_models.py",
    ROOT / "backend" / "tests" / "test_runtime_db_upgrades.py",
}
SCAN_SUFFIXES = {".py", ".ts", ".tsx", ".md", ".sql"}


def _iter_scan_files() -> list[Path]:
    files: list[Path] = []
    for target in SCAN_TARGETS:
        if target.is_file():
            files.append(target)
            continue
        files.extend(
            path
            for path in target.rglob("*")
            if path.is_file() and path.suffix in SCAN_SUFFIXES and "retired" not in path.parts
        )
    return files


def test_removed_workflow_package_versioning_tokens_stay_out_of_live_surfaces() -> None:
    hits: dict[str, list[str]] = {}
    for path in _iter_scan_files():
        if path in INTENTIONAL_NEGATIVE_ASSERTION_FILES:
            continue
        text = path.read_text(errors="ignore")
        for token in FORBIDDEN_WORKFLOW_PACKAGE_VERSIONING_TOKENS:
            if token in text:
                hits.setdefault(token, []).append(str(path.relative_to(ROOT)))

    assert hits == {}
