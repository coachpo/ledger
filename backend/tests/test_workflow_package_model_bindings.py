# pyright: reportPrivateUsage=false

from __future__ import annotations

from dataclasses import asdict
from typing import cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.models.model_connection import ModelConnection
from app.repositories.workflow_package import WorkflowPackageRepository
from app.schemas.model_connection import (
    ModelConnectionProtocolProfile,
    default_model_connection_capabilities,
    dump_model_connection_capabilities,
)
from app.services.model_connection_service import ModelConnectionService
from app.services.workflow_package_manifest_compiler import (
    WorkflowPackageManifestCompilerError,
    compile_workflow_package_manifest,
)
from tests.fixtures.workflow_manifests import dump_manifest, tradingagents_research_manifest_data
from tests.test_workflow_package_manifest_parser import _valid_package_manifest_source


def test_unknown_tool_key_is_package_diagnostic() -> None:
    source = _valid_package_manifest_source().replace(
        "signaldeck.finance.market_data.quote_lookup",
        "signaldeck.stock_analysis.report_lookup",
        1,
    )
    with pytest.raises(WorkflowPackageManifestCompilerError) as excinfo:
        _ = compile_workflow_package_manifest(source)

    assert excinfo.value.diagnostics


def test_package_export_uses_model_key_and_binding_summary(
    session_factory: sessionmaker[Session],
) -> None:
    secret_value = "sk-package-secret-1234"
    source = _valid_package_manifest_source()
    compiled = compile_workflow_package_manifest(source)

    with session_factory() as session:
        connection = ModelConnection(
            key="tradingagents_primary_model",
            name="TradingAgents Primary Model",
            description="Live global connection for package binding tests.",
            base_url="https://api.openai.com/v1",
            model_id="gpt-5.4-mini",
            reasoning_effort="medium",
            api_style="responses",
            timeout_seconds=60,
            secret_payload={"apiKey": secret_value},
        )
        session.add(connection)
        repository = WorkflowPackageRepository(session)
        package_definition = cast(dict[str, object], compiled["packageDefinition"])
        compiled_plan = cast(dict[str, object], compiled["compiledPlan"])
        session.flush()
        repository.create_package(
            key="tradingagents_research",
            name="TradingAgents Research Package",
            description="Portable package for the representative research workflow.",
            manifest_source=source,
            manifest_hash=cast(str, compiled["manifestHash"]),
            package_definition=package_definition,
            compiled_plan=compiled_plan,
            compiled_hash=cast(str, compiled["compiledHash"]),
        )
        binding = ModelConnectionService(session).resolve_package_model_connection_binding(
            "tradingagents_primary_model",
            path="spec.agents[0].modelConnection",
            require_api_key=True,
        )
        session.commit()
    binding_payload = asdict(binding)
    spec = cast(dict[str, object], cast(dict[str, object], compiled["packageDefinition"])["spec"])
    compiled_agent = cast(list[dict[str, object]], spec["agents"])[0]

    assert "modelConnection: tradingagents_primary_model" in source
    assert compiled_agent["modelConnection"] == "tradingagents_primary_model"
    assert set(binding_payload) == {
        "key",
        "name",
        "protocol_profile",
        "base_url",
        "model_id",
        "reasoning_effort",
        "capabilities",
        "output_strategy_policy",
        "parallel_tool_calls_policy",
        "reasoning_policy",
        "streaming_policy",
        "probe_cache_ttl_seconds",
        "api_style",
        "timeout_seconds",
        "has_api_key",
    }
    assert binding_payload["key"] == "tradingagents_primary_model"
    assert binding_payload["model_id"] == "gpt-5.4-mini"
    assert binding_payload["has_api_key"] is True


def test_package_model_connection_preflight_blocks_missing_key(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        service = ModelConnectionService(session)

        assert service.lookup_package_model_connection_binding("missing_model") is None
        with pytest.raises(ApiError) as excinfo:
            _ = service.resolve_package_model_connection_binding(
                "missing_model",
                path="spec.agents[0].modelConnection",
            )

    assert excinfo.value.code == "validation_error"
    assert excinfo.value.details


def _seed_tradingagents_connection(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        session.add(
            ModelConnection(
                key="tradingagents_primary_model",
                name="TradingAgents Primary Model",
                description="Live global connection for model-binding launch test.",
                base_url="https://api.openai.com/v1",
                model_id="gpt-5.4-mini",
                protocol_profile=ModelConnectionProtocolProfile.OPENAI_RESPONSES.value,
                capabilities=dump_model_connection_capabilities(
                    default_model_connection_capabilities(
                        ModelConnectionProtocolProfile.OPENAI_RESPONSES
                    )
                ),
                output_strategy_policy="prefer_strict_schema",
                parallel_tool_calls_policy="serialize",
                reasoning_policy="allow",
                streaming_policy="allow",
                probe_cache_ttl_seconds=900,
                timeout_seconds=60,
                secret_payload={"apiKey": "sk-live-key"},
            )
        )
        session.commit()


def _launch_ready_package_manifest_source() -> str:
    data = tradingagents_research_manifest_data()
    data["spec"]["mcpServers"] = []
    data["spec"]["agents"][0]["mcpServers"] = []
    return dump_manifest(data)


def test_launch_and_preflight_expose_resolved_model_connections(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    source = _launch_ready_package_manifest_source()
    _seed_tradingagents_connection(session_factory)

    create_response = client.post("/api/workflow-packages", json={"manifestSource": source})
    assert create_response.status_code == 201, create_response.json()

    package = cast(dict[str, object], create_response.json())
    package_id = cast(int, package["id"])

    preflight = client.post(
        f"/api/workflow-packages/{package_id}/preflight",
        json={"workflowKey": "daily_research", "parameters": {"ticker": "AAPL"}},
    )

    assert preflight.status_code == 200, preflight.json()
    preflight_body = cast(dict[str, object], preflight.json())
    launch = client.get(
        f"/api/workflow-packages/{package_id}/launch",
        params={"workflowKey": "daily_research"},
    )

    assert launch.status_code == 200, launch.json()
    launch_body = cast(dict[str, object], launch.json())

    expected_profile = {
        "key": "tradingagents_primary_model",
        "name": "TradingAgents Primary Model",
        "protocolProfile": "openai_responses",
        "baseUrl": "https://api.openai.com/v1",
        "modelId": "gpt-5.4-mini",
        "reasoningEffort": "medium",
        "capabilities": dump_model_connection_capabilities(
            default_model_connection_capabilities(ModelConnectionProtocolProfile.OPENAI_RESPONSES)
        ),
        "outputStrategyPolicy": "prefer_strict_schema",
        "parallelToolCallsPolicy": "serialize",
        "reasoningPolicy": "allow",
        "streamingPolicy": "allow",
        "probeCacheTtlSeconds": 900,
        "apiStyle": "responses",
        "timeoutSeconds": 60,
        "hasApiKey": True,
    }

    for body in (preflight_body, launch_body):
        connections = cast(list[dict[str, object]], body["resolvedModelConnections"])
        assert connections == [expected_profile]
        assert "apiKey" not in connections[0]
        assert "secretPayload" not in connections[0]

    assert preflight_body["ready"] is True, preflight_body
    assert launch_body["ready"] is True, launch_body
