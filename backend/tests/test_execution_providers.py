from __future__ import annotations

import pytest

from app.services.execution_providers import (
    ExecutionProviderBundle,
    ExecutionProviderContribution,
    execution_provider_bundle_from_parts,
    merge_execution_provider_bundles,
)


class _ProviderPayload:
    pass


def test_execution_provider_bundle_stores_extension_keyed_payloads() -> None:
    payload = _ProviderPayload()

    bundle = execution_provider_bundle_from_parts(
        extension_key="example.extension",
        payload=payload,
    )

    assert bundle.payload_for("example.extension") is payload
    assert bundle.payload_for("missing.extension") is None


def test_merge_execution_provider_bundles_rejects_duplicate_extension_payloads() -> None:
    first = ExecutionProviderBundle(
        contributions=(
            ExecutionProviderContribution(extension_key="example.extension", payload=object()),
        )
    )
    second = ExecutionProviderBundle(
        contributions=(
            ExecutionProviderContribution(extension_key="example.extension", payload=object()),
        )
    )

    with pytest.raises(ValueError, match="Duplicate execution provider contribution"):
        _ = merge_execution_provider_bundles((first, second))


def test_execution_provider_bundle_contributions_are_ordered() -> None:
    first_payload = _ProviderPayload()
    second_payload = _ProviderPayload()

    bundle = merge_execution_provider_bundles(
        (
            execution_provider_bundle_from_parts(
                extension_key="example.first",
                payload=first_payload,
            ),
            execution_provider_bundle_from_parts(
                extension_key="example.second",
                payload=second_payload,
            ),
        )
    )

    assert [contribution.extension_key for contribution in bundle.contributions] == [
        "example.first",
        "example.second",
    ]
    assert bundle.payload_for("example.first") is first_payload
    assert bundle.payload_for("example.second") is second_payload
