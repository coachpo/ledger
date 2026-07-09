from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy import text as sql_text
from sqlalchemy.engine.default import DefaultDialect
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.db.session import init_db, validate_supported_database_engine
from app.extensions.signaldeck_finance.services.report_service import ReportService
from app.models.model_connection import ModelConnection
from app.models.report import Report
from app.schemas.model_connection import (
    ModelConnectionCapabilities,
    ModelConnectionCapabilityStatus,
    ModelConnectionCreate,
    ModelConnectionUpdate,
    default_model_connection_capabilities,
    dump_model_connection_capabilities,
)
from app.schemas.report import ReportRead
from tests.fake_openai_provider import run_fake_openai_provider

UTC_TZ = timezone.utc  # noqa: UP017
_TRACE_ID_PATTERN = re.compile(r"[0-9a-f]{32}")
_EXPECTED_MODEL_CONNECTION_CAPABILITY_KEYS = {
    "chatCompletions",
    "jsonObjectOutput",
    "nativeToolCalls",
    "parallelToolCalls",
    "reasoningHints",
    "responsesApi",
    "streaming",
    "strictJsonSchemaOutput",
    "systemMessages",
    "textGeneration",
    "usageReporting",
}


def _assert_logfire_trace_id(value: object) -> None:
    assert isinstance(value, str)
    assert _TRACE_ID_PATTERN.fullmatch(value) is not None


def test_browser_safe_error_details_preserve_public_scalars_and_drop_unsafe_values() -> None:
    long_issue = "x" * 520

    error = ApiError(
        status_code=400,
        code="contract_probe",
        message="Contract probe failed",
        details=cast(
            Sequence[Mapping[str, object]],
            cast(
                object,
                [
                    {
                        "field": "workflowKey",
                        "issue": long_issue,
                        "extensionKey": "signaldeck.finance",
                        "surface": "tool.marketQuote",
                        "retryAfterSeconds": 30,
                        "enabled": False,
                        "ratio": 0.5,
                        "optional": None,
                        "apiKey": "sk-secret",
                        "authorizationHeader": "Bearer token",
                        "exceptionType": "RuntimeError",
                        "debugPayload": {"path": "/home/qing/private.py"},
                        "rawList": ["internal"],
                        "bad-key": "not exposed",
                        1: "not exposed",
                    },
                    "not an object",
                    {"apiKey": "sk-secret"},
                ],
            ),
        ),
    )

    assert error.details == [
        {
            "field": "workflowKey",
            "issue": f"{'x' * 497}...",
            "extensionKey": "signaldeck.finance",
            "surface": "tool.marketQuote",
            "retryAfterSeconds": 30,
            "enabled": False,
            "ratio": 0.5,
            "optional": None,
        }
    ]

    dict_detail_error = ApiError(
        status_code=400,
        code="contract_probe",
        message="Contract probe failed",
        details=cast(
            Sequence[Mapping[str, object]],
            cast(object, {"field": "name", "issue": "invalid"}),
        ),
    )
    text_detail_error = ApiError(
        status_code=400,
        code="contract_probe",
        message="Contract probe failed",
        details=cast(Sequence[Mapping[str, object]], cast(object, "not an array")),
    )

    assert dict_detail_error.details == []
    assert text_detail_error.details == []


def test_removed_workflow_memory_api_is_not_registered(client: TestClient) -> None:
    response = client.get("/api/memory/proposals")

    assert response.status_code == 404


def test_api_error_envelope_details_are_browser_safe(app: FastAPI) -> None:
    def api_error_details_probe() -> None:
        raise ApiError(
            status_code=400,
            code="contract_probe",
            message="Contract probe failed",
            details=[
                {
                    "field": "workflowKey",
                    "issue": "Unknown workflow",
                    "extensionKey": "signaldeck.digital_oracle",
                    "surface": "tool.predictionMarkets",
                    "retryAfterSeconds": 15,
                    "apiKey": "sk-secret",
                    "exceptionType": "RuntimeError",
                    "debugPayload": {"path": "/home/qing/private.py"},
                }
            ],
        )

    app.add_api_route("/__test/api-error-details", api_error_details_probe, methods=["GET"])

    with TestClient(app) as test_client:
        response = test_client.get("/__test/api-error-details")

    assert response.status_code == 400
    assert response.json() == {
        "code": "contract_probe",
        "message": "Contract probe failed",
        "details": [
            {
                "field": "workflowKey",
                "issue": "Unknown workflow",
                "extensionKey": "signaldeck.digital_oracle",
                "surface": "tool.predictionMarkets",
                "retryAfterSeconds": 15,
            }
        ],
    }


class UnsupportedEngine:
    def __init__(self, dialect_name: str) -> None:
        self.dialect = DefaultDialect()
        self.dialect.name = dialect_name


class _LiteralBaseUrlOpenAIResponse:
    _request_id = "req-literal-base-url"
    usage = {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}
    output_text = '{"summary": "literal base url output"}'
    output = [{"type": "message", "content": [{"type": "output_text", "text": "OK"}]}]
    choices = [{"message": {"content": "OK"}}]


class _LiteralBaseUrlRecordingOpenAIClient:
    init_calls: list[dict[str, object]] = []

    class _Responses:
        @staticmethod
        def create(**kwargs: object) -> _LiteralBaseUrlOpenAIResponse:
            del kwargs
            return _LiteralBaseUrlOpenAIResponse()

    def __init__(self, **kwargs: object) -> None:
        type(self).init_calls.append(dict(kwargs))
        self.responses = self._Responses()

    def __enter__(self) -> _LiteralBaseUrlRecordingOpenAIClient:
        return self

    def __exit__(self, exc_type: object, exc_value: object, exc_traceback: object) -> bool:
        return False

    @classmethod
    def reset(cls) -> None:
        cls.init_calls = []


def create_template(
    client: TestClient,
    *,
    name: str = "Daily Summary",
    content: str = "# Summary\n\n{{reports}}",
) -> dict[str, object]:
    response = client.post(
        "/api/v1/templates",
        json={"name": name, "content": content},
    )
    assert response.status_code == 201, response.json()
    return response.json()


def insert_report_row(
    session_factory: sessionmaker[Session],
    *,
    name: str,
    slug: str,
    source: str,
    content: str = "# Report",
    metadata: dict[str, object] | None = None,
) -> int:
    with session_factory() as session:
        report = Report(
            name=name,
            slug=slug,
            source=source,
            content=content,
            metadata_=metadata or {},
        )
        session.add(report)
        session.flush()
        report_id = report.id
        session.commit()
        return report_id


def _seed_model_connection_record(
    session_factory: sessionmaker[Session],
    *,
    connection_id: int,
    key: str,
    name: str,
    description: str,
    base_url: str,
    model_id: str,
    protocol_profile: str = "openai_responses",
    api_key: str | None = "test-api-key",
    probe_cache_ttl_seconds: int = 900,
    last_probed_at: datetime | None = None,
    last_tested_at: datetime | None = None,
    last_test_ok: bool | None = None,
    last_test_message: str | None = None,
    capabilities: ModelConnectionCapabilities | None = None,
) -> None:
    seeded_capabilities = capabilities or default_model_connection_capabilities(protocol_profile)
    with session_factory() as session:
        session.add(
            ModelConnection(
                id=connection_id,
                key=key,
                name=name,
                description=description,
                base_url=base_url,
                model_id=model_id,
                reasoning_effort="medium",
                protocol_profile=protocol_profile,
                capabilities=dump_model_connection_capabilities(seeded_capabilities),
                output_strategy_policy="prefer_strict_schema",
                parallel_tool_calls_policy="serialize",
                reasoning_policy="allow",
                streaming_policy="allow",
                probe_cache_ttl_seconds=probe_cache_ttl_seconds,
                timeout_seconds=60,
                secret_payload={} if api_key is None else {"apiKey": api_key},
                last_probed_at=last_probed_at,
                last_tested_at=last_tested_at,
                last_test_ok=last_test_ok,
                last_test_message=last_test_message,
            )
        )
        session.commit()


def _set_model_connection_probe_cache(
    session_factory: sessionmaker[Session],
    *,
    connection_id: int,
    probed_at: datetime,
) -> None:
    with session_factory() as session:
        connection = session.get(ModelConnection, connection_id)
        assert connection is not None
        capabilities = ModelConnectionCapabilities.model_validate(connection.capabilities)
        connection.last_probed_at = probed_at
        for field_name in type(capabilities).model_fields:
            getattr(capabilities, field_name).last_probed_at = probed_at
        connection.capabilities = dump_model_connection_capabilities(capabilities)
        session.commit()


def test_agent_platform_routes_mount_package_first_api(
    app: FastAPI,
) -> None:
    route_paths = set(app.openapi()["paths"])

    assert {
        "/api/workflow-packages",
        "/api/workflow-packages/{package_id}",
        "/api/workflow-packages/{package_id}/launch",
        "/api/workflow-packages/{package_id}/launches",
        "/api/model-connections",
        "/api/tools",
        "/api/runs",
        "/api/runs/{run_id}",
    } <= route_paths


def test_finance_workspace_product_routes_remain_mounted_for_templates_and_reports(
    app: FastAPI,
) -> None:
    route_paths = set(app.openapi()["paths"])

    assert {
        "/api/v1/templates",
        "/api/v1/reports",
    } <= route_paths


def _model_connection_create_payload(
    base_url: str = "https://provider.example.test",
) -> dict[str, object]:
    return {
        "key": "supported_fields_model",
        "name": "Supported Fields Model",
        "description": "Model connection with supported fields.",
        "baseUrl": base_url,
        "modelId": "gpt-5.5-mini",
        "reasoningEffort": "medium",
        "protocolProfile": "openai_responses",
        "timeoutSeconds": 60,
        "apiKey": "test-api-key",
    }


def _assert_unsupported_model_connection_fields_rejected(
    response: Response,
    field_names: set[str],
) -> None:
    assert response.status_code == 422, response.json()
    body = cast(dict[str, object], response.json())
    assert body["code"] == "validation_error"
    assert body["message"] == "Request validation failed"
    detail_items = cast(list[dict[str, str]], body["details"])
    details = {detail["field"]: detail["issue"] for detail in detail_items}
    assert field_names <= details.keys()
    for field_name in field_names:
        assert details[field_name] == "Extra inputs are not permitted"


def test_template_crud_and_compile_flow(client: TestClient) -> None:
    template = create_template(
        client,
        name="Input Summary",
        content=("# Summary\n\n" "Ticker: {{inputs.ticker}}\n" "All inputs:\n{{inputs}}"),
    )

    list_response = client.get("/api/v1/templates")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [template["id"]]

    get_response = client.get(f"/api/v1/templates/{template['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Input Summary"

    compile_response = client.post(
        f"/api/v1/templates/{template['id']}/compile",
        json={"inputs": {"ticker": "AAPL"}},
    )
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]
    assert "Ticker: AAPL" in compiled
    assert "- ticker: AAPL" in compiled

    update_response = client.patch(
        f"/api/v1/templates/{template['id']}",
        json={"name": "Weekly Summary", "content": "# Updated"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Weekly Summary"
    assert update_response.json()["content"] == "# Updated"

    delete_response = client.delete(f"/api/v1/templates/{template['id']}")
    assert delete_response.status_code == 204

    missing_response = client.get(f"/api/v1/templates/{template['id']}")
    assert missing_response.status_code == 404
    assert missing_response.json()["code"] == "not_found"


def test_template_compile_accepts_runtime_inputs(client: TestClient) -> None:
    aapl_report = client.post(
        "/api/v1/reports",
        json={
            "name": "AAPL Saved Analysis",
            "content": "AAPL prior view",
            "metadata": {
                "tags": ["aapl_loop"],
                "analysis": {"ticker": "AAPL"},
            },
        },
    )
    assert aapl_report.status_code == 201

    tsla_report = client.post(
        "/api/v1/reports",
        json={
            "name": "TSLA Saved Analysis",
            "content": "TSLA prior view",
            "metadata": {
                "tags": ["tsla_loop"],
                "analysis": {"ticker": "TSLA"},
            },
        },
    )
    assert tsla_report.status_code == 201

    template = create_template(
        client,
        name="Reusable Loop Template",
        content=(
            "Ticker: {{inputs.ticker}}\n"
            "Tagged prior: {{reports.by_tag(inputs.analysis_tag).latest.name}}\n"
            "Latest ticker analysis: {{reports.latest(inputs.ticker).content}}"
        ),
    )

    inline_aapl = client.post(
        "/api/v1/templates/compile",
        json={
            "content": template["content"],
            "inputs": {
                "ticker": "AAPL",
                "analysis_tag": "aapl_loop",
            },
        },
    )
    assert inline_aapl.status_code == 200
    assert inline_aapl.json()["compiled"] == (
        "Ticker: AAPL\n"
        "Tagged prior: AAPL Saved Analysis\n"
        "Latest ticker analysis: AAPL prior view"
    )

    stored_tsla = client.post(
        f"/api/v1/templates/{template['id']}/compile",
        json={
            "inputs": {
                "ticker": "TSLA",
                "analysis_tag": "tsla_loop",
            }
        },
    )
    assert stored_tsla.status_code == 200
    assert stored_tsla.json()["compiled"] == (
        "Ticker: TSLA\n"
        "Tagged prior: TSLA Saved Analysis\n"
        "Latest ticker analysis: TSLA prior view"
    )


def test_template_compile_surfaces_missing_runtime_inputs(client: TestClient) -> None:
    response = client.post(
        "/api/v1/templates/compile",
        json={
            "content": (
                "Ticker: {{inputs.ticker}}\n" "Latest: {{reports.latest(inputs.ticker).name}}"
            ),
            "inputs": {},
        },
    )

    assert response.status_code == 200
    assert response.json()["compiled"] == (
        "Ticker: [Missing input: ticker]\n" "Latest: [Missing input: ticker]"
    )


def test_validate_supported_database_engine_rejects_non_postgres() -> None:
    unsupported_engine = UnsupportedEngine("mysql")

    with pytest.raises(RuntimeError, match="requires PostgreSQL"):
        validate_supported_database_engine(unsupported_engine)


def test_init_db_creates_symbol_name_cache_as_unlogged_table(database_url: str) -> None:
    init_db(database_url)
    engine = create_engine(database_url, future=True)

    try:
        with engine.connect() as connection:
            relpersistence = connection.exec_driver_sql(
                "SELECT relpersistence FROM pg_class WHERE relname = 'symbol_name_cache'"
            ).scalar_one()

        assert relpersistence == "u"
    finally:
        engine.dispose()


def test_report_compile_crud_and_download(client: TestClient) -> None:
    template = create_template(
        client,
        name="Monthly Report",
        content="# Report\n\nTicker: {{inputs.ticker}}",
    )

    compile_response = client.post(
        f"/api/v1/reports/compile/{template['id']}",
        json={"inputs": {"ticker": "AAPL"}},
    )
    assert compile_response.status_code == 201
    report = compile_response.json()
    assert report["name"].startswith("monthly_report_")
    assert report["slug"].startswith("monthly_report_")
    assert report["source"] == "compiled"
    assert "metadata" in report
    assert "Ticker: AAPL" in report["content"]
    assert "createdAt" in report
    assert "updatedAt" in report

    list_response = client.get("/api/v1/reports")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["id"] == report["id"]

    get_response = client.get(f"/api/v1/reports/{report['slug']}")
    assert get_response.status_code == 200
    assert get_response.json()["name"] == report["name"]
    assert get_response.json()["content"] == report["content"]

    update_response = client.patch(
        f"/api/v1/reports/{report['slug']}",
        json={"content": "# Edited Report\n\nManual edit."},
    )
    assert update_response.status_code == 200
    assert update_response.json()["content"] == "# Edited Report\n\nManual edit."
    assert update_response.json()["name"] == report["name"]

    download_response = client.get(f"/api/v1/reports/{report['slug']}/download")
    assert download_response.status_code == 200
    assert "text/markdown" in download_response.headers["content-type"]
    assert f'filename="{report["slug"]}.md"' in download_response.headers["content-disposition"]
    assert download_response.text == "# Edited Report\n\nManual edit."

    delete_response = client.delete(f"/api/v1/reports/{report['slug']}")
    assert delete_response.status_code == 204

    missing_response = client.get(f"/api/v1/reports/{report['slug']}")
    assert missing_response.status_code == 404
    assert missing_response.json()["code"] == "not_found"


def test_report_compile_nonexistent_template(client: TestClient) -> None:
    response = client.post("/api/v1/reports/compile/99999")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def test_report_name_generation_and_uniqueness(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixed_now = datetime(2026, 3, 18, 10, 56, 51, tzinfo=UTC_TZ)
    monkeypatch.setattr(
        "app.extensions.signaldeck_finance.services.report_service.utcnow",
        lambda: fixed_now,
    )

    template = create_template(
        client,
        name="Q1 Summary",
        content="# Q1",
    )

    first = client.post(f"/api/v1/reports/compile/{template['id']}")
    assert first.status_code == 201
    first_name = first.json()["name"]
    first_slug = first.json()["slug"]
    assert first_name.startswith("q1_summary_")
    assert first_slug == first_name

    second = client.post(f"/api/v1/reports/compile/{template['id']}")
    assert second.status_code == 201
    second_name = second.json()["name"]
    second_slug = second.json()["slug"]
    assert second_name != first_name
    assert second_name.startswith("q1_summary_")
    assert second_name.endswith("_2")
    assert second_slug == second_name


def test_report_name_normalization(client: TestClient) -> None:
    template = create_template(
        client,
        name="My Report — March",
        content="# March",
    )

    response = client.post(f"/api/v1/reports/compile/{template['id']}")
    assert response.status_code == 201
    name = response.json()["name"]
    assert re.fullmatch(r"my_report_march_\d{8}_\d{6}", name)


def test_report_update_name_immutability(client: TestClient) -> None:
    template = create_template(client, name="Test", content="# Test")
    report = client.post(f"/api/v1/reports/compile/{template['id']}").json()

    response = client.patch(
        f"/api/v1/reports/{report['slug']}",
        json={"content": "# Updated", "name": "new_name"},
    )
    assert response.status_code == 422


def test_report_update_validation(client: TestClient) -> None:
    template = create_template(client, name="Test", content="# Test")
    report = client.post(f"/api/v1/reports/compile/{template['id']}").json()

    empty_payload = client.patch(f"/api/v1/reports/{report['slug']}", json={})
    assert empty_payload.status_code == 422

    whitespace_content = client.patch(
        f"/api/v1/reports/{report['slug']}",
        json={"content": "   "},
    )
    assert whitespace_content.status_code == 422


def test_report_404s(client: TestClient) -> None:
    assert client.get("/api/v1/reports/99999").status_code == 404
    assert client.patch("/api/v1/reports/99999", json={"content": "x"}).status_code == 404
    assert client.delete("/api/v1/reports/99999").status_code == 404
    assert client.get("/api/v1/reports/99999/download").status_code == 404


def test_report_name_timestamp_format(client: TestClient) -> None:
    import re

    template = create_template(client, name="Timestamp Test", content="# Test")
    report = client.post(f"/api/v1/reports/compile/{template['id']}").json()
    name = report["name"]

    pattern = r"^timestamp_test_\d{8}_\d{6}$"
    assert re.match(pattern, name), f"Name '{name}' does not match expected format"


def test_report_name_max_length_truncation(client: TestClient) -> None:
    long_name = "A" * 100
    template = create_template(client, name=long_name, content="# Long")
    report = client.post(f"/api/v1/reports/compile/{template['id']}").json()
    assert len(report["name"]) <= 200


def test_report_upload_crud_and_download(client: TestClient) -> None:
    upload_response = client.post(
        "/api/v1/reports/upload",
        files={
            "file": (
                "Quarterly Update.md",
                b"# Uploaded Report\n\nBody text.",
                "text/markdown",
            )
        },
        data={
            "slug": "quarterly_update",
            "author": "Analyst",
            "description": "Uploaded from disk",
            "tags": "quarterly, finance",
        },
    )
    assert upload_response.status_code == 201
    report = upload_response.json()
    assert report["name"] == "Quarterly Update"
    assert report["slug"] == "quarterly_update"
    assert report["source"] == "uploaded"
    assert report["metadata"] == {
        "author": "Analyst",
        "description": "Uploaded from disk",
        "tags": ["quarterly", "finance"],
    }

    get_response = client.get(f"/api/v1/reports/{report['slug']}")
    assert get_response.status_code == 200
    assert get_response.json()["content"] == "# Uploaded Report\n\nBody text."

    update_response = client.patch(
        f"/api/v1/reports/{report['slug']}",
        json={"content": "# Uploaded Report\n\nEdited body text."},
    )
    assert update_response.status_code == 200
    assert update_response.json()["content"] == "# Uploaded Report\n\nEdited body text."

    download_response = client.get(f"/api/v1/reports/{report['slug']}/download")
    assert download_response.status_code == 200
    assert f'filename="{report["slug"]}.md"' in download_response.headers["content-disposition"]
    assert download_response.text == "# Uploaded Report\n\nEdited body text."

    delete_response = client.delete(f"/api/v1/reports/{report['slug']}")
    assert delete_response.status_code == 204


@pytest.mark.parametrize(
    ("filename", "content", "content_type", "expected_code"),
    [
        ("notes.txt", b"# Not markdown", "text/plain", "invalid_file_type"),
        ("broken.md", b"\xff\xfe\x00", "application/octet-stream", "invalid_file_encoding"),
    ],
)
def test_report_upload_validation(
    client: TestClient,
    filename: str,
    content: bytes,
    content_type: str,
    expected_code: str,
) -> None:
    response = client.post(
        "/api/v1/reports/upload",
        files={"file": (filename, content, content_type)},
    )
    assert response.status_code == 400
    assert response.json()["code"] == expected_code


def test_report_compile_accepts_extensible_metadata(client: TestClient) -> None:
    template = create_template(client, name="Weekly Review", content="# Weekly")

    response = client.post(
        f"/api/v1/reports/compile/{template['id']}",
        json={
            "metadata": {
                "author": " Analyst ",
                "tags": [" weekly_review ", "reflection"],
                "analysis": {
                    "ticker": "aapl",
                    "customKey": "custom-value",
                },
                "customBlock": {"foo": "bar"},
            }
        },
    )

    assert response.status_code == 201
    report = response.json()
    assert report["source"] == "compiled"
    assert report["metadata"]["author"] == "Analyst"
    assert report["metadata"]["tags"] == ["weekly_review", "reflection"]
    assert report["metadata"]["analysis"]["ticker"] == "AAPL"
    assert report["metadata"]["analysis"]["customKey"] == "custom-value"
    assert report["metadata"]["customBlock"] == {"foo": "bar"}


def test_report_compile_accepts_runtime_inputs(client: TestClient) -> None:
    client.post(
        "/api/v1/reports",
        json={
            "name": "MSFT Prior Analysis",
            "content": "MSFT prior report body",
            "metadata": {
                "tags": ["msft_loop"],
                "analysis": {"ticker": "MSFT"},
            },
        },
    )

    template = create_template(
        client,
        name="Runtime Report Template",
        content=("Ticker: {{inputs.ticker}}\n" "Prior: {{reports.latest(inputs.ticker).content}}"),
    )

    response = client.post(
        f"/api/v1/reports/compile/{template['id']}",
        json={
            "inputs": {
                "ticker": "MSFT",
            },
            "metadata": {
                "tags": ["runtime_compile"],
            },
        },
    )

    assert response.status_code == 201
    report = response.json()
    assert report["content"] == ("Ticker: MSFT\n" "Prior: MSFT prior report body")
    assert report["metadata"]["tags"] == ["runtime_compile"]


def test_report_create_external_json(client: TestClient) -> None:
    response = client.post(
        "/api/v1/reports",
        json={
            "name": "AAPL Weekly Reflection",
            "content": "# AAPL\n\nReview body.",
            "metadata": {
                "tags": ["weekly_review"],
                "analysis": {
                    "ticker": "aapl",
                    "reviewType": "weekly_review",
                },
                "customFlag": True,
            },
        },
    )

    assert response.status_code == 201
    report = response.json()
    assert report["name"] == "AAPL Weekly Reflection"
    assert report["slug"] == "aapl_weekly_reflection"
    assert report["source"] == "external"
    assert report["metadata"]["tags"] == ["weekly_review"]
    assert report["metadata"]["analysis"]["ticker"] == "AAPL"
    assert report["metadata"]["analysis"]["reviewType"] == "weekly_review"
    assert report["metadata"]["customFlag"] is True

    get_response = client.get(f"/api/v1/reports/{report['slug']}")
    assert get_response.status_code == 200
    assert get_response.json()["source"] == "external"


def test_report_external_non_agent_update_and_delete_remains_allowed(
    client: TestClient,
) -> None:
    create_response = client.post(
        "/api/v1/reports",
        json={
            "name": "AAPL External Follow Up",
            "content": "# AAPL\n\nOriginal body.",
            "metadata": {
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "weekly_review",
                    "versionGroup": "weekly_review/v1",
                },
            },
        },
    )
    assert create_response.status_code == 201
    report = create_response.json()

    update_response = client.patch(
        f"/api/v1/reports/{report['slug']}",
        json={"content": "# AAPL\n\nEdited external body."},
    )
    assert update_response.status_code == 200
    assert update_response.json()["source"] == "external"
    assert update_response.json()["content"] == "# AAPL\n\nEdited external body."

    delete_response = client.delete(f"/api/v1/reports/{report['slug']}")
    assert delete_response.status_code == 204
    assert client.get(f"/api/v1/reports/{report['slug']}").status_code == 404


def test_report_create_external_slug_conflict(client: TestClient) -> None:
    first = client.post(
        "/api/v1/reports",
        json={
            "name": "External One",
            "slug": "external_one",
            "content": "# One",
        },
    )
    assert first.status_code == 201

    second = client.post(
        "/api/v1/reports",
        json={
            "name": "External Two",
            "slug": "external_one",
            "content": "# Two",
        },
    )
    assert second.status_code == 409
    assert second.json()["code"] == "slug_conflict"


def test_report_list_filters_and_pagination(client: TestClient) -> None:
    template = create_template(client, name="AAPL Weekly Template", content="# Weekly")

    compiled = client.post(
        f"/api/v1/reports/compile/{template['id']}",
        json={
            "metadata": {
                "tags": ["weekly_review", "reflection"],
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "weekly_review",
                },
            }
        },
    ).json()

    external_aapl = client.post(
        "/api/v1/reports",
        json={
            "name": "AAPL Monthly Reflection",
            "content": "# AAPL Monthly",
            "metadata": {
                "tags": ["monthly_review"],
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "monthly_review",
                },
            },
        },
    ).json()

    external_msft = client.post(
        "/api/v1/reports",
        json={
            "name": "MSFT Weekly Reflection",
            "content": "# MSFT Weekly",
            "metadata": {
                "tags": ["weekly_review"],
                "analysis": {
                    "ticker": "MSFT",
                    "reviewType": "weekly_review",
                },
            },
        },
    ).json()

    uploaded = client.post(
        "/api/v1/reports/upload",
        files={
            "file": (
                "Uploaded Note.md",
                b"# Uploaded Note\n\nArchive body.",
                "text/markdown",
            )
        },
        data={
            "slug": "uploaded_note",
            "tags": "archive",
        },
    ).json()

    all_reports = client.get("/api/v1/reports")
    assert all_reports.status_code == 200
    assert [report["id"] for report in all_reports.json()] == [
        uploaded["id"],
        external_msft["id"],
        external_aapl["id"],
        compiled["id"],
    ]

    by_ticker = client.get("/api/v1/reports", params={"ticker": "aapl"})
    assert by_ticker.status_code == 200
    assert [report["id"] for report in by_ticker.json()] == [
        external_aapl["id"],
        compiled["id"],
    ]

    by_tag = client.get("/api/v1/reports", params={"tag": "weekly_review"})
    assert by_tag.status_code == 200
    assert [report["id"] for report in by_tag.json()] == [
        external_msft["id"],
        compiled["id"],
    ]

    by_review_type = client.get("/api/v1/reports", params={"reviewType": "weekly_review"})
    assert by_review_type.status_code == 200
    assert [report["id"] for report in by_review_type.json()] == [
        external_msft["id"],
        compiled["id"],
    ]

    by_source = client.get("/api/v1/reports", params={"source": "external"})
    assert by_source.status_code == 200
    assert [report["id"] for report in by_source.json()] == [
        external_msft["id"],
        external_aapl["id"],
    ]

    combined = client.get(
        "/api/v1/reports",
        params={
            "ticker": "AAPL",
            "reviewType": "weekly_review",
        },
    )
    assert combined.status_code == 200
    assert [report["id"] for report in combined.json()] == [compiled["id"]]

    paginated = client.get(
        "/api/v1/reports",
        params={"source": "external", "limit": 1, "offset": 1},
    )
    assert paginated.status_code == 200
    assert [report["id"] for report in paginated.json()] == [external_aapl["id"]]


def test_report_source_filter_accepts_agent(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    external_response = client.post(
        "/api/v1/reports",
        json={
            "name": "True External Filter Companion",
            "content": "# External",
        },
    )
    assert external_response.status_code == 201
    external_report = external_response.json()
    assert external_report["source"] == "external"

    agent_report_id = insert_report_row(
        session_factory,
        name="Agent Review Report",
        slug="agent_review_report",
        source="agent",
        content="# Agent Review",
        metadata={
            "createdBy": {
                "type": "agent",
                "runId": 101,
                "agentKey": "analyst",
                "agentVersion": 1,
            },
            "analysis": {
                "reviewType": "agent_review",
                "versionGroup": "agent_review/v1",
                "runId": 101,
                "agentKey": "analyst",
                "agentVersion": 1,
            },
        },
    )

    response = client.get("/api/v1/reports", params={"source": "agent"})

    assert response.status_code == 200
    reports = response.json()
    assert [report["id"] for report in reports] == [agent_report_id]
    assert reports[0]["source"] == "agent"
    assert reports[0]["metadata"]["createdBy"]["agentKey"] == "analyst"


def test_report_read_schema_explicitly_owns_created_by_metadata(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    schema = ReportRead.model_json_schema(by_alias=True)
    report_read_properties = cast(dict[str, object], schema["properties"])
    metadata_schema = cast(dict[str, object], report_read_properties["metadata_"])
    metadata_schema_ref = metadata_schema["$ref"]
    metadata_definition_key = str(metadata_schema_ref).removeprefix("#/$defs/")
    read_metadata_schema = cast(dict[str, object], schema["$defs"])[metadata_definition_key]
    read_metadata_properties = cast(
        dict[str, object],
        cast(dict[str, object], read_metadata_schema)["properties"],
    )
    assert metadata_definition_key == "ReportReadMetadata"

    created_by_schema = cast(dict[str, object], read_metadata_properties["createdBy"])
    created_by_schema_options = cast(list[object], created_by_schema["anyOf"])
    created_by_schema_ref = cast(
        dict[str, object],
        created_by_schema_options[0],
    )["$ref"]
    created_by_definition_key = str(created_by_schema_ref).removeprefix("#/$defs/")
    created_by_definition = cast(dict[str, object], schema["$defs"])[created_by_definition_key]
    created_by_properties = cast(
        dict[str, object],
        cast(dict[str, object], created_by_definition)["properties"],
    )

    assert set(created_by_properties) == {
        "type",
        "runId",
        "agentKey",
        "agentVersion",
        "agentName",
        "workflowKey",
        "workflowVersion",
        "stepId",
        "slot",
        "traceId",
    }
    assert cast(dict[str, object], created_by_definition)["required"] == [
        "type",
        "runId",
        "agentKey",
        "agentVersion",
    ]

    report_id = insert_report_row(
        session_factory,
        name="Explicit CreatedBy Read Contract",
        slug="explicit_created_by_read_contract",
        source="agent",
        content="# Agent Review",
        metadata={
            "createdBy": {
                "type": "agent",
                "runId": 404,
                "agentKey": "analyst",
                "agentVersion": 7,
                "workflowKey": "daily_review",
                "workflowVersion": 2,
                "traceId": "trace-explicit-created-by",
            },
            "analysis": {
                "reviewType": "agent_review",
                "versionGroup": "agent_review/v1",
            },
            "unmodeledExtensionField": "preserved",
        },
    )

    response = client.get("/api/v1/reports/explicit_created_by_read_contract")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == report_id
    assert payload["metadata"]["createdBy"] == {
        "type": "agent",
        "runId": 404,
        "agentKey": "analyst",
        "agentVersion": 7,
        "workflowKey": "daily_review",
        "workflowVersion": 2,
        "traceId": "trace-explicit-created-by",
    }
    assert payload["metadata"]["analysis"] == {
        "reviewType": "agent_review",
        "versionGroup": "agent_review/v1",
    }
    assert payload["metadata"]["unmodeledExtensionField"] == "preserved"


def test_report_source_filter_external_excludes_agent_reports(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    external_response = client.post(
        "/api/v1/reports",
        json={
            "name": "True External Report",
            "content": "# External",
        },
    )
    assert external_response.status_code == 201
    external_report = external_response.json()
    agent_report_id = insert_report_row(
        session_factory,
        name="Agent Review External Exclusion",
        slug="agent_review_external_exclusion",
        source="agent",
        content="# Agent Review",
        metadata={
            "createdBy": {
                "type": "agent",
                "runId": 202,
                "agentKey": "analyst",
                "agentVersion": 1,
            },
            "analysis": {
                "reviewType": "agent_review",
                "versionGroup": "agent_review/v1",
                "runId": 202,
                "agentKey": "analyst",
                "agentVersion": 1,
            },
        },
    )

    agent_response = client.get("/api/v1/reports", params={"source": "agent"})
    response = client.get("/api/v1/reports", params={"source": "external"})

    assert agent_response.status_code == 200
    agent_report_ids = [report["id"] for report in agent_response.json()]
    assert agent_report_ids == [agent_report_id]
    assert agent_response.json()[0]["metadata"]["createdBy"]["runId"] == 202

    assert response.status_code == 200
    report_ids = [report["id"] for report in response.json()]
    assert report_ids == [external_report["id"]]
    assert response.json()[0]["source"] == "external"


def test_public_report_create_rejects_agent_created_by_provenance(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    created_by = {
        "type": "agent",
        "runId": 303,
        "agentKey": "spoofed-agent",
        "agentVersion": 1,
    }
    expected_message = (
        "Report createdBy provenance is server-owned and cannot be supplied for non-agent reports."
    )

    create_response = client.post(
        "/api/v1/reports",
        json={
            "name": "Spoofed External Report",
            "content": "# Spoofed",
            "metadata": {"createdBy": created_by},
        },
    )

    assert create_response.status_code == 400
    assert create_response.json()["code"] == "invalid_report_provenance"
    assert create_response.json()["message"] == expected_message

    template = create_template(client, name="Spoofed Compile", content="# Compile")
    compile_response = client.post(
        f"/api/v1/reports/compile/{template['id']}",
        json={"metadata": {"createdBy": created_by}},
    )

    assert compile_response.status_code == 400
    assert compile_response.json()["code"] == "invalid_report_provenance"
    assert compile_response.json()["message"] == expected_message

    with session_factory() as session:
        service = ReportService(session)
        with pytest.raises(ApiError) as upload_error:
            service.create_from_upload(
                content="# Uploaded Spoof",
                slug="uploaded_spoof",
                name="Uploaded Spoof",
                metadata={"createdBy": created_by},
            )
        with pytest.raises(ApiError) as external_error:
            service.create_external_report(
                content="# Snake Case Spoof",
                name="Snake Case Spoof",
                metadata={"created_by": created_by},
            )

    for error in (upload_error.value, external_error.value):
        assert error.status_code == 400
        assert error.code == "invalid_report_provenance"
        assert error.message == expected_message


def test_report_placeholder_all_paths(client: TestClient) -> None:
    source_template = create_template(
        client,
        name="Source",
        content="Name: {{inputs.name}}",
    )
    report_response = client.post(
        f"/api/v1/reports/compile/{source_template['id']}",
        json={"inputs": {"name": "Growth"}},
    )
    assert report_response.status_code == 201
    report = report_response.json()
    report_name = report["name"]

    meta_template = create_template(
        client,
        name="Report Meta Test",
        content=(
            "All: {{reports}}\n"
            f"Single: {{{{reports.{report_name}}}}}\n"
            f"Content: {{{{reports.{report_name}.content}}}}\n"
            f"NameField: {{{{reports.{report_name}.name}}}}\n"
            f"Created: {{{{reports.{report_name}.created_at}}}}\n"
            "Unknown: {{reports.nonexistent_report}}\n"
            f"BadField: {{{{reports.{report_name}.unknown_field}}}}"
        ),
    )

    compile_response = client.get(f"/api/v1/templates/{meta_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]

    assert compiled.startswith("All: - **")
    assert f"**{report_name}**" in compiled

    single_line = [line for line in compiled.split("\n") if line.startswith("Single: ")][0]
    assert single_line.startswith(f"Single: **{report_name}**")
    assert "(" in single_line and "Z)" in single_line

    assert "Content: Name: Growth" in compiled

    assert f"NameField: {report_name}" in compiled

    created_line = [line for line in compiled.split("\n") if line.startswith("Created: ")][0]
    created_value = created_line.replace("Created: ", "")
    assert created_value.endswith("Z")
    assert "T" in created_value

    assert "[Unknown report: nonexistent_report]" in compiled
    assert "[Unknown report field: unknown_field]" in compiled


def test_report_placeholder_recompilation(client: TestClient) -> None:
    source_template = create_template(
        client,
        name="Recomp Source",
        content="Original: {{inputs.name}}",
    )
    report = client.post(
        f"/api/v1/reports/compile/{source_template['id']}",
        json={"inputs": {"name": "Recomp"}},
    ).json()
    report_name = report["name"]

    client.patch(
        f"/api/v1/reports/{report['slug']}",
        json={"content": "Name: {{inputs.name}}\nTicker: {{inputs.ticker}}"},
    )

    embed_template = create_template(
        client,
        name="Embed Test",
        content=f"{{{{reports.{report_name}.content}}}}",
    )
    compile_response = client.get(f"/api/v1/templates/{embed_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]

    assert "Name: [Missing input: name]" in compiled
    assert "Ticker: [Missing input: ticker]" in compiled


def test_report_placeholder_cycle_detection_self_reference(
    client: TestClient,
) -> None:
    source_template = create_template(client, name="Self Ref", content="# Self")
    report = client.post(f"/api/v1/reports/compile/{source_template['id']}").json()
    report_name = report["name"]

    client.patch(
        f"/api/v1/reports/{report['slug']}",
        json={"content": f"{{{{reports.{report_name}.content}}}}"},
    )

    embed_template = create_template(
        client,
        name="Self Ref Embed",
        content=f"{{{{reports.{report_name}.content}}}}",
    )
    compile_response = client.get(f"/api/v1/templates/{embed_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]
    assert f"[Circular report reference: {report_name}]" in compiled


def test_report_placeholder_cycle_detection_indirect(
    client: TestClient,
) -> None:
    tmpl_a = create_template(client, name="Cycle A", content="# A")
    tmpl_b = create_template(client, name="Cycle B", content="# B")
    report_a = client.post(f"/api/v1/reports/compile/{tmpl_a['id']}").json()
    report_b = client.post(f"/api/v1/reports/compile/{tmpl_b['id']}").json()
    name_a = report_a["name"]
    name_b = report_b["name"]

    client.patch(
        f"/api/v1/reports/{report_a['slug']}",
        json={"content": f"A includes B: {{{{reports.{name_b}.content}}}}"},
    )
    client.patch(
        f"/api/v1/reports/{report_b['slug']}",
        json={"content": f"B includes A: {{{{reports.{name_a}.content}}}}"},
    )

    embed_template = create_template(
        client,
        name="Indirect Cycle",
        content=f"{{{{reports.{name_a}.content}}}}",
    )
    compile_response = client.get(f"/api/v1/templates/{embed_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]
    assert (
        f"[Circular report reference: {name_a}]" in compiled
        or f"[Circular report reference: {name_b}]" in compiled
    )


def test_placeholder_tree_includes_reports(client: TestClient) -> None:
    source_template = create_template(client, name="Tree Test", content="# Tree")
    report = client.post(f"/api/v1/reports/compile/{source_template['id']}").json()

    tree_response = client.get("/api/v1/templates/placeholders")
    assert tree_response.status_code == 200
    tree = tree_response.json()

    assert "reports" in tree
    report_names = [r["name"] for r in tree["reports"]]
    assert report["name"] in report_names
    assert "createdAt" in tree["reports"][0]


def test_report_placeholder_dynamic_selectors(client: TestClient) -> None:
    source_template = create_template(client, name="Latest Report", content="Compiled AAPL")
    compiled_aapl = client.post(
        f"/api/v1/reports/compile/{source_template['id']}",
        json={
            "metadata": {
                "tags": ["weekly_review"],
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "weekly_review",
                },
            }
        },
    ).json()

    external_aapl = client.post(
        "/api/v1/reports",
        json={
            "name": "AAPL Dynamic Latest",
            "content": "Dynamic AAPL: {{inputs.ticker}}",
            "metadata": {
                "tags": ["weekly_review"],
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "weekly_review",
                },
            },
        },
    ).json()

    external_msft = client.post(
        "/api/v1/reports",
        json={
            "name": "MSFT Dynamic Latest",
            "content": "MSFT body",
            "metadata": {
                "tags": ["weekly_review"],
                "analysis": {
                    "ticker": "MSFT",
                    "reviewType": "weekly_review",
                },
            },
        },
    ).json()

    selector_template = create_template(
        client,
        name="Dynamic Selector Test",
        content=(
            "LatestMeta: {{reports.latest}}\n"
            "LatestName: {{reports.latest.name}}\n"
            'TickerLatestName: {{reports.latest("AAPL").name}}\n'
            'TickerLatestContent: {{reports.latest("AAPL").content}}\n'
            "IndexZeroName: {{reports[0].name}}\n"
            'TagLatestName: {{reports.by_tag("weekly_review").latest.name}}\n'
            'TagLatestContent: {{reports.by_tag("weekly_review").latest.content}}\n'
            'NoMatchInline: before{{reports.latest("NVDA").name}}after\n'
            "NoMatchIndex: before{{reports[99].content}}after\n"
            'InvalidSelector: {{reports.by_tag("weekly_review")}}\n'
            f"ExactNameReportName: {{{{reports.{compiled_aapl['name']}.name}}}}"
        ),
    )

    compile_response = client.get(f"/api/v1/templates/{selector_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]

    latest_meta_line = [line for line in compiled.split("\n") if line.startswith("LatestMeta: ")][0]
    assert latest_meta_line.startswith(f"LatestMeta: **{external_msft['name']}**")
    assert f"LatestName: {external_msft['name']}" in compiled
    assert f"TickerLatestName: {external_aapl['name']}" in compiled
    assert "TickerLatestContent: Dynamic AAPL: [Missing input: ticker]" in compiled
    assert f"IndexZeroName: {external_msft['name']}" in compiled
    assert f"TagLatestName: {external_msft['name']}" in compiled
    assert "TagLatestContent: MSFT body" in compiled
    assert "NoMatchInline: beforeafter" in compiled
    assert "NoMatchIndex: beforeafter" in compiled
    assert 'InvalidSelector: [Invalid report selector: reports.by_tag("weekly_review")]' in compiled
    assert f"ExactNameReportName: {compiled_aapl['name']}" in compiled


def test_report_placeholder_dynamic_selector_cycle_detection(client: TestClient) -> None:
    source_template = create_template(client, name="Cycle Selector", content="# Start")
    report = client.post(
        f"/api/v1/reports/compile/{source_template['id']}",
        json={
            "metadata": {
                "tags": ["weekly_review"],
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "weekly_review",
                },
            }
        },
    ).json()

    client.patch(
        f"/api/v1/reports/{report['slug']}",
        json={"content": '{{reports.latest("AAPL").content}}'},
    )

    embed_template = create_template(
        client,
        name="Dynamic Cycle Embed",
        content='{{reports.latest("AAPL").content}}',
    )
    compile_response = client.get(f"/api/v1/templates/{embed_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]
    assert f"[Circular report reference: {report['name']}]" in compiled


def test_report_filters_and_dynamic_selectors_ignore_reports_without_analysis_metadata(
    client: TestClient,
) -> None:
    client.post(
        "/api/v1/reports/upload",
        files={
            "file": (
                "Uploaded Note.md",
                b"# Uploaded Note\n\nLegacy body.",
                "text/markdown",
            )
        },
        data={"slug": "uploaded_note"},
    ).json()

    external = client.post(
        "/api/v1/reports",
        json={
            "name": "AAPL Metadata Report",
            "content": "AAPL body",
            "metadata": {
                "analysis": {
                    "ticker": "AAPL",
                    "reviewType": "weekly_review",
                }
            },
        },
    ).json()

    filtered = client.get("/api/v1/reports", params={"ticker": "AAPL"})
    assert filtered.status_code == 200
    assert [report["id"] for report in filtered.json()] == [external["id"]]

    selector_template = create_template(
        client,
        name="Missing Analysis Selector",
        content=(
            'TickerLatest: {{reports.latest("AAPL").name}}\n'
            'NoTickerMatch: before{{reports.latest("MSFT").content}}after'
        ),
    )

    compile_response = client.get(f"/api/v1/templates/{selector_template['id']}/compile")
    assert compile_response.status_code == 200
    compiled = compile_response.json()["compiled"]

    assert compiled == f"TickerLatest: {external['name']}\nNoTickerMatch: beforeafter"


def test_model_connection_secret_writes_are_explicit_encrypted_and_public_reads_safe(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    credential_value = uuid4().hex
    rotated_value = uuid4().hex

    create_response = client.post(
        "/api/model-connections",
        json={**_model_connection_create_payload(), "apiKey": credential_value},
    )
    assert create_response.status_code == 201, create_response.json()
    create_body = cast(dict[str, object], create_response.json())
    connection_id = cast(int, create_body["id"])
    assert "apiKey" not in create_body
    assert "secretPayload" not in create_body

    list_response = client.get("/api/model-connections")
    assert list_response.status_code == 200, list_response.json()
    list_body = cast(dict[str, object], list_response.json())
    assert "apiKey" not in str(list_body)
    assert "secretPayload" not in str(list_body)

    get_response = client.get(f"/api/model-connections/{connection_id}")
    assert get_response.status_code == 200, get_response.json()
    get_body = cast(dict[str, object], get_response.json())
    assert "apiKey" not in get_body
    assert "secretPayload" not in get_body

    with session_factory() as session:
        raw_secret_payload = session.execute(
            sql_text("SELECT secret_payload::text FROM model_connections WHERE id = :id"),
            {"id": connection_id},
        ).scalar_one()
        assert "__encrypted__" in str(raw_secret_payload)
        assert credential_value not in str(raw_secret_payload)
        connection = session.get(ModelConnection, connection_id)
        assert connection is not None
        assert connection.secret_payload == {"apiKey": credential_value}

    omitted_secret_patch = client.patch(
        f"/api/model-connections/{connection_id}",
        json={"description": "Updated without credential rotation."},
    )
    assert omitted_secret_patch.status_code == 200, omitted_secret_patch.json()
    assert "apiKey" not in cast(dict[str, object], omitted_secret_patch.json())
    with session_factory() as session:
        connection = session.get(ModelConnection, connection_id)
        assert connection is not None
        assert connection.secret_payload == {"apiKey": credential_value}

    rejected_blank_patch = client.patch(
        f"/api/model-connections/{connection_id}",
        json={"apiKey": "   "},
    )
    assert rejected_blank_patch.status_code == 422, rejected_blank_patch.json()
    rejected_null_patch = client.patch(
        f"/api/model-connections/{connection_id}",
        json={"apiKey": None},
    )
    assert rejected_null_patch.status_code == 422, rejected_null_patch.json()
    with session_factory() as session:
        connection = session.get(ModelConnection, connection_id)
        assert connection is not None
        assert connection.secret_payload == {"apiKey": credential_value}

    rotated_patch = client.patch(
        f"/api/model-connections/{connection_id}",
        json={"apiKey": rotated_value},
    )
    assert rotated_patch.status_code == 200, rotated_patch.json()
    assert "apiKey" not in cast(dict[str, object], rotated_patch.json())

    with session_factory() as session:
        raw_secret_payload = session.execute(
            sql_text("SELECT secret_payload::text FROM model_connections WHERE id = :id"),
            {"id": connection_id},
        ).scalar_one()
        assert "__encrypted__" in str(raw_secret_payload)
        assert credential_value not in str(raw_secret_payload)
        assert rotated_value not in str(raw_secret_payload)
        connection = session.get(ModelConnection, connection_id)
        assert connection is not None
        assert connection.secret_payload == {"apiKey": rotated_value}


def test_model_connection_resolution_derives_caps_and_rejects_public_policy_writes(
    client: TestClient,
) -> None:
    create_payload = {
        **_model_connection_create_payload(),
        "protocolProfile": "openai_chat_completions",
    }
    public_runtime_profile_fields: dict[str, object] = {
        "apiStyle": "chat_completions",
        "capabilities": {"nativeToolCalls": {"status": "supported"}},
        "outputStrategyPolicy": "allow_json_object_validation",
        "parallelToolCallsPolicy": "forbid",
        "reasoningPolicy": "forbid",
        "streamingPolicy": "forbid",
        "probeCacheTtlSeconds": 300,
    }

    rejected_create = client.post(
        "/api/model-connections",
        json={**create_payload, **public_runtime_profile_fields},
    )
    field_names = set(public_runtime_profile_fields)
    _assert_unsupported_model_connection_fields_rejected(rejected_create, field_names)

    create_response = client.post("/api/model-connections", json=create_payload)
    assert create_response.status_code == 201, create_response.json()
    create_body = cast(dict[str, object], create_response.json())
    assert create_body["protocolProfile"] == "openai_chat_completions"
    assert create_body["outputStrategyPolicy"] == "prefer_strict_schema"
    assert create_body["parallelToolCallsPolicy"] == "serialize"
    assert create_body["reasoningPolicy"] == "allow"
    assert create_body["streamingPolicy"] == "allow"
    assert create_body["probeCacheTtlSeconds"] == 900
    assert create_body["lastProbedAt"] is None
    assert create_body["capabilities"] == default_model_connection_capabilities(
        "openai_chat_completions"
    ).model_dump(mode="json", by_alias=True)
    connection_id = cast(int, create_body["id"])

    rejected_patch = client.patch(
        f"/api/model-connections/{connection_id}",
        json=public_runtime_profile_fields,
    )
    _assert_unsupported_model_connection_fields_rejected(rejected_patch, field_names)

    patch_response = client.patch(
        f"/api/model-connections/{connection_id}",
        json={"protocolProfile": "openai_responses"},
    )
    assert patch_response.status_code == 200, patch_response.json()
    patch_body = cast(dict[str, object], patch_response.json())
    assert patch_body["protocolProfile"] == "openai_responses"
    assert patch_body["outputStrategyPolicy"] == "prefer_strict_schema"
    assert patch_body["parallelToolCallsPolicy"] == "serialize"
    assert patch_body["reasoningPolicy"] == "allow"
    assert patch_body["streamingPolicy"] == "allow"
    assert patch_body["probeCacheTtlSeconds"] == 900
    assert patch_body["capabilities"] == default_model_connection_capabilities(
        "openai_responses"
    ).model_dump(mode="json", by_alias=True)


def test_model_connection_rejects_invalid_protocol_profile(
    client: TestClient,
) -> None:
    invalid_profile_response = client.post(
        "/api/model-connections",
        json={**_model_connection_create_payload(), "protocolProfile": "responses"},
    )
    assert invalid_profile_response.status_code == 422, invalid_profile_response.json()
    invalid_profile_body = cast(dict[str, object], invalid_profile_response.json())
    assert invalid_profile_body["code"] == "validation_error"

    with pytest.raises(ValidationError):
        ModelConnectionCreate.model_validate(
            {**_model_connection_create_payload(), "protocolProfile": "responses"}
        )


def test_model_connection_base_url_preserves_exact_user_input(
    client: TestClient,
) -> None:
    create_payload = _model_connection_create_payload(
        "https://provider.example.test/openai-compatible/",
    )

    create_response = client.post("/api/model-connections", json=create_payload)
    assert create_response.status_code == 201, create_response.json()
    create_body = cast(dict[str, object], create_response.json())
    assert create_body["baseUrl"] == "https://provider.example.test/openai-compatible/"
    connection_id = cast(int, create_body["id"])

    patch_response = client.patch(
        f"/api/model-connections/{connection_id}",
        json={"baseUrl": "https://provider.example.test/v1/responses/"},
    )
    assert patch_response.status_code == 200, patch_response.json()
    patch_body = cast(dict[str, object], patch_response.json())
    assert patch_body["baseUrl"] == "https://provider.example.test/v1/responses/"

    get_response = client.get(f"/api/model-connections/{connection_id}")
    assert get_response.status_code == 200, get_response.json()
    get_body = cast(dict[str, object], get_response.json())
    assert get_body["baseUrl"] == "https://provider.example.test/v1/responses/"

    assert (
        ModelConnectionCreate.model_validate(create_payload).base_url
        == "https://provider.example.test/openai-compatible/"
    )
    assert (
        ModelConnectionUpdate.model_validate(
            {"baseUrl": "https://provider.example.test/v1/responses/"}
        ).base_url
        == "https://provider.example.test/v1/responses/"
    )

    with pytest.raises(ValidationError):
        ModelConnectionCreate.model_validate(
            {
                **_model_connection_create_payload(
                    "https://provider.example.test/openai-compatible",
                ),
                "baseUrl": "https://provider.example.test/openai-compatible?query=1",
            }
        )

    fragment_invalid_response = client.post(
        "/api/model-connections",
        json={
            **_model_connection_create_payload(
                "https://provider.example.test/openai-compatible",
            ),
            "baseUrl": "https://provider.example.test/openai-compatible#fragment",
        },
    )
    assert fragment_invalid_response.status_code == 422, fragment_invalid_response.json()
    fragment_invalid_body = cast(dict[str, object], fragment_invalid_response.json())
    assert fragment_invalid_body["code"] == "validation_error"
    fragment_invalid_details = cast(list[dict[str, str]], fragment_invalid_body["details"])
    assert fragment_invalid_details[0]["field"] == "baseUrl"
    assert "fragment" in fragment_invalid_details[0]["issue"].lower()

    with pytest.raises(ValidationError):
        ModelConnectionCreate.model_validate(
            {
                **_model_connection_create_payload(
                    "https://provider.example.test/openai-compatible",
                ),
                "baseUrl": "https://provider.example.test/openai-compatible#fragment",
            }
        )

    with pytest.raises(ValidationError):
        ModelConnectionUpdate.model_validate(
            {"baseUrl": "ftp://provider.example.test/openai-compatible"}
        )


def test_model_connection_connection_test_uses_provider_openai_behavior(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    session_factory: sessionmaker[Session],
) -> None:
    fixed_now = datetime(2026, 5, 12, 15, 0, tzinfo=UTC_TZ)
    monkeypatch.setattr("app.services.model_connection_service.utcnow", lambda: fixed_now)

    request_log: list[dict[str, object]] = []
    with run_fake_openai_provider(base_path="/codex/v1", request_log=request_log) as base_url:
        create_response = client.post(
            "/api/model-connections",
            json=_model_connection_create_payload(base_url),
        )
        assert create_response.status_code == 201, create_response.json()
        create_body = cast(dict[str, object], create_response.json())
        connection_id = cast(int, create_body["id"])

        probe_seed_at = datetime(2026, 5, 12, 14, 50, tzinfo=UTC_TZ)
        _set_model_connection_probe_cache(
            session_factory,
            connection_id=connection_id,
            probed_at=probe_seed_at,
        )

        test_response = client.post(f"/api/model-connections/{connection_id}/connection-test")
        assert test_response.status_code == 200, test_response.json()

    request_paths = [cast(str, entry["path"]) for entry in request_log]
    assert request_paths == ["/codex/v1/responses"]

    test_body = cast(dict[str, object], test_response.json())
    assert test_body["modelConnectionId"] == connection_id
    assert test_body["ok"] is True
    assert test_body["message"] == "Connection test succeeded (request fake-openai-request)."
    assert (
        datetime.fromisoformat(cast(str, test_body["lastTestedAt"]).replace("Z", "+00:00"))
        == fixed_now
    )

    get_response = client.get(f"/api/model-connections/{connection_id}")
    assert get_response.status_code == 200, get_response.json()
    get_body = cast(dict[str, object], get_response.json())
    assert get_body["lastTestOk"] is True
    assert get_body["lastTestMessage"] == "Connection test succeeded (request fake-openai-request)."
    assert (
        datetime.fromisoformat(cast(str, get_body["lastTestedAt"]).replace("Z", "+00:00"))
        == fixed_now
    )
    assert get_body["lastProbedAt"] is None
    capabilities = cast(dict[str, dict[str, object]], get_body["capabilities"])
    assert capabilities["responsesApi"]["lastProbedAt"] is None
    assert capabilities["textGeneration"]["lastProbedAt"] is None


def test_model_connection_connection_test_passes_literal_trailing_slash_base_url_to_openai_client(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _LiteralBaseUrlRecordingOpenAIClient.reset()
    monkeypatch.setattr(
        "app.services.model_connection_service.OpenAI",
        _LiteralBaseUrlRecordingOpenAIClient,
        raising=False,
    )
    literal_base_url = "https://new.sharedchat.cc/codex/v1/"

    create_response = client.post(
        "/api/model-connections",
        json=_model_connection_create_payload(literal_base_url),
    )
    assert create_response.status_code == 201, create_response.json()
    connection_id = int(create_response.json()["id"])

    test_response = client.post(f"/api/model-connections/{connection_id}/connection-test")
    assert test_response.status_code == 200, test_response.json()
    assert test_response.json()["ok"] is True

    assert _LiteralBaseUrlRecordingOpenAIClient.init_calls[-1]["base_url"] == literal_base_url


def test_model_connection_connection_test_preserves_openai_style_control_root_base_url(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _LiteralBaseUrlRecordingOpenAIClient.reset()
    monkeypatch.setattr(
        "app.services.model_connection_service.OpenAI",
        _LiteralBaseUrlRecordingOpenAIClient,
        raising=False,
    )
    control_base_url = "https://api.openai.com/v1"

    create_response = client.post(
        "/api/model-connections",
        json=_model_connection_create_payload(control_base_url),
    )
    assert create_response.status_code == 201, create_response.json()
    connection_id = int(create_response.json()["id"])

    test_response = client.post(f"/api/model-connections/{connection_id}/connection-test")
    assert test_response.status_code == 200, test_response.json()
    assert test_response.json()["ok"] is True

    assert _LiteralBaseUrlRecordingOpenAIClient.init_calls[-1]["base_url"] == control_base_url


def test_model_connection_capability_probe_uses_cache_refresh_and_fixtures(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed_now = datetime(2026, 5, 12, 15, 0, tzinfo=UTC_TZ)
    fresh_probe_at = fixed_now - timedelta(minutes=5)
    stale_probe_at = fixed_now - timedelta(hours=2)

    class _ProbeOpenAIResponse:
        _request_id = "req-capability-probe"
        usage = {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}
        output_text = '{"ok": true}'
        output = [{"type": "message", "content": [{"type": "output_text", "text": "OK"}]}]
        choices = [{"message": {"content": "OK"}}]

    class _ProbeOpenAIStream:
        closed = False

        def close(self) -> None:
            self.closed = True

    class _CapabilityProbeOpenAIClient:
        init_calls: list[dict[str, object]] = []
        chat_calls: list[dict[str, object]] = []
        response_calls: list[dict[str, object]] = []

        class _Responses:
            def __init__(self, client: _CapabilityProbeOpenAIClient) -> None:
                self._client = client

            def create(self, **kwargs: object) -> _ProbeOpenAIResponse | _ProbeOpenAIStream:
                self._client.response_calls.append(dict(kwargs))
                return self._client._create_probe_response(kwargs)

        class _ChatCompletions:
            def __init__(self, client: _CapabilityProbeOpenAIClient) -> None:
                self._client = client

            def create(self, **kwargs: object) -> _ProbeOpenAIResponse | _ProbeOpenAIStream:
                self._client.chat_calls.append(dict(kwargs))
                return self._client._create_probe_response(kwargs)

        class _Chat:
            def __init__(self, client: _CapabilityProbeOpenAIClient) -> None:
                self.completions = _CapabilityProbeOpenAIClient._ChatCompletions(client)

        def __init__(self, **kwargs: object) -> None:
            self.init_calls.append(dict(kwargs))
            self.responses = self._Responses(self)
            self.chat = self._Chat(self)

        def __enter__(self) -> _CapabilityProbeOpenAIClient:
            return self

        def __exit__(self, exc_type: object, exc_value: object, exc_traceback: object) -> bool:
            return False

        @staticmethod
        def _contains_json_word(value: object) -> bool:
            if isinstance(value, str):
                return re.search(r"\bjson\b", value, re.IGNORECASE) is not None
            if isinstance(value, dict):
                return any(
                    _CapabilityProbeOpenAIClient._contains_json_word(item)
                    for item in value.values()
                )
            if isinstance(value, list):
                return any(_CapabilityProbeOpenAIClient._contains_json_word(item) for item in value)
            return False

        @staticmethod
        def _create_probe_response(
            kwargs: dict[str, object],
        ) -> _ProbeOpenAIResponse | _ProbeOpenAIStream:
            if kwargs.get("stream") is True:
                return _ProbeOpenAIStream()
            model = str(kwargs.get("model"))
            if model == "fake-tools-disabled" and "tools" in kwargs:
                raise RuntimeError("tool calls disabled by fake provider")
            text = kwargs.get("text")
            text_format = text.get("format") if isinstance(text, dict) else None
            response_format = kwargs.get("response_format")
            json_schema = (
                response_format.get("json_schema") if isinstance(response_format, dict) else None
            )
            json_object_requested = (
                isinstance(text_format, dict)
                and text_format.get("type") == "json_object"
                or isinstance(response_format, dict)
                and response_format.get("type") == "json_object"
            )
            prompt_payload = [
                kwargs.get("instructions"),
                kwargs.get("input"),
                kwargs.get("messages"),
            ]
            if json_object_requested and not _CapabilityProbeOpenAIClient._contains_json_word(
                prompt_payload
            ):
                raise RuntimeError(
                    "Prompt must contain the word 'json' in some form to use "
                    "'response_format' of type 'json_object'."
                )
            if model == "fake-strict-schema-disabled" and (
                isinstance(text_format, dict)
                and text_format.get("type") == "json_schema"
                or isinstance(json_schema, dict)
            ):
                raise RuntimeError("This response_format type is unavailable now")
            return _ProbeOpenAIResponse()

    fresh_capabilities = default_model_connection_capabilities("openai_chat_completions")
    fresh_capabilities.native_tool_calls.status = ModelConnectionCapabilityStatus.UNSUPPORTED
    fresh_capabilities.native_tool_calls.detail = (
        "Provider profile fixture keeps tool calls unsupported."
    )
    fresh_capabilities.strict_json_schema_output.status = (
        ModelConnectionCapabilityStatus.UNSUPPORTED
    )
    fresh_capabilities.strict_json_schema_output.detail = (
        "Provider profile fixture keeps strict schema unsupported."
    )
    for field_name in type(fresh_capabilities).model_fields:
        getattr(fresh_capabilities, field_name).last_probed_at = fresh_probe_at

    _seed_model_connection_record(
        session_factory,
        connection_id=9001,
        key="runtime_profile_tools_disabled",
        name="Provider Profile Fixture: Tools Disabled",
        description="Probe fixture with tool calls disabled.",
        base_url="https://runtime-profile-tools-disabled.example.test",
        model_id="fake-tools-disabled",
        protocol_profile="openai_chat_completions",
        capabilities=fresh_capabilities,
        last_probed_at=fresh_probe_at,
    )

    stale_capabilities = default_model_connection_capabilities("openai_responses")
    stale_capabilities.strict_json_schema_output.status = (
        ModelConnectionCapabilityStatus.UNSUPPORTED
    )
    stale_capabilities.strict_json_schema_output.detail = (
        "Provider profile fixture keeps strict schema unsupported."
    )
    for field_name in type(stale_capabilities).model_fields:
        getattr(stale_capabilities, field_name).last_probed_at = stale_probe_at

    _seed_model_connection_record(
        session_factory,
        connection_id=9002,
        key="runtime_profile_strict_schema_disabled",
        name="Provider Profile Fixture: Strict Schema Disabled",
        description="Probe fixture with strict schema disabled.",
        base_url="https://runtime-profile-strict-schema-disabled.example.test",
        model_id="fake-strict-schema-disabled",
        protocol_profile="openai_responses",
        capabilities=stale_capabilities,
        last_probed_at=stale_probe_at,
    )

    monkeypatch.setattr("app.services.model_connection_probe_service.utcnow", lambda: fixed_now)
    monkeypatch.setattr(
        "app.services.model_connection_probe_service.OpenAI",
        _CapabilityProbeOpenAIClient,
        raising=False,
    )

    cached_response = client.post("/api/model-connections/9001/capability-probe")
    assert cached_response.status_code == 200, cached_response.json()
    cached_body = cast(dict[str, object], cached_response.json())
    assert cached_body["modelConnectionId"] == 9001
    assert cached_body["cached"] is True
    requested_capability_keys = cast(list[str], cached_body["requestedCapabilityKeys"])
    assert len(requested_capability_keys) == len(ModelConnectionCapabilities.model_fields)
    assert set(requested_capability_keys) == _EXPECTED_MODEL_CONNECTION_CAPABILITY_KEYS
    assert (
        datetime.fromisoformat(cast(str, cached_body["lastProbedAt"]).replace("Z", "+00:00"))
        == fresh_probe_at
    )
    cached_capabilities = cast(dict[str, dict[str, object]], cached_body["capabilities"])
    assert set(cached_capabilities) == _EXPECTED_MODEL_CONNECTION_CAPABILITY_KEYS
    assert cached_capabilities["chatCompletions"]["status"] == "supported"
    assert cached_capabilities["responsesApi"]["status"] == "notApplicable"
    assert cached_capabilities["nativeToolCalls"]["status"] == "unsupported"
    assert cached_capabilities["reasoningHints"]["status"] == "unknown"
    assert cached_capabilities["strictJsonSchemaOutput"]["detail"] == (
        "Provider profile fixture keeps strict schema unsupported."
    )
    assert (
        datetime.fromisoformat(
            cast(str, cached_capabilities["nativeToolCalls"]["lastProbedAt"]).replace(
                "Z",
                "+00:00",
            )
        )
        == fresh_probe_at
    )
    assert _CapabilityProbeOpenAIClient.init_calls == []

    refreshed_response = client.post(
        "/api/model-connections/9001/capability-probe",
        json={"refresh": True},
    )
    assert refreshed_response.status_code == 200, refreshed_response.json()
    refreshed_body = cast(dict[str, object], refreshed_response.json())
    assert refreshed_body["cached"] is False
    assert (
        datetime.fromisoformat(cast(str, refreshed_body["lastProbedAt"]).replace("Z", "+00:00"))
        == fixed_now
    )
    refreshed_capabilities = cast(dict[str, dict[str, object]], refreshed_body["capabilities"])
    assert refreshed_capabilities["strictJsonSchemaOutput"]["status"] == "supported"
    assert refreshed_capabilities["jsonObjectOutput"]["status"] == "supported"
    assert refreshed_capabilities["nativeToolCalls"]["status"] == "unsupported"
    assert "tool calls disabled" in cast(str, refreshed_capabilities["nativeToolCalls"]["detail"])
    assert (
        datetime.fromisoformat(
            cast(str, refreshed_capabilities["strictJsonSchemaOutput"]["lastProbedAt"]).replace(
                "Z",
                "+00:00",
            )
        )
        == fixed_now
    )
    assert (
        datetime.fromisoformat(
            cast(str, refreshed_capabilities["nativeToolCalls"]["lastProbedAt"]).replace(
                "Z",
                "+00:00",
            )
        )
        == fixed_now
    )

    def _is_chat_json_object_probe_with_json_prompt(call: dict[str, object]) -> bool:
        response_format = call.get("response_format")
        return (
            isinstance(response_format, dict)
            and response_format.get("type") == "json_object"
            and _CapabilityProbeOpenAIClient._contains_json_word(call.get("messages"))
        )

    assert any("response_format" in call for call in _CapabilityProbeOpenAIClient.chat_calls)
    assert any(
        _is_chat_json_object_probe_with_json_prompt(call)
        for call in _CapabilityProbeOpenAIClient.chat_calls
    )
    assert any("tools" in call for call in _CapabilityProbeOpenAIClient.chat_calls)

    stale_response = client.post(
        "/api/model-connections/9002/capability-probe",
        json={
            "capabilityKeys": [
                "strictJsonSchemaOutput",
                "jsonObjectOutput",
                "nativeToolCalls",
            ]
        },
    )
    assert stale_response.status_code == 200, stale_response.json()
    stale_body = cast(dict[str, object], stale_response.json())
    assert stale_body["modelConnectionId"] == 9002
    assert stale_body["cached"] is False
    assert stale_body["requestedCapabilityKeys"] == [
        "strictJsonSchemaOutput",
        "jsonObjectOutput",
        "nativeToolCalls",
    ]
    assert (
        datetime.fromisoformat(cast(str, stale_body["lastProbedAt"]).replace("Z", "+00:00"))
        == fixed_now
    )
    stale_capabilities_body = cast(dict[str, dict[str, object]], stale_body["capabilities"])
    assert stale_capabilities_body["strictJsonSchemaOutput"]["status"] == "unsupported"
    assert "This response_format type is unavailable now" in cast(
        str,
        stale_capabilities_body["strictJsonSchemaOutput"]["detail"],
    )
    assert stale_capabilities_body["jsonObjectOutput"]["status"] == "supported"
    assert stale_capabilities_body["nativeToolCalls"]["status"] == "supported"

    def _is_responses_strict_schema_probe(call: dict[str, object]) -> bool:
        text = call.get("text")
        if not isinstance(text, dict):
            return False
        text_format = text.get("format")
        return isinstance(text_format, dict) and text_format.get("type") == "json_schema"

    def _is_responses_json_object_probe_with_json_prompt(call: dict[str, object]) -> bool:
        text = call.get("text")
        if not isinstance(text, dict):
            return False
        text_format = text.get("format")
        return (
            isinstance(text_format, dict)
            and text_format.get("type") == "json_object"
            and _CapabilityProbeOpenAIClient._contains_json_word(
                [call.get("instructions"), call.get("input")]
            )
        )

    assert any(
        _is_responses_strict_schema_probe(call)
        for call in _CapabilityProbeOpenAIClient.response_calls
    )
    assert any(
        _is_responses_json_object_probe_with_json_prompt(call)
        for call in _CapabilityProbeOpenAIClient.response_calls
    )
    assert any("tools" in call for call in _CapabilityProbeOpenAIClient.response_calls)
    assert (
        datetime.fromisoformat(
            cast(str, stale_capabilities_body["strictJsonSchemaOutput"]["lastProbedAt"]).replace(
                "Z",
                "+00:00",
            )
        )
        == fixed_now
    )


def test_model_connection_capability_probe_refresh_uses_literal_custom_root_request_path(
    client: TestClient,
) -> None:
    request_log: list[dict[str, object]] = []
    with run_fake_openai_provider(base_path="/codex/v1", request_log=request_log) as base_url:
        create_response = client.post(
            "/api/model-connections",
            json=_model_connection_create_payload(base_url),
        )
        assert create_response.status_code == 201, create_response.json()
        connection_id = int(create_response.json()["id"])

        probe_response = client.post(
            f"/api/model-connections/{connection_id}/capability-probe",
            json={"capabilityKeys": ["responsesApi"], "refresh": True},
        )
        assert probe_response.status_code == 200, probe_response.json()

    request_paths = [cast(str, entry["path"]) for entry in request_log]
    assert request_paths == ["/codex/v1/responses"]

    probe_body = cast(dict[str, object], probe_response.json())
    assert probe_body["cached"] is False
    assert probe_body["requestedCapabilityKeys"] == ["responsesApi"]


def test_model_connection_probe_refresh_passes_literal_trailing_slash_base_url(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _LiteralBaseUrlRecordingOpenAIClient.reset()
    monkeypatch.setattr(
        "app.services.model_connection_probe_service.OpenAI",
        _LiteralBaseUrlRecordingOpenAIClient,
        raising=False,
    )
    literal_base_url = "https://new.sharedchat.cc/codex/v1/"

    create_response = client.post(
        "/api/model-connections",
        json=_model_connection_create_payload(literal_base_url),
    )
    assert create_response.status_code == 201, create_response.json()
    connection_id = int(create_response.json()["id"])

    probe_response = client.post(
        f"/api/model-connections/{connection_id}/capability-probe",
        json={"capabilityKeys": ["responsesApi"], "refresh": True},
    )
    assert probe_response.status_code == 200, probe_response.json()
    assert probe_response.json()["cached"] is False

    assert _LiteralBaseUrlRecordingOpenAIClient.init_calls[-1]["base_url"] == literal_base_url


def test_model_connection_capability_probe_marks_transport_failures_inconclusive(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed_now = datetime(2026, 5, 12, 15, 10, tzinfo=UTC_TZ)

    class _InconclusiveProbeOpenAIClient:
        init_calls: list[dict[str, object]] = []

        class _Responses:
            @staticmethod
            def create(**kwargs: object) -> object:
                del kwargs
                raise RuntimeError("temporary transport outage")

        def __init__(self, **kwargs: object) -> None:
            self.init_calls.append(dict(kwargs))
            self.responses = self._Responses()

        def __enter__(self) -> _InconclusiveProbeOpenAIClient:
            return self

        def __exit__(self, exc_type: object, exc_value: object, exc_traceback: object) -> bool:
            return False

    _seed_model_connection_record(
        session_factory,
        connection_id=9003,
        key="runtime_profile_transport_inconclusive",
        name="Provider Profile Fixture: Transport Inconclusive",
        description="Probe fixture with an inconclusive transport failure.",
        base_url="https://runtime-profile-transport-inconclusive.example.test",
        model_id="fake-transport-inconclusive",
    )
    monkeypatch.setattr("app.services.model_connection_probe_service.utcnow", lambda: fixed_now)
    monkeypatch.setattr(
        "app.services.model_connection_probe_service.OpenAI",
        _InconclusiveProbeOpenAIClient,
        raising=False,
    )

    response = client.post(
        "/api/model-connections/9003/capability-probe",
        json={"capabilityKeys": ["strictJsonSchemaOutput"]},
    )

    assert response.status_code == 200, response.json()
    body = cast(dict[str, object], response.json())
    assert body["cached"] is False
    assert body["lastProbedAt"] == "2026-05-12T15:10:00Z"
    capabilities = cast(dict[str, dict[str, object]], body["capabilities"])
    strict_schema = capabilities["strictJsonSchemaOutput"]
    assert strict_schema["status"] == "unknown"
    assert "inconclusive" in cast(str, strict_schema["detail"])
    assert "temporary transport outage" in cast(str, strict_schema["detail"])
    assert strict_schema["lastProbedAt"] == "2026-05-12T15:10:00Z"


def test_model_connection_connection_test_requires_provider_api_key_without_openai(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed_now = datetime(2026, 5, 12, 15, 5, tzinfo=UTC_TZ)

    class _UnexpectedOpenAIClient:
        def __init__(self, **kwargs: object) -> None:
            raise AssertionError("OpenAI should not be used when the provider API key is missing")

    monkeypatch.setattr("app.services.model_connection_service.OpenAI", _UnexpectedOpenAIClient)
    monkeypatch.setattr("app.services.model_connection_service.utcnow", lambda: fixed_now)

    payload = {
        **_model_connection_create_payload(),
        "baseUrl": "https://provider.invalid/v1",
        "modelId": "provider-check",
        "protocolProfile": "openai_chat_completions",
    }
    payload.pop("apiKey")

    create_response = client.post("/api/model-connections", json=payload)
    assert create_response.status_code == 201, create_response.json()
    create_body = cast(dict[str, object], create_response.json())
    connection_id = cast(int, create_body["id"])

    test_response = client.post(f"/api/model-connections/{connection_id}/connection-test")
    assert test_response.status_code == 200, test_response.json()
    test_body = cast(dict[str, object], test_response.json())
    assert test_body["modelConnectionId"] == connection_id
    assert test_body["ok"] is False
    assert test_body["message"] == "API key is not configured."
    assert (
        datetime.fromisoformat(cast(str, test_body["lastTestedAt"]).replace("Z", "+00:00"))
        == fixed_now
    )

    get_response = client.get(f"/api/model-connections/{connection_id}")
    assert get_response.status_code == 200, get_response.json()
    get_body = cast(dict[str, object], get_response.json())
    assert get_body["lastTestOk"] is False
    assert get_body["lastTestMessage"] == "API key is not configured."
    assert (
        datetime.fromisoformat(cast(str, get_body["lastTestedAt"]).replace("Z", "+00:00"))
        == fixed_now
    )
