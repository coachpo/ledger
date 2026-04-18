from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.agent_spec import AgentSpec
from app.models.capability_registry_entry import CapabilityRegistryEntry
from app.models.persona_profile import PersonaProfile
from app.models.workflow_spec import WorkflowSpec
from app.services.runtime_seed_bootstrap import (
    RuntimeSeedBootstrapDriftError,
    bootstrap_runtime_seed_mirrors,
)
from app.services.runtime_seed_catalog import (
    SEEDED_AGENT_SPECS,
    SEEDED_BUILTIN_SPECS,
    SEEDED_CAPABILITY_BUNDLE_SPECS,
    SEEDED_CONNECTOR_SPECS,
    SEEDED_TOOL_SPECS,
)


def test_runtime_seed_bootstrap_materializes_seeded_runtime_mirrors(session_factory) -> None:
    with session_factory() as session:
        workflows = {
            workflow.key: workflow
            for workflow in session.scalars(
                select(WorkflowSpec)
                .where(WorkflowSpec.origin == "seeded")
                .order_by(WorkflowSpec.key, WorkflowSpec.version)
            )
        }
        agents = {
            agent.key: agent
            for agent in session.scalars(
                select(AgentSpec)
                .where(AgentSpec.origin == "seeded")
                .order_by(AgentSpec.key, AgentSpec.version)
            )
        }
        personas = {
            persona.key: persona
            for persona in session.scalars(
                select(PersonaProfile)
                .where(PersonaProfile.origin == "seeded")
                .order_by(PersonaProfile.key, PersonaProfile.version)
            )
        }
        capabilities = {
            entry.key: entry
            for entry in session.scalars(
                select(CapabilityRegistryEntry)
                .where(CapabilityRegistryEntry.origin == "seeded")
                .order_by(CapabilityRegistryEntry.key, CapabilityRegistryEntry.version)
            )
        }

        assert workflows == {}

        assert set(agents) == {agent.key for agent in SEEDED_AGENT_SPECS}
        for seeded_agent in SEEDED_AGENT_SPECS:
            agent = agents[seeded_agent.key]
            assert agent.version == 1
            assert agent.origin == "seeded"
            assert agent.status == "ACTIVE"
            assert agent.name == seeded_agent.role
            assert agent.instructions == seeded_agent.system_prompt
            assert agent.model_policy == {}
            assert agent.final_output_contract is None
            assert agent.default_capability_bundle_keys == []
            assert agent.default_persona_profile_keys == []

        assert set(personas) == {builtin.canonical_target_id for builtin in SEEDED_BUILTIN_SPECS}
        for builtin in SEEDED_BUILTIN_SPECS:
            persona = personas[builtin.canonical_target_id]
            assert persona.version == 1
            assert persona.origin == "seeded"
            assert persona.status == "ACTIVE"
            assert persona.kind == "builtin_profile"
            assert persona.display_name == builtin.display_name
            assert persona.enabled is True
            assert persona.handle == builtin.handle
            assert persona.canonical_target_id == builtin.canonical_target_id
            assert persona.parent_profile_key is None
            assert persona.parent_profile_version is None
            assert persona.legacy_source_version == builtin.revision
            assert persona.system_prompt_fragment == builtin.description
            assert persona.prompt_append_fragment == ""
            assert persona.default_capability_bundle_keys == list(builtin.capability_bundle_keys)

        assert set(capabilities) == {
            *(tool.tool_id for tool in SEEDED_TOOL_SPECS),
            *(bundle.bundle_key for bundle in SEEDED_CAPABILITY_BUNDLE_SPECS),
            *(connector.connector_id for connector in SEEDED_CONNECTOR_SPECS),
        }

        report_lookup = capabilities["ledger.report_lookup"]
        assert report_lookup.version == 1
        assert report_lookup.type == "tool"
        assert report_lookup.approval_mode == "not_required"
        assert report_lookup.adapter_key == "ledger.report_lookup"
        assert report_lookup.config_schema == {
            "type": "object",
            "properties": {"slug": {"type": "string"}},
            "required": ["slug"],
            "additionalProperties": False,
        }
        assert report_lookup.bundle_members is None
        assert report_lookup.transport is None
        assert report_lookup.lifecycle is None

        orchestration_lookup = capabilities["ledger.orchestration_catalog_lookup"]
        assert orchestration_lookup.type == "tool"
        assert orchestration_lookup.approval_mode == "not_required"
        assert orchestration_lookup.config_schema == {
            "type": "object",
            "properties": {"handle": {"type": "string"}},
            "additionalProperties": False,
        }

        cycle_context_lookup = capabilities["ledger.cycle_context_lookup"]
        assert cycle_context_lookup.type == "tool"
        assert cycle_context_lookup.approval_mode == "not_required"
        assert cycle_context_lookup.config_schema == {
            "type": "object",
            "properties": {
                "artifact_key": {
                    "type": "string",
                    "enum": [
                        "prompt_report_slug",
                        "prompt_report",
                        "authored_entry_prompt_body",
                        "compiled_entry_prompt_body",
                        "execution_context_body",
                        "full_user_prompt",
                        "resolved_mentions",
                        "mentioned_target_outputs",
                        "mentioned_target_output_ids",
                    ],
                }
            },
            "required": ["artifact_key"],
            "additionalProperties": False,
        }

        librarian_bundle = capabilities["builtin.librarian_context"]
        assert librarian_bundle.type == "bundle"
        assert librarian_bundle.approval_mode == "not_required"
        assert librarian_bundle.adapter_key is None
        assert librarian_bundle.config_schema is None
        assert librarian_bundle.bundle_members == [
            {"key": "ledger.report_lookup", "type": "tool", "version": 1},
            {"key": "ledger.orchestration_catalog_lookup", "type": "tool", "version": 1},
        ]
        assert librarian_bundle.transport is None
        assert librarian_bundle.lifecycle is None

        explore_bundle = capabilities["builtin.explore_context"]
        assert explore_bundle.type == "bundle"
        assert explore_bundle.bundle_members == [
            {"key": "ledger.orchestration_catalog_lookup", "type": "tool", "version": 1},
            {"key": "ledger.cycle_context_lookup", "type": "tool", "version": 1},
        ]

        market_data = capabilities["ledger.mcp.market_data"]
        assert market_data.type == "connector"
        assert market_data.approval_mode == "required"
        assert market_data.adapter_key == "ledger.mcp.market_data"
        assert market_data.config_schema == {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
            "additionalProperties": False,
        }
        assert market_data.bundle_members is None
        assert market_data.transport == "mcp"
        assert market_data.lifecycle == "placeholder"

        company_filings = capabilities["ledger.mcp.company_filings"]
        assert company_filings.type == "connector"
        assert company_filings.approval_mode == "required"
        assert company_filings.transport == "mcp"
        assert company_filings.lifecycle == "placeholder"


def test_runtime_seed_bootstrap_is_idempotent_on_repeat_calls(session_factory) -> None:
    with session_factory() as session:
        result = bootstrap_runtime_seed_mirrors(session)
        session.commit()

        workflow_count = len(
            session.scalars(select(WorkflowSpec).where(WorkflowSpec.origin == "seeded")).all()
        )
        agent_count = len(
            session.scalars(select(AgentSpec).where(AgentSpec.origin == "seeded")).all()
        )
        persona_count = len(
            session.scalars(select(PersonaProfile).where(PersonaProfile.origin == "seeded")).all()
        )
        capability_count = len(
            session.scalars(
                select(CapabilityRegistryEntry).where(CapabilityRegistryEntry.origin == "seeded")
            ).all()
        )

        assert result.total_inserted == 0
        assert result.workflow_specs_inserted == 0
        assert result.agent_specs_inserted == 0
        assert result.persona_profiles_inserted == 0
        assert result.capability_registry_entries_inserted == 0
        assert workflow_count == 0
        assert agent_count == len(SEEDED_AGENT_SPECS)
        assert persona_count == len(SEEDED_BUILTIN_SPECS)
        assert capability_count == (
            len(SEEDED_TOOL_SPECS)
            + len(SEEDED_CAPABILITY_BUNDLE_SPECS)
            + len(SEEDED_CONNECTOR_SPECS)
        )


def test_runtime_seed_bootstrap_drift_is_rejected_for_unexpected_seeded_history_row(
    session_factory,
) -> None:
    with session_factory() as session:
        seed_agent = session.scalar(
            select(AgentSpec).where(
                AgentSpec.key == "position_analyst",
                AgentSpec.version == 1,
                AgentSpec.origin == "seeded",
            )
        )
        assert seed_agent is not None
        session.add(
            AgentSpec(
                key=seed_agent.key,
                version=2,
                origin="seeded",
                status="DEPRECATED",
                name=seed_agent.name,
                instructions=seed_agent.instructions,
                model_policy=seed_agent.model_policy,
                final_output_contract=seed_agent.final_output_contract,
                default_capability_bundle_keys=seed_agent.default_capability_bundle_keys,
                default_persona_profile_keys=seed_agent.default_persona_profile_keys,
            )
        )
        session.commit()

    with session_factory() as session:
        with pytest.raises(
            RuntimeSeedBootstrapDriftError,
            match=(
                r"Seed drift detected for agent_specs: unexpected seeded rows "
                r'\[\{"key":"position_analyst","version":2\}\]'
            ),
        ):
            bootstrap_runtime_seed_mirrors(session)
