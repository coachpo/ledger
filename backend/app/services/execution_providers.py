from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExecutionProviderContribution:
    extension_key: str
    payload: object

    def __post_init__(self) -> None:
        normalized_key = self.extension_key.strip()
        if not normalized_key:
            raise ValueError("Execution provider contribution requires an extension key.")
        object.__setattr__(self, "extension_key", normalized_key)


@dataclass(frozen=True, slots=True)
class ExecutionProviderBundle:
    contributions: tuple[ExecutionProviderContribution, ...] = ()

    def __post_init__(self) -> None:
        normalized = tuple(self.contributions)
        seen_keys: set[str] = set()
        for contribution in normalized:
            if contribution.extension_key in seen_keys:
                message = "Duplicate execution provider contribution for extension " + (
                    f"{contribution.extension_key!r}."
                )
                raise ValueError(message)
            seen_keys.add(contribution.extension_key)
        object.__setattr__(self, "contributions", normalized)

    def payload_for(self, extension_key: str) -> object | None:
        normalized_key = extension_key.strip()
        for contribution in self.contributions:
            if contribution.extension_key == normalized_key:
                return contribution.payload
        return None


def execution_provider_bundle_from_parts(
    *,
    extension_key: str,
    payload: object,
) -> ExecutionProviderBundle:
    return ExecutionProviderBundle(
        contributions=(ExecutionProviderContribution(extension_key=extension_key, payload=payload),)
    )


def merge_execution_provider_bundles(
    bundles: Iterable[ExecutionProviderBundle],
) -> ExecutionProviderBundle:
    contributions: list[ExecutionProviderContribution] = []
    for bundle in bundles:
        contributions.extend(bundle.contributions)
    return ExecutionProviderBundle(contributions=tuple(contributions))


__all__ = [
    "ExecutionProviderBundle",
    "ExecutionProviderContribution",
    "execution_provider_bundle_from_parts",
    "merge_execution_provider_bundles",
]
