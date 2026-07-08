from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from io import StringIO
from typing import Any, cast

from ruamel.yaml import YAML

ManifestNode = dict[str, Any]

_BASE_MANIFEST = """apiVersion: signaldeck.workflowPackage/v1
kind: WorkflowPackage
metadata:
  key: runtime_package
  name: Runtime Package
  description: Runtime package fixture.
spec:
  inputs:
    type: object
    properties:
      ticker:
        type: string
    required: [ticker]
  capabilityProfiles: []
  outputSchemas:
    - key: summary_output
      name: Summary Output
      jsonSchema:
        type: object
        properties:
          summary:
            type: string
        required: [summary]
  agents:
    - key: package_analyst
      name: Package Analyst
      modelConnection: package_runtime_model
      systemPrompt: Return a short JSON summary.
      inputSchema:
        type: object
        properties:
          ticker:
            type: string
        required: [ticker]
      outputSchema: summary_output
      capabilityProfiles: []
  workflows:
    - key: runtime_workflow
      name: Runtime Workflow
      inputSchema:
        type: object
        properties:
          ticker:
            type: string
        required: [ticker]
      flow:
        kind: step
        id: package_analysis
        slot: analysis
        uses: package_analyst
        with:
          ticker: ${{ inputs.ticker }}
      output:
        from: ${{ nodes.package_analysis.outputs.analysis }}
"""


def _yaml() -> YAML:
    yaml = YAML(typ="rt")
    yaml.default_flow_style = False
    yaml.representer.ignore_aliases = lambda _data: True
    yaml.width = 4096
    return yaml


def _load_base_manifest() -> ManifestNode:
    manifest = _yaml().load(_BASE_MANIFEST)
    return cast(ManifestNode, manifest)


def dump_manifest(manifest: ManifestNode) -> str:
    stream = StringIO()
    _yaml().dump(manifest, stream)
    return stream.getvalue()


def base_manifest_data(
    *,
    package_key: str = "runtime_package",
    package_name: str = "Runtime Package",
    package_description: str | None = "Runtime package fixture.",
    input_schema: ManifestNode | None = None,
    capability_profiles: list[ManifestNode] | None = None,
    tool_keys: Sequence[str] | None = None,
    tool_profile_key: str = "package_tools",
    tool_profile_name: str = "Package Tools",
    output_schemas: list[ManifestNode] | None = None,
    mcp_servers: list[ManifestNode] | None = None,
    agents: list[ManifestNode] | None = None,
    agent_key: str = "package_analyst",
    agent_name: str = "Package Analyst",
    agent_description: str | None = None,
    model_connection: str = "package_runtime_model",
    system_prompt: str = "Return a short JSON summary.",
    output_schema_key: str = "summary_output",
    workflows: list[ManifestNode] | None = None,
    workflow_key: str = "runtime_workflow",
    workflow_name: str = "Runtime Workflow",
    workflow_description: str | None = None,
    flow: ManifestNode | None = None,
    workflow_output: ManifestNode | None = None,
) -> ManifestNode:
    manifest = _load_base_manifest()
    metadata = cast(ManifestNode, manifest["metadata"])
    spec = cast(ManifestNode, manifest["spec"])

    metadata["key"] = package_key
    metadata["name"] = package_name
    if package_description is None:
        metadata.pop("description", None)
    else:
        metadata["description"] = package_description

    if input_schema is not None:
        spec["inputs"] = deepcopy(input_schema)

    if tool_keys is not None and capability_profiles is None:
        capability_profiles = [
            {
                "key": tool_profile_key,
                "name": tool_profile_name,
                "toolKeys": list(tool_keys),
            }
        ]
    if capability_profiles is not None:
        spec["capabilityProfiles"] = deepcopy(capability_profiles)

    if output_schemas is not None:
        spec["outputSchemas"] = deepcopy(output_schemas)
    elif output_schema_key != "summary_output":
        output_schema = cast(list[ManifestNode], spec["outputSchemas"])[0]
        output_schema["key"] = output_schema_key

    if mcp_servers is not None:
        spec["mcpServers"] = deepcopy(mcp_servers)

    if agents is not None:
        spec["agents"] = deepcopy(agents)
    else:
        agent = cast(list[ManifestNode], spec["agents"])[0]
        agent["key"] = agent_key
        agent["name"] = agent_name
        if agent_description is not None:
            agent["description"] = agent_description
        agent["modelConnection"] = model_connection
        agent["systemPrompt"] = system_prompt
        agent["outputSchema"] = output_schema_key
        if input_schema is not None:
            agent["inputSchema"] = deepcopy(input_schema)
        if capability_profiles is not None:
            agent["capabilityProfiles"] = [profile["key"] for profile in capability_profiles]
        if mcp_servers is not None:
            agent["mcpServers"] = [server["key"] for server in mcp_servers]

    if workflows is not None:
        spec["workflows"] = deepcopy(workflows)
        return manifest

    workflow = cast(list[ManifestNode], spec["workflows"])[0]
    workflow["key"] = workflow_key
    workflow["name"] = workflow_name
    if workflow_description is not None:
        workflow["description"] = workflow_description
    if input_schema is not None:
        workflow["inputSchema"] = deepcopy(input_schema)
    workflow_flow = cast(ManifestNode, workflow["flow"])
    workflow_flow["uses"] = agent_key
    if flow is not None:
        workflow["flow"] = deepcopy(flow)
    if workflow_output is not None:
        workflow["output"] = deepcopy(workflow_output)
    return manifest


def base_manifest(**overrides: Any) -> str:
    return dump_manifest(base_manifest_data(**overrides))


def tradingagents_research_manifest_data() -> ManifestNode:
    input_schema = {
        "type": "object",
        "properties": {"ticker": {"type": "string"}},
        "required": ["ticker"],
    }
    return base_manifest_data(
        package_key="tradingagents_research",
        package_name="TradingAgents Research Package",
        package_description="Portable package for the representative research workflow.",
        input_schema=input_schema,
        capability_profiles=[
            {
                "key": "market_research_tools",
                "name": "Market Research Tools",
                "description": "Uses server-declared market data tools.",
                "toolKeys": ["signaldeck.finance.market_data.quote_lookup"],
            }
        ],
        output_schema_key="trading_decision",
        output_schemas=[
            {
                "key": "trading_decision",
                "name": "Trading Decision",
                "description": "Final research-only portfolio decision.",
                "jsonSchema": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["action", "rationale"],
                },
            }
        ],
        mcp_servers=[
            {
                "key": "research_context",
                "name": "Research Context",
                "description": "Local context server declaration.",
                "transport": "stdio",
                "command": "python",
                "args": ["server.py"],
                "env": {"RESEARCH_CONTEXT_TOKEN": "local-token"},
                "toolKeys": ["research_context.search"],
            }
        ],
        agent_key="market_analyst",
        agent_name="Market Analyst",
        agent_description="Produces market research.",
        model_connection="tradingagents_primary_model",
        system_prompt="Use provided tools and return structured output.\n",
        workflow_key="daily_research",
        workflow_name="Daily Research",
        workflow_description="Runs the market analyst.",
        flow={
            "kind": "step",
            "id": "market_analysis",
            "slot": "decision",
            "uses": "market_analyst",
            "with": {"ticker": "${{ inputs.ticker }}"},
        },
        workflow_output={"from": "${{ nodes.market_analysis.outputs.decision }}"},
    )


def tradingagents_research_manifest() -> str:
    return dump_manifest(tradingagents_research_manifest_data())
