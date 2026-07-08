from __future__ import annotations

from app.services.workflow_package_manifest_parser import parse_workflow_package_manifest
from tests.fixtures.workflow_manifests import base_manifest, base_manifest_data, dump_manifest


def test_base_manifest_fixture_round_trips_through_parser() -> None:
    source = base_manifest(package_key="fixture_roundtrip", model_connection="fixture_model")

    result = parse_workflow_package_manifest(source)

    assert result.diagnostics == []
    assert result.manifest is not None
    assert result.manifest.metadata.key == "fixture_roundtrip"
    assert result.manifest.spec.agents[0].model_connection == "fixture_model"

    data = base_manifest_data(package_key="fixture_roundtrip_copy")
    data["metadata"]["name"] = "Fixture Roundtrip Copy"

    copied = parse_workflow_package_manifest(dump_manifest(data))
    assert copied.diagnostics == []
    assert copied.manifest is not None
    assert copied.manifest.metadata.name == "Fixture Roundtrip Copy"
