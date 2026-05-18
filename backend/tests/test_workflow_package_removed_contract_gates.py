from __future__ import annotations

import base64
import os
import re
import subprocess
from pathlib import Path

from tests.test_workflow_package_manifest_http_node import (
    assert_removed_contract_tokens_absent,
    removed_contract_tokens,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SQL_BASE64_DECODE_RE = re.compile(
    r"decode\('([^']+)'\s*,\s*'base64'\)",
    re.IGNORECASE | re.MULTILINE,
)


def _run_git_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "GIT_MASTER": "1"}
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        check=False,
        cwd=_REPO_ROOT,
        env=env,
        text=True,
    )


def _tracked_sql_paths() -> list[Path]:
    completed = _run_git_command(["ls-files", "--", "*.sql"])
    assert completed.returncode == 0, completed.stderr
    return [_REPO_ROOT / path for path in completed.stdout.splitlines() if path.strip()]


def test_tracked_source_has_no_removed_contract_tokens() -> None:
    for token in removed_contract_tokens():
        completed = _run_git_command(["grep", "-n", token, "--", "."])
        assert completed.returncode == 1, completed.stdout or completed.stderr
        assert completed.stdout == ""


def test_tracked_sql_seed_payloads_decode_without_removed_contract_tokens() -> None:
    decoded_payload_count = 0
    for sql_path in _tracked_sql_paths():
        sql_source = sql_path.read_text(encoding="utf-8")
        for encoded_payload in _SQL_BASE64_DECODE_RE.findall(sql_source):
            decoded_payload = base64.b64decode(encoded_payload, validate=True).decode("utf-8")
            decoded_payload_count += 1
            assert_removed_contract_tokens_absent(
                decoded_payload,
                context=f"decoded SQL payload in {sql_path.relative_to(_REPO_ROOT)}",
            )
    assert decoded_payload_count > 0
