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

from app.schemas.agent_manifest import (
    AgentManifest,
    AgentManifestDiagnostic,
    AgentManifestDiagnosticSeverity,
    AgentManifestParseResult,
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


def parse_agent_manifest(source: str) -> AgentManifestParseResult:
    return AgentManifestParser().parse(source)


def locate_agent_manifest_path(source: str, path: str) -> tuple[int | None, int | None]:
    return AgentManifestParser().locate_path(source, path)


class AgentManifestParser:
    def parse(self, source: str) -> AgentManifestParseResult:
        syntax_diagnostics = self._scan_yaml_events(source)
        if syntax_diagnostics:
            return AgentManifestParseResult(diagnostics=syntax_diagnostics)

        try:
            data = self._new_yaml().load(source)
        except DuplicateKeyError as exc:
            return AgentManifestParseResult(diagnostics=[self._duplicate_key_diagnostic(exc)])
        except MarkedYAMLError as exc:
            return AgentManifestParseResult(diagnostics=[self._marked_yaml_diagnostic(exc)])
        except YAMLError as exc:
            return AgentManifestParseResult(
                diagnostics=[self._diagnostic(f"Malformed YAML: {exc}", path="$")]
            )

        if not isinstance(data, Mapping):
            return AgentManifestParseResult(
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
            return AgentManifestParseResult(diagnostics=json_diagnostics)

        unsupported_skill_diagnostics = self._validate_unsupported_skill_refs(data)
        if unsupported_skill_diagnostics:
            return AgentManifestParseResult(diagnostics=unsupported_skill_diagnostics)

        try:
            manifest = AgentManifest.model_validate(data)
        except ValidationError as exc:
            return AgentManifestParseResult(diagnostics=self._validation_diagnostics(exc, data))

        semantic_diagnostics = self._validate_manifest_semantics(manifest, data)
        if semantic_diagnostics:
            return AgentManifestParseResult(diagnostics=semantic_diagnostics)
        return AgentManifestParseResult(manifest=manifest, diagnostics=[])

    def locate_path(self, source: str, path: str) -> tuple[int | None, int | None]:
        try:
            data = self._new_yaml().load(source)
        except YAMLError:
            return None, None
        return self._location_for(data, self._path_to_tokens(path))

    def _scan_yaml_events(self, source: str) -> list[AgentManifestDiagnostic]:
        diagnostics: list[AgentManifestDiagnostic] = []
        try:
            for event in self._new_yaml().parse(source):
                anchor = getattr(event, "anchor", None)
                if isinstance(event, AliasEvent):
                    diagnostics.append(
                        self._diagnostic(
                            "YAML aliases are not supported in agent manifests",
                            path="$",
                            location=self._mark_location(event.start_mark),
                        )
                    )
                    continue
                if anchor:
                    diagnostics.append(
                        self._diagnostic(
                            "YAML anchors are not supported in agent manifests",
                            path="$",
                            location=self._mark_location(event.start_mark),
                        )
                    )
                tag = getattr(event, "tag", None)
                if tag == "tag:yaml.org,2002:merge":
                    diagnostics.append(
                        self._diagnostic(
                            "YAML merge keys are not supported in agent manifests",
                            path="$",
                            location=self._mark_location(event.start_mark),
                        )
                    )
                elif tag not in _ALLOWED_YAML_TAGS:
                    diagnostics.append(
                        self._diagnostic(
                            f"YAML tag {tag!r} is not supported in agent manifests",
                            path="$",
                            location=self._mark_location(event.start_mark),
                        )
                    )
                elif isinstance(event, ScalarEvent) and event.value == "<<":
                    diagnostics.append(
                        self._diagnostic(
                            "YAML merge keys are not supported in agent manifests",
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
        self,
        value: object,
        tokens: tuple[_PathToken, ...],
    ) -> list[AgentManifestDiagnostic]:
        diagnostics: list[AgentManifestDiagnostic] = []
        if isinstance(value, Mapping):
            mapping = cast(Mapping[object, object], value)
            for key, child in mapping.items():
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

    def _validation_diagnostics(
        self,
        exc: ValidationError,
        data: object,
    ) -> list[AgentManifestDiagnostic]:
        diagnostics: list[AgentManifestDiagnostic] = []
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
        self,
        manifest: AgentManifest,
        data: object,
    ) -> list[AgentManifestDiagnostic]:
        diagnostics: list[AgentManifestDiagnostic] = []
        seen_capabilities: set[tuple[str, int]] = set()
        for index, ref in enumerate(manifest.spec.capabilities):
            identity = (ref.key, ref.version)
            if identity in seen_capabilities:
                diagnostics.append(
                    self._diagnostic(
                        "Duplicate capability selection",
                        path=f"spec.capabilities[{index}]",
                        location=self._location_for(data, ("spec", "capabilities", index)),
                    )
                )
            seen_capabilities.add(identity)

        seen_mcp_servers: set[tuple[str, int]] = set()
        for index, ref in enumerate(manifest.spec.mcp_servers):
            identity = (ref.key, ref.version)
            if identity in seen_mcp_servers:
                diagnostics.append(
                    self._diagnostic(
                        "Duplicate MCP server selection",
                        path=f"spec.mcpServers[{index}]",
                        location=self._location_for(data, ("spec", "mcpServers", index)),
                    )
                )
            seen_mcp_servers.add(identity)
        return diagnostics

    def _validate_unsupported_skill_refs(self, data: object) -> list[AgentManifestDiagnostic]:
        if not isinstance(data, Mapping):
            return []
        spec = cast(Mapping[object, object], data).get("spec")
        if not isinstance(spec, Mapping):
            return []
        spec_mapping = cast(Mapping[object, object], spec)
        if "skills" not in spec_mapping:
            return []
        return [
            self._diagnostic(
                "spec.skills is not supported in agent manifests; use spec.capabilities",
                path="spec.skills",
                location=self._location_for(data, ("spec", "skills")),
            )
        ]

    @staticmethod
    def _new_yaml() -> YAML:
        yaml = YAML(typ="rt")
        yaml.allow_duplicate_keys = False
        yaml.version = (1, 2)
        return yaml

    def _duplicate_key_diagnostic(self, exc: DuplicateKeyError) -> AgentManifestDiagnostic:
        mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
        return self._diagnostic(
            "Duplicate mapping key is not allowed",
            path="$",
            location=self._mark_location(mark),
        )

    def _marked_yaml_diagnostic(self, exc: MarkedYAMLError) -> AgentManifestDiagnostic:
        mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
        problem = getattr(exc, "problem", None) or str(exc)
        return self._diagnostic(
            f"Malformed YAML: {problem}",
            path="$",
            location=self._mark_location(mark),
        )

    @staticmethod
    def _diagnostic(
        message: str,
        *,
        path: str,
        location: tuple[int | None, int | None] = (None, None),
    ) -> AgentManifestDiagnostic:
        line, column = location
        return AgentManifestDiagnostic(
            severity=AgentManifestDiagnosticSeverity.ERROR,
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
        aliases = {
            "api_version": "apiVersion",
            "model_connection": "modelConnection",
            "system_prompt": "systemPrompt",
            "input_schema": "inputSchema",
            "output_schema": "outputSchema",
            "capabilities": "capabilities",
            "mcp_servers": "mcpServers",
        }
        for item in loc:
            if isinstance(item, str):
                tokens.append(aliases.get(item, item))
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
        self,
        root: object,
        tokens: tuple[_PathToken, ...],
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
                raw_location = accessor_fn(key)
            except (KeyError, TypeError):
                continue
            location = self._raw_location(raw_location)
            if location != (None, None):
                return location
        return self._object_location(mapping)

    def _sequence_item_location(
        self,
        sequence: object,
        index: int,
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


__all__ = ["AgentManifestParser", "locate_agent_manifest_path", "parse_agent_manifest"]
