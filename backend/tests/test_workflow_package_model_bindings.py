# pyright: reportPrivateUsage=false

from __future__ import annotations

import json
from dataclasses import asdict
from typing import cast

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import ApiError
from app.models.model_connection import ModelConnection
from app.repositories.workflow_package import WorkflowPackageRepository
from app.services.model_connection_service import ModelConnectionService
from app.services.workflow_package_manifest_compiler import (
    WorkflowPackageManifestCompilerError,
    compile_workflow_package_manifest,
)
from app.services.workflow_package_manifest_decompiler import decompile_workflow_package_manifest
from tests.test_workflow_package_manifest_parser import _valid_package_manifest_source


def test_unknown_tool_key_is_package_diagnostic() -> None:
    source = _valid_package_manifest_source().replace(
        "signaldeck.market_data.quote_lookup",
        "signaldeck.stock_analysis.report_lookup",
        1,
    )
    with pytest.raises(WorkflowPackageManifestCompilerError) as excinfo:
        _ = compile_workflow_package_manifest(source)

    assert any(
        diagnostic.path == "spec.capabilityProfiles.market_research_tools.toolKeys[0]"
        and "Unknown server-declared tool 'signaldeck.stock_analysis.report_lookup'"
        in diagnostic.message
        for diagnostic in excinfo.value.diagnostics
    )


def test_package_export_contains_model_key_not_secret_or_id(
    session_factory: sessionmaker[Session],
) -> None:
    secret_value = "sk-package-secret-1234"
    source = _valid_package_manifest_source()
    compiled = compile_workflow_package_manifest(source)

    with session_factory() as session:
        connection = ModelConnection(
            key="tradingagents_primary_model",
            status="active",
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
        package = repository.create_package(
            key="tradingagents_research",
            name="TradingAgents Research Package",
            description="Portable package for the representative research workflow.",
            draft_source=source,
        )
        package_definition = cast(dict[str, object], compiled["packageDefinition"])
        compiled_plan = cast(dict[str, object], compiled["compiledPlan"])
        version = repository.create_version(
            package,
            manifest_source=source,
            manifest_hash=cast(str, compiled["manifestHash"]),
            package_definition=package_definition,
            compiled_plan=compiled_plan,
            compiled_hash=cast(str, compiled["compiledHash"]),
            validation_summary={"diagnostics": []},
        )
        binding = ModelConnectionService(session).resolve_package_model_connection_binding(
            "tradingagents_primary_model",
            path="spec.agents[0].modelConnection",
            require_api_key=True,
        )
        session.commit()
        package_payload = {
            "packageDefinition": version.package_definition,
            "compiledPlan": version.compiled_plan,
        }

    roundtrip = decompile_workflow_package_manifest(package_payload)
    binding_payload = asdict(binding)
    serialized_package = json.dumps(
        {
            "packageDefinition": package_payload["packageDefinition"],
            "compiledPlan": package_payload["compiledPlan"],
            "source": roundtrip.source,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    assert "modelConnection: tradingagents_primary_model" in roundtrip.source
    assert '"modelConnection":"tradingagents_primary_model"' in serialized_package
    assert binding_payload["key"] == "tradingagents_primary_model"
    assert binding_payload["has_api_key"] is True
    assert "id" not in binding_payload
    for forbidden in (
        "modelConnectionId",
        "secretPayload",
        "apiKey",
        "__encrypted__",
        "ciphertext",
        secret_value,
    ):
        assert forbidden not in serialized_package
        assert forbidden not in json.dumps(binding_payload, sort_keys=True)


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
    assert excinfo.value.details == [
        {
            "field": "spec.agents[0].modelConnection",
            "issue": "Model connection 'missing_model' was not found",
        }
    ]
