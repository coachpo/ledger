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

from app.schemas.workflow_manifest import (
    WorkflowManifest,
    WorkflowManifestDiagnostic,
    WorkflowManifestDiagnosticSeverity,
    WorkflowManifestParseResult,
    WorkflowManifestReference,
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


def parse_workflow_manifest(source: str) -> WorkflowManifestParseResult:
    return WorkflowManifestParser().parse(source)


def locate_workflow_manifest_path(source: str, path: str) -> tuple[int | None, int | None]:
    return WorkflowManifestParser().locate_path(source, path)


class WorkflowManifestParser:
    def parse(self, source: str) -> WorkflowManifestParseResult:
        syntax_diagnostics = self._scan_yaml_events(source)
        if syntax_diagnostics:
            return WorkflowManifestParseResult(diagnostics=syntax_diagnostics)

        try:
            data = self._new_yaml().load(source)
        except DuplicateKeyError as exc:
            return WorkflowManifestParseResult(diagnostics=[self._duplicate_key_diagnostic(exc)])
        except MarkedYAMLError as exc:
            return WorkflowManifestParseResult(diagnostics=[self._marked_yaml_diagnostic(exc)])
        except YAMLError as exc:
            return WorkflowManifestParseResult(
                diagnostics=[self._diagnostic(f"Malformed YAML: {exc}", path="$")]
            )

        if not isinstance(data, Mapping):
            return WorkflowManifestParseResult(
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
            return WorkflowManifestParseResult(diagnostics=json_diagnostics)

        try:
            manifest = WorkflowManifest.model_validate(data)
        except ValidationError as exc:
            return WorkflowManifestParseResult(diagnostics=self._validation_diagnostics(exc, data))

        semantic_diagnostics = self._validate_manifest_semantics(manifest, data)
        if semantic_diagnostics:
            return WorkflowManifestParseResult(diagnostics=semantic_diagnostics)
        return WorkflowManifestParseResult(manifest=manifest, diagnostics=[])

    def locate_path(self, source: str, path: str) -> tuple[int | None, int | None]:
        try:
            data = self._new_yaml().load(source)
        except YAMLError:
            return None, None
        return self._location_for(data, self._path_to_tokens(path))

    def _scan_yaml_events(self, source: str) -> list[WorkflowManifestDiagnostic]:
        diagnostics: list[WorkflowManifestDiagnostic] = []
        try:
            for event in self._new_yaml().parse(source):
                anchor = getattr(event, "anchor", None)
                if isinstance(event, AliasEvent):
                    diagnostics.append(
                        self._diagnostic(
                            "YAML aliases are not supported in workflow manifests",
                            path="$",
                            location=self._mark_location(event.start_mark),
                        )
                    )
                    continue
                if anchor:
                    diagnostics.append(
                        self._diagnostic(
                            "YAML anchors are not supported in workflow manifests",
                            path="$",
                            location=self._mark_location(event.start_mark),
                        )
                    )
                tag = getattr(event, "tag", None)
                if tag == "tag:yaml.org,2002:merge":
                    diagnostics.append(
                        self._diagnostic(
                            "YAML merge keys are not supported in workflow manifests",
                            path="$",
                            location=self._mark_location(event.start_mark),
                        )
                    )
                elif tag not in _ALLOWED_YAML_TAGS:
                    diagnostics.append(
                        self._diagnostic(
                            f"YAML tag {tag!r} is not supported in workflow manifests",
                            path="$",
                            location=self._mark_location(event.start_mark),
                        )
                    )
                elif isinstance(event, ScalarEvent) and event.value == "<<":
                    diagnostics.append(
                        self._diagnostic(
                            "YAML merge keys are not supported in workflow manifests",
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
    ) -> list[WorkflowManifestDiagnostic]:
        diagnostics: list[WorkflowManifestDiagnostic] = []
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
            sequence = value
            for index, child in enumerate(sequence):
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
    ) -> list[WorkflowManifestDiagnostic]:
        diagnostics: list[WorkflowManifestDiagnostic] = []
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
        manifest: WorkflowManifest,
        data: object,
    ) -> list[WorkflowManifestDiagnostic]:
        diagnostics: list[WorkflowManifestDiagnostic] = []
        step_index_by_id: dict[str, int] = {}
        slot_optional_by_step: dict[str, dict[str, bool]] = {}

        for step_index, step in enumerate(manifest.steps):
            step_path = ("steps", step_index, "id")
            if step.id in step_index_by_id:
                diagnostics.append(
                    self._diagnostic(
                        f"Duplicate step id: {step.id}",
                        path=self._manifest_path(step_path),
                        location=self._location_for(data, step_path),
                    )
                )
                continue
            step_index_by_id[step.id] = step_index

            slots: dict[str, bool] = {}
            for agent_index, agent in enumerate(step.agents):
                slot_path = ("steps", step_index, "agents", agent_index, "slot")
                if agent.slot in slots:
                    diagnostics.append(
                        self._diagnostic(
                            "Duplicate slot name within the same step",
                            path=self._manifest_path(slot_path),
                            location=self._location_for(data, slot_path),
                        )
                    )
                    continue
                slots[agent.slot] = agent.optional
            slot_optional_by_step[step.id] = slots

        if diagnostics:
            return diagnostics

        for step_index, step in enumerate(manifest.steps):
            for agent_index, agent in enumerate(step.agents):
                for field_name, reference in agent.inputs.items():
                    reference_path = (
                        "steps",
                        step_index,
                        "agents",
                        agent_index,
                        "with",
                        field_name,
                    )
                    diagnostic = self._validate_step_reference(
                        reference,
                        step_index=step_index,
                        step_index_by_id=step_index_by_id,
                        slot_optional_by_step=slot_optional_by_step,
                        path=reference_path,
                        data=data,
                    )
                    if diagnostic is not None:
                        diagnostics.append(diagnostic)

        output_reference = manifest.output.from_
        output_path = ("output", "from")
        output_diagnostic = self._validate_step_reference(
            output_reference,
            step_index=len(manifest.steps),
            step_index_by_id=step_index_by_id,
            slot_optional_by_step=slot_optional_by_step,
            path=output_path,
            data=data,
            forbid_optional=True,
        )
        if output_diagnostic is not None:
            diagnostics.append(output_diagnostic)
        return diagnostics

    def _validate_step_reference(
        self,
        reference: WorkflowManifestReference,
        *,
        step_index: int,
        step_index_by_id: dict[str, int],
        slot_optional_by_step: dict[str, dict[str, bool]],
        path: tuple[_PathToken, ...],
        data: object,
        forbid_optional: bool = False,
    ) -> WorkflowManifestDiagnostic | None:
        if reference.source != "steps":
            return None
        referenced_step_id = str(reference.step_id or "")
        referenced_slot = str(reference.slot or "")
        referenced_index = step_index_by_id.get(referenced_step_id)
        if referenced_index is None:
            return self._diagnostic(
                f"Step {referenced_step_id!r} was not found",
                path=self._manifest_path(path),
                location=self._location_for(data, path),
            )
        if referenced_index >= step_index:
            return self._diagnostic(
                "Step references must point to an earlier step",
                path=self._manifest_path(path),
                location=self._location_for(data, path),
            )
        slots = slot_optional_by_step[referenced_step_id]
        if referenced_slot not in slots:
            return self._diagnostic(
                f"Slot {referenced_slot!r} was not found on step {referenced_step_id!r}",
                path=self._manifest_path(path),
                location=self._location_for(data, path),
            )
        if forbid_optional and slots[referenced_slot]:
            return self._diagnostic(
                "Final output cannot reference an optional slot",
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

    def _duplicate_key_diagnostic(self, exc: DuplicateKeyError) -> WorkflowManifestDiagnostic:
        mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
        return self._diagnostic(
            "Duplicate mapping key is not allowed",
            path="$",
            location=self._mark_location(mark),
        )

    def _marked_yaml_diagnostic(self, exc: MarkedYAMLError) -> WorkflowManifestDiagnostic:
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
    ) -> WorkflowManifestDiagnostic:
        line, column = location
        return WorkflowManifestDiagnostic(
            severity=WorkflowManifestDiagnosticSeverity.ERROR,
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
            if isinstance(item, str) and item == "from_":
                tokens.append("from")
            elif isinstance(item, str) and item == "input_schema":
                tokens.append("inputSchema")
            elif isinstance(item, str) and item == "api_version":
                tokens.append("apiVersion")
            elif isinstance(item, str | int):
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

    def _map_value_location(
        self,
        mapping: object,
        key: str,
    ) -> tuple[int | None, int | None]:
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
                raw_location = item_fn(index)
                location = self._raw_location(raw_location)
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
    "WorkflowManifestParser",
    "locate_workflow_manifest_path",
    "parse_workflow_manifest",
]
