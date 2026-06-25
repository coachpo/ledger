# pyright: reportImplicitStringConcatenation=false, reportUnnecessaryCast=false
from __future__ import annotations

from collections.abc import Callable, Mapping
from importlib import import_module
from pathlib import Path
from typing import cast

import pytest

from app.schemas.workflow_package_manifest import WorkflowPackageStepNode
from app.services.package_execution_plan_builder import PackageExecutionPlanBuilder
from app.services.workflow_package_manifest_compiler import compile_workflow_package_manifest
from app.services.workflow_package_manifest_parser import parse_workflow_package_manifest

_manifest_parser_module = import_module("tests.test_workflow_package_manifest_parser")
_valid_package_manifest_source = cast(
    Callable[[], str],
    _manifest_parser_module.__dict__["_valid_package_manifest_source"],
)
_MEMORY_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "workflow_packages"
    / "advisory_research_memory.yaml"
)


def _parse_manifest(source: str):
    result = parse_workflow_package_manifest(source)

    assert result.diagnostics == []
    assert result.manifest is not None
    return result.manifest


def _single_diagnostic(source: str):
    result = parse_workflow_package_manifest(source)

    assert result.manifest is None
    assert len(result.diagnostics) == 1
    return result.diagnostics[0]


def _valid_memory_config() -> str:
    return """    enabled: true
    retrieval:
      enabled: true
      namespaces: [research]
      maxItems: 5
      relevanceThreshold: 0.72
      includeKinds: [fact, observation, preference]
    writes:
      proposals: true
      allowedKinds: [fact, observation, preference]
      defaultDecision: commit
      autoCommitKinds: [fact]
    policy:
      secrets: quarantine
      sensitiveData: review
      expirationDays: 180
      unauthorized: reject
      consolidation: run_end
    checkpoints:
      enabled: true
      retention: run_lifecycle
"""


def test_manifest_memory_is_disabled_when_omitted() -> None:
    manifest = _parse_manifest(_valid_package_manifest_source())

    assert manifest.spec.memory is None
    assert manifest.spec.workflows[0].memory is None
    assert manifest.spec.agents[0].memory is None
    step = cast(WorkflowPackageStepNode, manifest.spec.workflows[0].flow)
    assert step.memory is None


def test_parse_manifest_accepts_spec_memory_config() -> None:
    source = _valid_package_manifest_source().replace(
        "  capabilityProfiles:\n",
        "  memory:\n" + _valid_memory_config() + "  capabilityProfiles:\n",
        1,
    )

    manifest = _parse_manifest(source)

    assert manifest.spec.memory is not None
    assert manifest.spec.memory.enabled is True
    assert manifest.spec.memory.retrieval is not None
    assert manifest.spec.memory.retrieval.namespaces == ["research"]
    assert manifest.spec.memory.retrieval.max_items == 5
    assert manifest.spec.memory.retrieval.relevance_threshold == 0.72
    assert manifest.spec.memory.retrieval.include_kinds == ["fact", "observation", "preference"]
    assert manifest.spec.memory.writes is not None
    assert manifest.spec.memory.writes.default_decision == "commit"
    assert manifest.spec.memory.writes.auto_commit_kinds == ["fact"]
    assert manifest.spec.memory.policy is not None
    assert manifest.spec.memory.policy.expiration_days == 180


def test_parse_manifest_accepts_workflow_memory_config() -> None:
    source = _valid_package_manifest_source().replace(
        """      inputSchema:
        type: object
        properties:
          ticker:
            type: string
      flow:
""",
        "      memory:\n"
        + _valid_memory_config().replace("    ", "        ")
        + """      inputSchema:
        type: object
        properties:
          ticker:
            type: string
      flow:
""",
        1,
    )

    manifest = _parse_manifest(source)
    workflow = manifest.spec.workflows[0]
    dumped = workflow.model_dump(mode="json", by_alias=True)

    assert workflow.memory is not None
    assert dumped["memory"] == {
        "enabled": True,
        "retrieval": {
            "enabled": True,
            "namespaces": ["research"],
            "maxItems": 5,
            "relevanceThreshold": 0.72,
            "includeKinds": ["fact", "observation", "preference"],
        },
        "writes": {
            "proposals": True,
            "allowedKinds": ["fact", "observation", "preference"],
            "defaultDecision": "commit",
            "autoCommitKinds": ["fact"],
        },
        "policy": {
            "secrets": "quarantine",
            "sensitiveData": "review",
            "expirationDays": 180,
            "unauthorized": "reject",
            "consolidation": "run_end",
        },
        "checkpoints": {"enabled": True, "retention": "run_lifecycle"},
    }


def test_parse_manifest_accepts_agent_memory_config() -> None:
    source = _valid_package_manifest_source().replace(
        "      inputSchema:\n",
        "      memory:\n"
        + _valid_memory_config().replace("    ", "        ")
        + "      inputSchema:\n",
        1,
    )

    manifest = _parse_manifest(source)

    agent = manifest.spec.agents[0]
    assert agent.memory is not None
    assert agent.memory.writes is not None
    assert agent.memory.writes.proposals is True
    assert agent.memory.writes.allowed_kinds == ["fact", "observation", "preference"]


def test_parse_manifest_accepts_step_memory_config() -> None:
    source = _valid_package_manifest_source().replace(
        "        with:\n",
        "        memory:\n"
        + _valid_memory_config().replace("    ", "          ")
        + "        with:\n",
        1,
    )

    manifest = _parse_manifest(source)

    step = cast(WorkflowPackageStepNode, manifest.spec.workflows[0].flow)
    assert step.memory is not None
    assert step.memory.checkpoints is not None
    assert step.memory.checkpoints.retention == "run_lifecycle"


@pytest.mark.parametrize(
    ("memory_field", "value", "expected_path"),
    [
        ("instructions", "Write these facts after every run.", "spec.memory.instructions"),
        ("systemPrompt", "You must remember everything.", "spec.memory.systemPrompt"),
        ("developerPrompt", "Store private reasoning.", "spec.memory.developerPrompt"),
        ("override", True, "spec.memory.override"),
        ("prompt", "Remember this instruction text.", "spec.memory.prompt"),
    ],
)
def test_parse_manifest_rejects_prompt_like_memory_fields(
    memory_field: str,
    value: object,
    expected_path: str,
) -> None:
    rendered = value if isinstance(value, bool) else f"{value!r}"
    source = _valid_package_manifest_source().replace(
        "  capabilityProfiles:\n",
        f"  memory:\n    {memory_field}: {rendered}\n  capabilityProfiles:\n",
        1,
    )

    diagnostic = _single_diagnostic(source)

    assert diagnostic.path == expected_path
    assert diagnostic.message == "Extra inputs are not permitted"


def test_parse_manifest_rejects_raw_memory_prompt_text() -> None:
    source = _valid_package_manifest_source().replace(
        "  capabilityProfiles:\n",
        "  memory: Remember all agent outputs.\n  capabilityProfiles:\n",
        1,
    )

    diagnostic = _single_diagnostic(source)

    assert diagnostic.path == "spec.memory"
    assert "Input should be a valid dictionary" in diagnostic.message


def test_parse_manifest_rejects_negative_memory_max_items() -> None:
    source = _valid_package_manifest_source().replace(
        "  capabilityProfiles:\n",
        "  memory:\n    retrieval:\n      maxItems: -1\n  capabilityProfiles:\n",
        1,
    )

    diagnostic = _single_diagnostic(source)

    assert diagnostic.path == "spec.memory.retrieval.maxItems"
    assert "greater than or equal to 0" in diagnostic.message


def test_parse_manifest_accepts_zero_memory_max_items() -> None:
    source = _valid_package_manifest_source().replace(
        "  capabilityProfiles:\n",
        "  memory:\n"
        "    retrieval:\n"
        "      enabled: true\n"
        "      maxItems: 0\n"
        "  capabilityProfiles:\n",
        1,
    )

    manifest = _parse_manifest(source)

    assert manifest.spec.memory is not None
    assert manifest.spec.memory.retrieval is not None
    assert manifest.spec.memory.retrieval.max_items == 0


def test_parse_manifest_rejects_out_of_bounds_memory_relevance_threshold() -> None:
    source = _valid_package_manifest_source().replace(
        "  capabilityProfiles:\n",
        "  memory:\n    retrieval:\n      relevanceThreshold: 1.5\n  capabilityProfiles:\n",
        1,
    )

    diagnostic = _single_diagnostic(source)

    assert diagnostic.path == "spec.memory.retrieval.relevanceThreshold"
    assert "less than or equal to 1" in diagnostic.message


@pytest.mark.parametrize(
    ("writes", "expected_message"),
    [
        (
            "allowedKinds: [fact]\n      defaultDecision: commit\n      autoCommitKinds: []",
            "commit memory policy requires at least one safe autoCommitKinds value",
        ),
        (
            "allowedKinds: [fact]\n"
            "      defaultDecision: commit\n"
            "      autoCommitKinds: [observation]",
            "autoCommitKinds must be included in allowedKinds",
        ),
        (
            "allowedKinds: [artifact]\n"
            "      defaultDecision: commit\n"
            "      autoCommitKinds: [artifact]",
            "autoCommitKinds contains values that are not safe for automatic commits",
        ),
    ],
)
def test_parse_manifest_rejects_unsafe_commit_memory_policy(
    writes: str,
    expected_message: str,
) -> None:
    source = _valid_package_manifest_source().replace(
        "  capabilityProfiles:\n",
        f"  memory:\n    writes:\n      {writes}\n  capabilityProfiles:\n",
        1,
    )

    diagnostic = _single_diagnostic(source)

    assert diagnostic.path == "spec.memory.writes"
    assert expected_message in diagnostic.message


@pytest.mark.parametrize(
    ("field", "expected_path"),
    [
        ("apiKey", "spec.memory.retrieval.apiKey"),
        ("secret", "spec.memory.retrieval.secret"),
        ("password", "spec.memory.retrieval.password"),
    ],
)
def test_parse_manifest_rejects_secret_like_memory_static_config(
    field: str,
    expected_path: str,
) -> None:
    source = _valid_package_manifest_source().replace(
        "  capabilityProfiles:\n",
        "  memory:\n"
        "    retrieval:\n"
        "      enabled: true\n"
        f"      {field}: raw-secret\n"
        "  capabilityProfiles:\n",
        1,
    )

    diagnostic = _single_diagnostic(source)

    assert diagnostic.path == expected_path
    assert diagnostic.message == f"{field} is not allowed in workflow package manifests"


def test_parse_manifest_allows_review_memory_write_policy_without_auto_commit_kinds() -> None:
    source = _valid_package_manifest_source().replace(
        "  capabilityProfiles:\n",
        "  memory:\n    writes:\n      defaultDecision: review\n  capabilityProfiles:\n",
        1,
    )

    manifest = _parse_manifest(source)

    assert manifest.spec.memory is not None
    assert manifest.spec.memory.writes is not None
    assert manifest.spec.memory.writes.default_decision == "review"
    assert manifest.spec.memory.writes.auto_commit_kinds == []


@pytest.mark.parametrize(
    ("memory", "expected_path"),
    [
        ("retrieval:\n      kinds: [fact]", "spec.memory.retrieval.kinds"),
        ("writes:\n      enabled: true", "spec.memory.writes.enabled"),
        ("writes:\n      kinds: [fact]", "spec.memory.writes.kinds"),
        ("checkpoints:\n      on: [workflowComplete]", "spec.memory.checkpoints.on"),
    ],
)
def test_parse_manifest_rejects_off_plan_memory_aliases(
    memory: str,
    expected_path: str,
) -> None:
    source = _valid_package_manifest_source().replace(
        "  capabilityProfiles:\n",
        f"  memory:\n    {memory}\n  capabilityProfiles:\n",
        1,
    )

    diagnostic = _single_diagnostic(source)

    assert diagnostic.path == expected_path
    assert diagnostic.message == "Extra inputs are not permitted"


def test_memory_dump_keeps_external_camel_case_contract() -> None:
    manifest = _parse_manifest(
        _valid_package_manifest_source().replace(
            "  capabilityProfiles:\n",
            "  memory:\n" + _valid_memory_config() + "  capabilityProfiles:\n",
            1,
        )
    )
    dumped = manifest.model_dump(mode="json", by_alias=True)
    spec = cast(Mapping[str, object], dumped["spec"])
    memory = cast(Mapping[str, object], spec["memory"])
    retrieval = cast(Mapping[str, object], memory["retrieval"])
    writes = cast(Mapping[str, object], memory["writes"])
    policy = cast(Mapping[str, object], memory["policy"])

    assert set(retrieval) == {
        "enabled",
        "namespaces",
        "maxItems",
        "relevanceThreshold",
        "includeKinds",
    }
    assert set(writes) == {"proposals", "allowedKinds", "defaultDecision", "autoCommitKinds"}
    assert set(policy) == {
        "secrets",
        "sensitiveData",
        "expirationDays",
        "unauthorized",
        "consolidation",
    }


def test_compile_manifest_omitted_memory_resolves_disabled_policy() -> None:
    compiled = compile_workflow_package_manifest(_valid_package_manifest_source())
    compiled_plan = cast(dict[str, object], compiled["compiledPlan"])
    workflow = cast(list[dict[str, object]], compiled_plan["workflows"])[0]
    step = cast(list[dict[str, object]], workflow["steps"])[0]
    agent = cast(list[dict[str, object]], step["agents"])[0]

    disabled_policy = {
        "enabled": False,
        "retrieval": None,
        "writes": None,
        "policy": None,
        "checkpoints": None,
    }
    assert compiled_plan["memoryPolicy"] == disabled_policy
    assert workflow["memoryPolicy"] == disabled_policy
    assert agent["memoryPolicy"] == disabled_policy


def test_compile_manifest_resolves_memory_precedence_into_step_policy() -> None:
    source = _valid_package_manifest_source().replace(
        "  capabilityProfiles:\n",
        """  memory:
    enabled: true
    retrieval:
      enabled: true
      namespaces: [spec_ns]
      maxItems: 3
      includeKinds: [fact]
    writes:
      proposals: true
      allowedKinds: [fact, observation]
      defaultDecision: review
    policy:
      secrets: quarantine
      sensitiveData: review
      expirationDays: 365
      unauthorized: reject
      consolidation: disabled
    checkpoints:
      enabled: true
      retention: run_lifecycle
  capabilityProfiles:
""",
        1,
    )
    source = source.replace(
        "      inputSchema:\n",
        """      memory:
        retrieval:
          namespaces: [agent_ns]
          maxItems: 7
        writes:
          allowedKinds: [preference]
      inputSchema:
""",
        1,
    )
    source = source.replace(
        "      inputSchema:\n"
        "        type: object\n"
        "        properties:\n"
        "          ticker:\n"
        "            type: string\n"
        "      flow:\n",
        """      memory:
        retrieval:
          relevanceThreshold: 0.6
        policy:
          sensitiveData: quarantine
          expirationDays: 30
          unauthorized: reject
          consolidation: run_end
      inputSchema:
        type: object
        properties:
          ticker:
            type: string
      flow:
""",
        1,
    )
    source = source.replace(
        "        with:\n",
        """        memory:
          retrieval:
            maxItems: 0
          writes:
            proposals: true
            allowedKinds: [fact, preference]
            defaultDecision: commit
            autoCommitKinds: [fact]
          checkpoints:
            enabled: false
            retention: none
        with:
""",
        1,
    )

    compiled = compile_workflow_package_manifest(source)
    compiled_plan = cast(dict[str, object], compiled["compiledPlan"])
    workflow = cast(list[dict[str, object]], compiled_plan["workflows"])[0]
    step = cast(list[dict[str, object]], workflow["steps"])[0]
    agent = cast(list[dict[str, object]], step["agents"])[0]
    policy = cast(dict[str, object], agent["memoryPolicy"])

    assert policy["enabled"] is True
    assert policy["retrieval"] == {
        "enabled": True,
        "namespaces": ["agent_ns"],
        "maxItems": 0,
        "relevanceThreshold": 0.6,
        "includeKinds": ["fact"],
    }
    assert policy["writes"] == {
        "proposals": True,
        "allowedKinds": ["fact", "preference"],
        "defaultDecision": "commit",
        "autoCommitKinds": ["fact"],
    }
    assert policy["policy"] == {
        "secrets": "quarantine",
        "sensitiveData": "quarantine",
        "expirationDays": 30,
        "unauthorized": "reject",
        "consolidation": "run_end",
    }
    assert policy["checkpoints"] is None
    assert cast(dict[str, object], workflow["memoryPolicy"])["policy"] == {
        "secrets": "quarantine",
        "sensitiveData": "quarantine",
        "expirationDays": 30,
        "unauthorized": "reject",
        "consolidation": "run_end",
    }

    execution_plan = PackageExecutionPlanBuilder.build_from_compiled_plan(
        cast(dict[str, object], compiled_plan),
        "daily_research",
    )
    runtime_policy = execution_plan.steps[0].agents[0].memory_policy
    assert runtime_policy.enabled is True
    assert runtime_policy.retrieval is not None
    assert runtime_policy.retrieval.max_items == 0
    assert runtime_policy.writes is not None
    assert runtime_policy.writes.default_decision == "commit"
    assert runtime_policy.checkpoints is None


def test_memory_fixture_preserves_yaml_and_runtime_memory_contract() -> None:
    source = _MEMORY_FIXTURE.read_text()

    manifest = _parse_manifest(source)
    compiled = compile_workflow_package_manifest(manifest)
    compiled_plan = cast(dict[str, object], compiled["compiledPlan"])
    workflow = cast(list[dict[str, object]], compiled_plan["workflows"])[0]
    step = cast(list[dict[str, object]], workflow["steps"])[0]
    agent = cast(list[dict[str, object]], step["agents"])[0]
    policy = cast(dict[str, object], agent["memoryPolicy"])

    assert policy["retrieval"] == {
        "enabled": True,
        "namespaces": ["advisory_research"],
        "maxItems": 4,
        "relevanceThreshold": 0.7,
        "includeKinds": ["fact", "observation", "preference"],
    }
    assert policy["policy"] == {
        "secrets": "quarantine",
        "sensitiveData": "review",
        "expirationDays": 180,
        "unauthorized": "reject",
        "consolidation": "run_end",
    }

    execution_plan = PackageExecutionPlanBuilder.build_from_compiled_plan(
        compiled_plan,
        "advisory_research",
    )
    runtime_policy = execution_plan.steps[0].agents[0].memory_policy
    assert runtime_policy.retrieval is not None
    assert runtime_policy.retrieval.relevance_threshold == 0.7
    assert runtime_policy.policy is not None
    assert runtime_policy.policy.consolidation == "run_end"


@pytest.mark.parametrize(
    ("memory", "expected_path"),
    [
        ("owner: local_user", "spec.memory.owner"),
        ("ownerType: local_user", "spec.memory.ownerType"),
        ("ownerId: default", "spec.memory.ownerId"),
        ("retrieval:\n      ownerId: default", "spec.memory.retrieval.ownerId"),
        ("policy:\n      ownership: platform", "spec.memory.policy.ownership"),
    ],
)
def test_parse_manifest_rejects_memory_ownership_config(
    memory: str,
    expected_path: str,
) -> None:
    source = _valid_package_manifest_source().replace(
        "  capabilityProfiles:\n",
        f"  memory:\n    {memory}\n  capabilityProfiles:\n",
        1,
    )

    diagnostic = _single_diagnostic(source)

    assert diagnostic.path == expected_path
    assert diagnostic.message == "Extra inputs are not permitted"
