# pyright: reportMissingImports=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import cast

from pydantic import ValidationError
from ruamel.yaml import YAML
from ruamel.yaml.constructor import DuplicateKeyError
from ruamel.yaml.error import MarkedYAMLError, YAMLError
from ruamel.yaml.events import AliasEvent, ScalarEvent

from app.schemas.workflow_package_manifest import (
    WORKFLOW_PACKAGE_MANIFEST_API_VERSION,
    WorkflowPackageFanoutNode,
    WorkflowPackageHttpNode,
    WorkflowPackageLoopNode,
    WorkflowPackageManifest,
    WorkflowPackageManifestDiagnostic,
    WorkflowPackageManifestDiagnosticSeverity,
    WorkflowPackageManifestParseResult,
    WorkflowPackageNode,
    WorkflowPackageReference,
    WorkflowPackageSequenceNode,
    WorkflowPackageStepNode,
)

_PathToken = str | int

_ALLOWED_YAML_TAGS = {
    None,
    "tag:yaml.org,2002:bool",
    "tag:yaml.org,2002:float",
    "tag:yaml.org,2002:int",
    "tag:yaml.org,2002:map",
    "tag:yaml.org,2002:null",
    "tag:yaml.org,2002:seq",
    "tag:yaml.org,2002:str",
}
_FORBIDDEN_MANIFEST_KEYS = {
    "modelConnectionId",
    "outputSchemaId",
    "capabilityId",
    "mcpServerId",
    "apiKey",
    "secret",
    "secretPayload",
    "encrypted",
    "password",
}
_REF_EXPR_RE = re.compile(r"^\$\{\{\s*(?P<body>[^{}]+?)\s*\}\}$")
_HTTP_REQUEST_REF_FIELDS = {"url", "headers", "query", "body"}
_REMOVED_SCHEMA_KEYWORDS = {"additionalProperties", "allowAdditionalProperties"}

_ALIAS_LOC = {
    "api_version": "apiVersion",
    "capability_profiles": "capabilityProfiles",
    "output_schemas": "outputSchemas",
    "mcp_servers": "mcpServers",
    "tool_keys": "toolKeys",
    "json_schema": "jsonSchema",
    "model_connection": "modelConnection",
    "system_prompt": "systemPrompt",
    "input_schema": "inputSchema",
    "output_schema": "outputSchema",
    "budget_usd": "budgetUsd",
    "from_": "from",
    "max_iterations": "maxIterations",
    "timeout_seconds": "timeoutSeconds",
}


def parse_workflow_package_manifest(source: str) -> WorkflowPackageManifestParseResult:
    return WorkflowPackageManifestParser().parse(source)


def locate_workflow_package_manifest_path(source: str, path: str) -> tuple[int | None, int | None]:
    return WorkflowPackageManifestParser().locate_path(source, path)


class WorkflowPackageManifestParser:
    def parse(self, source: str) -> WorkflowPackageManifestParseResult:
        syntax_diagnostics = self._scan_yaml_events(source)
        if syntax_diagnostics:
            return WorkflowPackageManifestParseResult(diagnostics=syntax_diagnostics)

        try:
            data = self._new_yaml().load(source)
        except DuplicateKeyError as exc:
            return WorkflowPackageManifestParseResult(
                diagnostics=[self._duplicate_key_diagnostic(exc)]
            )
        except MarkedYAMLError as exc:
            return WorkflowPackageManifestParseResult(
                diagnostics=[self._marked_yaml_diagnostic(exc)]
            )
        except YAMLError as exc:
            return WorkflowPackageManifestParseResult(
                diagnostics=[self._diagnostic(f"Malformed YAML: {exc}", path="$")]
            )

        if not isinstance(data, Mapping):
            return WorkflowPackageManifestParseResult(
                diagnostics=[
                    self._diagnostic(
                        "Manifest source must be a YAML mapping",
                        path="$",
                        location=self._location_for(data, ()),
                    )
                ]
            )

        json_diagnostics = self._validate_json_compatible(data, ())
        if json_diagnostics:
            return WorkflowPackageManifestParseResult(diagnostics=json_diagnostics)

        legacy_diagnostics = self._validate_legacy_skill_refs(data)
        if legacy_diagnostics:
            return WorkflowPackageManifestParseResult(diagnostics=legacy_diagnostics)

        forbidden_diagnostics = self._validate_forbidden_keys(data, ())
        if forbidden_diagnostics:
            return WorkflowPackageManifestParseResult(diagnostics=forbidden_diagnostics)

        closed_object_diagnostics = self._validate_closed_object_schema_keywords(data)
        if closed_object_diagnostics:
            return WorkflowPackageManifestParseResult(diagnostics=closed_object_diagnostics)

        secret_ref_diagnostics = self._validate_secret_reference_locations(data, data, (), False)
        if secret_ref_diagnostics:
            return WorkflowPackageManifestParseResult(diagnostics=secret_ref_diagnostics)

        api_version = data.get("apiVersion")
        if api_version != WORKFLOW_PACKAGE_MANIFEST_API_VERSION:
            return WorkflowPackageManifestParseResult(
                diagnostics=[
                    self._diagnostic(
                        self._api_version_message(api_version),
                        path="apiVersion",
                        location=self._location_for(data, ("apiVersion",)),
                    )
                ]
            )

        try:
            manifest = WorkflowPackageManifest.model_validate(data)
        except ValidationError as exc:
            return WorkflowPackageManifestParseResult(
                diagnostics=self._validation_diagnostics(exc, data)
            )

        semantic_diagnostics = self._validate_manifest_semantics(manifest, data)
        if semantic_diagnostics:
            return WorkflowPackageManifestParseResult(diagnostics=semantic_diagnostics)
        return WorkflowPackageManifestParseResult(manifest=manifest, diagnostics=[])

    def locate_path(self, source: str, path: str) -> tuple[int | None, int | None]:
        try:
            data = self._new_yaml().load(source)
        except YAMLError:
            return None, None
        return self._location_for(data, self._path_to_tokens(path))

    def _scan_yaml_events(self, source: str) -> list[WorkflowPackageManifestDiagnostic]:
        diagnostics: list[WorkflowPackageManifestDiagnostic] = []
        try:
            for event in self._new_yaml().parse(source):
                anchor = getattr(event, "anchor", None)
                if isinstance(event, AliasEvent):
                    diagnostics.append(
                        self._diagnostic(
                            "YAML aliases are not supported in workflow package manifests",
                            path="$",
                            location=self._mark_location(event.start_mark),
                        )
                    )
                    continue
                if anchor:
                    diagnostics.append(
                        self._diagnostic(
                            "YAML anchors are not supported in workflow package manifests",
                            path="$",
                            location=self._mark_location(event.start_mark),
                        )
                    )
                tag = getattr(event, "tag", None)
                if tag == "tag:yaml.org,2002:merge":
                    diagnostics.append(
                        self._diagnostic(
                            "YAML merge keys are not supported in workflow package manifests",
                            path="$",
                            location=self._mark_location(event.start_mark),
                        )
                    )
                elif tag not in _ALLOWED_YAML_TAGS:
                    diagnostics.append(
                        self._diagnostic(
                            f"YAML tag {tag!r} is not supported in workflow package manifests",
                            path="$",
                            location=self._mark_location(event.start_mark),
                        )
                    )
                elif isinstance(event, ScalarEvent) and event.value == "<<":
                    diagnostics.append(
                        self._diagnostic(
                            "YAML merge keys are not supported in workflow package manifests",
                            path="$",
                            location=self._mark_location(event.start_mark),
                        )
                    )
        except DuplicateKeyError as exc:
            return [self._duplicate_key_diagnostic(exc)]
        except MarkedYAMLError as exc:
            return [self._marked_yaml_diagnostic(exc)]
        except YAMLError as exc:
            return [self._diagnostic(f"Malformed YAML: {exc}", path="$")]
        return diagnostics

    def _validate_json_compatible(
        self, value: object, tokens: tuple[_PathToken, ...]
    ) -> list[WorkflowPackageManifestDiagnostic]:
        diagnostics: list[WorkflowPackageManifestDiagnostic] = []
        if isinstance(value, Mapping):
            for key, child in cast(Mapping[object, object], value).items():
                if not isinstance(key, str):
                    diagnostics.append(
                        self._diagnostic(
                            "YAML mapping keys must be strings",
                            path=self._manifest_path(tokens),
                            location=self._location_for(value, tokens),
                        )
                    )
                    continue
                diagnostics.extend(self._validate_json_compatible(child, (*tokens, key)))
            return diagnostics
        if isinstance(value, bool | str) or value is None:
            return diagnostics
        if isinstance(value, int):
            return diagnostics
        if isinstance(value, float):
            if math.isfinite(value):
                return diagnostics
            diagnostics.append(
                self._diagnostic(
                    "YAML numeric values must be finite",
                    path=self._manifest_path(tokens),
                    location=self._location_for(value, tokens),
                )
            )
            return diagnostics
        if isinstance(value, Sequence):
            for index, child in enumerate(value):
                diagnostics.extend(self._validate_json_compatible(child, (*tokens, index)))
            return diagnostics
        diagnostics.append(
            self._diagnostic(
                f"YAML value type {type(value).__name__!r} is not supported",
                path=self._manifest_path(tokens),
                location=self._location_for(value, tokens),
            )
        )
        return diagnostics

    def _validate_closed_object_schema_keywords(
        self, data: Mapping[object, object]
    ) -> list[WorkflowPackageManifestDiagnostic]:
        diagnostics: list[WorkflowPackageManifestDiagnostic] = []
        for tokens in self._schema_root_tokens(data):
            schema = self._value_at_path(data, tokens)
            diagnostics.extend(
                self._validate_closed_object_schema_keywords_at(data, schema, tokens)
            )
        return diagnostics

    def _schema_root_tokens(self, data: Mapping[object, object]) -> list[tuple[_PathToken, ...]]:
        spec = data.get("spec")
        if not isinstance(spec, Mapping):
            return []
        roots: list[tuple[_PathToken, ...]] = [("spec", "inputs")]
        output_schemas = spec.get("outputSchemas")
        if isinstance(output_schemas, Sequence) and not isinstance(output_schemas, str | bytes):
            roots.extend(
                ("spec", "outputSchemas", index, "jsonSchema")
                for index, item in enumerate(output_schemas)
                if isinstance(item, Mapping)
            )
        agents = spec.get("agents")
        if isinstance(agents, Sequence) and not isinstance(agents, str | bytes):
            roots.extend(
                ("spec", "agents", index, "inputSchema")
                for index, item in enumerate(agents)
                if isinstance(item, Mapping)
            )
        workflows = spec.get("workflows")
        if isinstance(workflows, Sequence) and not isinstance(workflows, str | bytes):
            roots.extend(
                ("spec", "workflows", index, "inputSchema")
                for index, item in enumerate(workflows)
                if isinstance(item, Mapping)
            )
        return roots

    def _value_at_path(self, data: object, tokens: tuple[_PathToken, ...]) -> object:
        current = data
        for token in tokens:
            if isinstance(current, Mapping) and isinstance(token, str):
                current = cast(Mapping[object, object], current).get(token)
                continue
            if (
                isinstance(current, Sequence)
                and not isinstance(current, str | bytes)
                and isinstance(token, int)
            ):
                sequence = cast(Sequence[object], current)
                current = sequence[token] if 0 <= token < len(sequence) else None
                continue
            return None
        return current

    def _validate_closed_object_schema_keywords_at(
        self,
        data: object,
        value: object,
        tokens: tuple[_PathToken, ...],
    ) -> list[WorkflowPackageManifestDiagnostic]:
        diagnostics: list[WorkflowPackageManifestDiagnostic] = []
        if isinstance(value, Mapping):
            source = cast(Mapping[object, object], value)
            property_name_context = bool(tokens and tokens[-1] == "properties")
            for key, item in source.items():
                if not isinstance(key, str):
                    continue
                child_tokens = (*tokens, key)
                if not property_name_context and key in _REMOVED_SCHEMA_KEYWORDS:
                    diagnostics.append(
                        self._diagnostic(
                            f"{key} is not supported in package schemas; "
                            "objects are closed by default",
                            path=self._manifest_path(child_tokens),
                            location=self._location_for(data, child_tokens),
                        )
                    )
                    continue
                diagnostics.extend(
                    self._validate_closed_object_schema_keywords_at(data, item, child_tokens)
                )
            return diagnostics
        if isinstance(value, Sequence) and not isinstance(value, str | bytes):
            for index, item in enumerate(value):
                diagnostics.extend(
                    self._validate_closed_object_schema_keywords_at(data, item, (*tokens, index))
                )
        return diagnostics

    def _validate_forbidden_keys(
        self, value: object, tokens: tuple[_PathToken, ...]
    ) -> list[WorkflowPackageManifestDiagnostic]:
        diagnostics: list[WorkflowPackageManifestDiagnostic] = []
        if isinstance(value, Mapping):
            for key, child in cast(Mapping[object, object], value).items():
                child_tokens = (*tokens, key) if isinstance(key, str) else tokens
                if isinstance(key, str) and key in _FORBIDDEN_MANIFEST_KEYS:
                    diagnostics.append(
                        self._diagnostic(
                            f"{key} is not allowed in workflow package manifests",
                            path=self._manifest_path(child_tokens),
                            location=self._location_for(value, (key,)),
                        )
                    )
                diagnostics.extend(self._validate_forbidden_keys(child, child_tokens))
        elif isinstance(value, Sequence) and not isinstance(value, str | bytes):
            for index, child in enumerate(value):
                diagnostics.extend(self._validate_forbidden_keys(child, (*tokens, index)))
        return diagnostics

    def _validate_secret_reference_locations(
        self,
        root: object,
        value: object,
        tokens: tuple[_PathToken, ...],
        in_http_request_field: bool,
    ) -> list[WorkflowPackageManifestDiagnostic]:
        diagnostics: list[WorkflowPackageManifestDiagnostic] = []
        if isinstance(value, Mapping):
            is_http_node = cast(Mapping[object, object], value).get("kind") == "http"
            for key, child in cast(Mapping[object, object], value).items():
                child_tokens = (*tokens, key) if isinstance(key, str) else tokens
                child_in_http_request = in_http_request_field or (
                    is_http_node and isinstance(key, str) and key in _HTTP_REQUEST_REF_FIELDS
                )
                diagnostics.extend(
                    self._validate_secret_reference_locations(
                        root,
                        child,
                        child_tokens,
                        child_in_http_request,
                    )
                )
            return diagnostics
        if isinstance(value, Sequence) and not isinstance(value, str | bytes):
            for index, child in enumerate(value):
                diagnostics.extend(
                    self._validate_secret_reference_locations(
                        root,
                        child,
                        (*tokens, index),
                        in_http_request_field,
                    )
                )
            return diagnostics
        if (
            isinstance(value, str)
            and "${{" in value
            and "secrets." in value
            and not in_http_request_field
        ):
            diagnostics.append(
                self._diagnostic(
                    "Secret references are only supported in HTTP request fields",
                    path=self._manifest_path(tokens),
                    location=self._location_for(root, tokens),
                )
            )
        return diagnostics

    def _validate_legacy_skill_refs(self, data: object) -> list[WorkflowPackageManifestDiagnostic]:
        if not isinstance(data, Mapping):
            return []
        spec = cast(Mapping[object, object], data).get("spec")
        if not isinstance(spec, Mapping):
            return []
        if "skills" not in cast(Mapping[object, object], spec):
            return []
        return [
            self._diagnostic(
                "spec.skills is no longer supported; use spec.capabilityProfiles",
                path="spec.skills",
                location=self._location_for(data, ("spec", "skills")),
            )
        ]

    def _validation_diagnostics(
        self, exc: ValidationError, data: object
    ) -> list[WorkflowPackageManifestDiagnostic]:
        diagnostics: list[WorkflowPackageManifestDiagnostic] = []
        for raw_error in cast(list[object], exc.errors()):
            error = cast(Mapping[str, object], raw_error)
            tokens = self._error_loc_to_tokens(error.get("loc", ()))
            diagnostics.append(
                self._diagnostic(
                    self._clean_validation_message(str(error.get("msg", "Invalid manifest value"))),
                    path=self._manifest_path(tokens),
                    location=self._location_for(data, tokens),
                )
            )
        return diagnostics

    def _validate_manifest_semantics(
        self, manifest: WorkflowPackageManifest, data: object
    ) -> list[WorkflowPackageManifestDiagnostic]:
        diagnostics: list[WorkflowPackageManifestDiagnostic] = []
        diagnostics.extend(
            self._validate_unique_keys(
                [item.key for item in manifest.spec.capability_profiles],
                ("spec", "capabilityProfiles"),
                data,
                "Duplicate capability profile key",
            )
        )
        diagnostics.extend(
            self._validate_unique_keys(
                [item.key for item in manifest.spec.output_schemas],
                ("spec", "outputSchemas"),
                data,
                "Duplicate output schema key",
            )
        )
        diagnostics.extend(
            self._validate_unique_keys(
                [item.key for item in manifest.spec.mcp_servers],
                ("spec", "mcpServers"),
                data,
                "Duplicate MCP server key",
            )
        )
        diagnostics.extend(
            self._validate_unique_keys(
                [item.key for item in manifest.spec.agents],
                ("spec", "agents"),
                data,
                "Duplicate agent key",
            )
        )
        diagnostics.extend(
            self._validate_unique_keys(
                [item.key for item in manifest.spec.workflows],
                ("spec", "workflows"),
                data,
                "Duplicate workflow key",
            )
        )
        for workflow_index, workflow in enumerate(manifest.spec.workflows):
            diagnostics.extend(
                self._validate_workflow_graph(
                    workflow.flow, ("spec", "workflows", workflow_index, "flow"), data
                )
            )
        return diagnostics

    def _validate_unique_keys(
        self, keys: list[str], base_path: tuple[_PathToken, ...], data: object, message: str
    ) -> list[WorkflowPackageManifestDiagnostic]:
        diagnostics: list[WorkflowPackageManifestDiagnostic] = []
        seen: set[str] = set()
        for index, key in enumerate(keys):
            if key in seen:
                path = (*base_path, index, "key")
                diagnostics.append(
                    self._diagnostic(
                        f"{message}: {key}",
                        path=self._manifest_path(path),
                        location=self._location_for(data, path),
                    )
                )
            seen.add(key)
        return diagnostics

    def _validate_workflow_graph(
        self, node: WorkflowPackageNode, path: tuple[_PathToken, ...], data: object
    ) -> list[WorkflowPackageManifestDiagnostic]:
        diagnostics: list[WorkflowPackageManifestDiagnostic] = []
        node_ids: dict[str, tuple[_PathToken, ...]] = {}

        def visit(current: WorkflowPackageNode, current_path: tuple[_PathToken, ...]) -> None:
            id_path = (*current_path, "id")
            if current.id in node_ids:
                diagnostics.append(
                    self._diagnostic(
                        f"Duplicate node id: {current.id}",
                        path=self._manifest_path(id_path),
                        location=self._location_for(data, id_path),
                    )
                )
            else:
                node_ids[current.id] = id_path
            if isinstance(current, WorkflowPackageSequenceNode):
                slots: set[str] = set()
                for index, child in enumerate(current.nodes):
                    child_path = (*current_path, "nodes", index)
                    if isinstance(child, WorkflowPackageStepNode | WorkflowPackageHttpNode):
                        if child.slot in slots:
                            slot_path = (*child_path, "slot")
                            diagnostics.append(
                                self._diagnostic(
                                    "Duplicate output slot name within the same sequence",
                                    path=self._manifest_path(slot_path),
                                    location=self._location_for(data, slot_path),
                                )
                            )
                        slots.add(child.slot)
                    visit(child, child_path)
            elif isinstance(current, WorkflowPackageFanoutNode):
                branch_ids: set[str] = set()
                for index, branch in enumerate(current.branches):
                    branch_path = (*current_path, "branches", index)
                    if branch.id in branch_ids:
                        id_path = (*branch_path, "id")
                        diagnostics.append(
                            self._diagnostic(
                                f"Duplicate fanout branch id: {branch.id}",
                                path=self._manifest_path(id_path),
                                location=self._location_for(data, id_path),
                            )
                        )
                    branch_ids.add(branch.id)
                    visit(branch.node, (*branch_path, "node"))
            elif isinstance(current, WorkflowPackageLoopNode):
                visit(current.sequence, (*current_path, "sequence"))

        visit(node, path)
        if diagnostics:
            return diagnostics
        available_outputs: dict[str, set[str]] = {}
        diagnostics.extend(self._validate_node_order(node, path, data, available_outputs, node_ids))
        return diagnostics

    def _validate_node_order(
        self,
        node: WorkflowPackageNode,
        path: tuple[_PathToken, ...],
        data: object,
        available_outputs: dict[str, set[str]],
        all_node_ids: dict[str, tuple[_PathToken, ...]],
    ) -> list[WorkflowPackageManifestDiagnostic]:
        diagnostics: list[WorkflowPackageManifestDiagnostic] = []
        if isinstance(node, WorkflowPackageStepNode):
            for field_name, reference in node.inputs.items():
                diagnostic = self._validate_reference(
                    reference, (*path, "with", field_name), data, available_outputs, all_node_ids
                )
                if diagnostic is not None:
                    diagnostics.append(diagnostic)
            available_outputs[node.id] = {node.slot}
            return diagnostics
        if isinstance(node, WorkflowPackageHttpNode):
            for request_path, reference in self._http_request_references(node):
                diagnostic = self._validate_reference(
                    reference,
                    (*path, *request_path),
                    data,
                    available_outputs,
                    all_node_ids,
                )
                if diagnostic is not None:
                    diagnostics.append(diagnostic)
            available_outputs[node.id] = {node.slot}
            return diagnostics
        if isinstance(node, WorkflowPackageSequenceNode):
            sequence_outputs: set[str] = set()
            for index, child in enumerate(node.nodes):
                diagnostics.extend(
                    self._validate_node_order(
                        child, (*path, "nodes", index), data, available_outputs, all_node_ids
                    )
                )
                sequence_outputs.update(available_outputs.get(child.id, set()))
            available_outputs[node.id] = sequence_outputs
            return diagnostics
        if isinstance(node, WorkflowPackageFanoutNode):
            fanout_outputs: set[str] = set()
            baseline = {key: set(slots) for key, slots in available_outputs.items()}
            branch_outputs: dict[str, set[str]] = {}
            for index, branch in enumerate(node.branches):
                local_available = {key: set(slots) for key, slots in baseline.items()}
                diagnostics.extend(
                    self._validate_node_order(
                        branch.node,
                        (*path, "branches", index, "node"),
                        data,
                        local_available,
                        all_node_ids,
                    )
                )
                child_outputs = local_available.get(branch.node.id, set())
                branch_outputs.update(
                    {key: slots for key, slots in local_available.items() if key not in baseline}
                )
                fanout_outputs.update(child_outputs)
                if child_outputs:
                    fanout_outputs.add(branch.id)
            available_outputs.update(branch_outputs)
            available_outputs[node.id] = fanout_outputs
            return diagnostics
        for field_name, reference in node.state.items():
            diagnostic = self._validate_reference(
                reference, (*path, "state", field_name), data, available_outputs, all_node_ids
            )
            if diagnostic is not None:
                diagnostics.append(diagnostic)
        diagnostics.extend(
            self._validate_node_order(
                node.sequence, (*path, "sequence"), data, available_outputs, all_node_ids
            )
        )
        available_outputs[node.id] = set(available_outputs.get(node.sequence.id, set()))
        return diagnostics

    def _http_request_references(
        self,
        node: WorkflowPackageHttpNode,
    ) -> list[tuple[tuple[_PathToken, ...], WorkflowPackageReference]]:
        references: list[tuple[tuple[_PathToken, ...], WorkflowPackageReference]] = []
        for field_name, value in (
            ("url", node.url),
            ("headers", node.headers),
            ("query", node.query),
            ("body", node.body),
        ):
            references.extend(self._collect_http_request_references(value, (field_name,)))
        return references

    def _collect_http_request_references(
        self,
        value: object,
        path: tuple[_PathToken, ...],
    ) -> list[tuple[tuple[_PathToken, ...], WorkflowPackageReference]]:
        if isinstance(value, dict):
            mapped_references: list[tuple[tuple[_PathToken, ...], WorkflowPackageReference]] = []
            for key, item in cast(dict[str, object], value).items():
                mapped_references.extend(self._collect_http_request_references(item, (*path, key)))
            return mapped_references
        if isinstance(value, list):
            listed_references: list[tuple[tuple[_PathToken, ...], WorkflowPackageReference]] = []
            for index, item in enumerate(value):
                listed_references.extend(
                    self._collect_http_request_references(item, (*path, index))
                )
            return listed_references
        if not isinstance(value, str):
            return []
        expression = value.strip()
        match = _REF_EXPR_RE.fullmatch(expression)
        if match is None:
            return []
        body = match.group("body").strip()
        if body.startswith("secrets."):
            return []
        return [(path, WorkflowPackageReference.model_validate(expression))]

    def _validate_reference(
        self,
        reference: WorkflowPackageReference,
        path: tuple[_PathToken, ...],
        data: object,
        available_outputs: dict[str, set[str]],
        all_node_ids: dict[str, tuple[_PathToken, ...]],
    ) -> WorkflowPackageManifestDiagnostic | None:
        if reference.source != "nodes":
            return None
        node_id = str(reference.node_id or "")
        slot = str(reference.slot or "")
        slots = available_outputs.get(node_id)
        if slots is None:
            if node_id in all_node_ids:
                return self._diagnostic(
                    "Node references must point to an earlier node",
                    path=self._manifest_path(path),
                    location=self._location_for(data, path),
                )
            return self._diagnostic(
                f"Node {node_id!r} was not found",
                path=self._manifest_path(path),
                location=self._location_for(data, path),
            )
        if slot not in slots:
            return self._diagnostic(
                f"Slot {slot!r} was not found on node {node_id!r}",
                path=self._manifest_path(path),
                location=self._location_for(data, path),
            )
        return None

    @staticmethod
    def _new_yaml() -> YAML:
        yaml = YAML(typ="rt")
        yaml.allow_duplicate_keys = False
        yaml.version = (1, 2)
        return yaml

    def _duplicate_key_diagnostic(
        self, exc: DuplicateKeyError
    ) -> WorkflowPackageManifestDiagnostic:
        mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
        return self._diagnostic(
            "Duplicate mapping key is not allowed", path="$", location=self._mark_location(mark)
        )

    def _marked_yaml_diagnostic(self, exc: MarkedYAMLError) -> WorkflowPackageManifestDiagnostic:
        mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
        problem = getattr(exc, "problem", None) or str(exc)
        return self._diagnostic(
            f"Malformed YAML: {problem}", path="$", location=self._mark_location(mark)
        )

    @staticmethod
    def _api_version_message(api_version: object) -> str:
        if api_version is None:
            return "Field required"
        if isinstance(api_version, str) and api_version.startswith("signaldeck.workflow/"):
            return (
                "Workflow roots are not package manifests; use "
                f"'{WORKFLOW_PACKAGE_MANIFEST_API_VERSION}'"
            )
        return f"Input should be '{WORKFLOW_PACKAGE_MANIFEST_API_VERSION}'"

    @staticmethod
    def _diagnostic(
        message: str, *, path: str, location: tuple[int | None, int | None] = (None, None)
    ) -> WorkflowPackageManifestDiagnostic:
        line, column = location
        return WorkflowPackageManifestDiagnostic(
            severity=WorkflowPackageManifestDiagnosticSeverity.ERROR,
            message=message,
            path=path,
            line=line,
            column=column,
        )

    @staticmethod
    def _clean_validation_message(message: str) -> str:
        return message.removeprefix("Value error, ")

    @staticmethod
    def _error_loc_to_tokens(loc: object) -> tuple[_PathToken, ...]:
        if not isinstance(loc, Iterable) or isinstance(loc, str | bytes):
            return ()
        tokens: list[_PathToken] = []
        for item in loc:
            if isinstance(item, str):
                if item in {"step", "http", "sequence", "fanout", "loop"}:
                    continue
                tokens.append(_ALIAS_LOC.get(item, item))
            elif isinstance(item, int):
                tokens.append(item)
        return tuple(tokens)

    @staticmethod
    def _manifest_path(tokens: tuple[_PathToken, ...]) -> str:
        if not tokens:
            return "$"
        path = ""
        for token in tokens:
            if isinstance(token, int):
                path += f"[{token}]"
            elif not path:
                path = token
            else:
                path += f".{token}"
        return path

    @staticmethod
    def _path_to_tokens(path: str) -> tuple[_PathToken, ...]:
        if path == "$":
            return ()
        tokens: list[_PathToken] = []
        for raw_segment in path.split("."):
            segment = raw_segment
            while segment:
                key_match = re.match(r"[^\[\]]+", segment)
                if key_match is not None:
                    tokens.append(key_match.group(0))
                    segment = segment[key_match.end() :]
                    continue
                index_match = re.match(r"\[(\d+)\]", segment)
                if index_match is None:
                    return ()
                tokens.append(int(index_match.group(1)))
                segment = segment[index_match.end() :]
        return tuple(tokens)

    def _location_for(
        self, root: object, tokens: tuple[_PathToken, ...]
    ) -> tuple[int | None, int | None]:
        current = root
        last_location = self._object_location(root)
        for index, token in enumerate(tokens):
            if isinstance(current, Mapping) and isinstance(token, str):
                mapping = cast(Mapping[object, object], current)
                if token not in mapping:
                    return last_location
                location = self._map_value_location(current, token)
                if index == len(tokens) - 1:
                    return location
                last_location = location
                current = mapping[token]
                continue
            if (
                isinstance(current, Sequence)
                and not isinstance(current, str | bytes)
                and isinstance(token, int)
            ):
                sequence = cast(Sequence[object], current)
                if token < 0 or token >= len(sequence):
                    return last_location
                location = self._sequence_item_location(current, token)
                if index == len(tokens) - 1:
                    return location
                last_location = location
                current = sequence[token]
                continue
            return last_location
        return last_location

    @staticmethod
    def _object_location(value: object) -> tuple[int | None, int | None]:
        lc = getattr(value, "lc", None)
        line = getattr(lc, "line", None)
        column = getattr(lc, "col", None)
        if isinstance(line, int) and isinstance(column, int):
            return line + 1, column + 1
        return None, None

    def _map_value_location(self, mapping: object, key: str) -> tuple[int | None, int | None]:
        lc = getattr(mapping, "lc", None)
        for accessor_name in ("value", "key"):
            accessor = getattr(lc, accessor_name, None)
            if accessor is None:
                continue
            accessor_fn = cast(Callable[[str], object], accessor)
            try:
                location = self._raw_location(accessor_fn(key))
            except (KeyError, TypeError):
                continue
            if location != (None, None):
                return location
        return self._object_location(mapping)

    def _sequence_item_location(
        self, sequence: object, index: int
    ) -> tuple[int | None, int | None]:
        lc = getattr(sequence, "lc", None)
        item = getattr(lc, "item", None)
        if item is not None:
            item_fn = cast(Callable[[int], object], item)
            try:
                location = self._raw_location(item_fn(index))
            except (KeyError, TypeError):
                location = (None, None)
            if location != (None, None):
                return location
        return self._object_location(sequence)

    @staticmethod
    def _raw_location(raw_location: object) -> tuple[int | None, int | None]:
        if (
            isinstance(raw_location, tuple)
            and len(raw_location) >= 2
            and isinstance(raw_location[0], int)
            and isinstance(raw_location[1], int)
        ):
            return raw_location[0] + 1, raw_location[1] + 1
        return None, None

    @staticmethod
    def _mark_location(mark: object) -> tuple[int | None, int | None]:
        line = getattr(mark, "line", None)
        column = getattr(mark, "column", None)
        if isinstance(line, int) and isinstance(column, int):
            return line + 1, column + 1
        return None, None


__all__ = [
    "WorkflowPackageManifestParser",
    "locate_workflow_package_manifest_path",
    "parse_workflow_package_manifest",
]
