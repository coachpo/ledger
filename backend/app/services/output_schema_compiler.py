from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from math import isfinite
from typing import Annotated, Any, Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, RootModel, create_model

from app.schemas.output_schema import (
    JsonPrimitive,
    JsonValue,
    OutputSchemaBuilderArray,
    OutputSchemaBuilderBoolean,
    OutputSchemaBuilderDiscriminatedUnion,
    OutputSchemaBuilderEnum,
    OutputSchemaBuilderField,
    OutputSchemaBuilderInteger,
    OutputSchemaBuilderLiteral,
    OutputSchemaBuilderNode,
    OutputSchemaBuilderNumber,
    OutputSchemaBuilderObject,
    OutputSchemaBuilderRef,
    OutputSchemaBuilderString,
)

_REGISTRY_REF_RE = re.compile(
    r"^registry://(?P<key>[a-z][a-z0-9_]{0,119})(?:@(?P<version>[1-9][0-9]*))?$"
)
_PRIMITIVE_TYPES = {"string", "integer", "number", "boolean"}


class OutputSchemaLike(Protocol):
    @property
    def key(self) -> str: ...

    @property
    def version(self) -> int: ...

    @property
    def status(self) -> str: ...

    @property
    def kind(self) -> str: ...

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str | None: ...

    @property
    def json_schema(self) -> dict[str, Any]: ...

    @property
    def registry_refs(self) -> list[str]: ...


class OutputSchemaRegistryResolver(Protocol):
    def resolve_registry_ref(
        self,
        key: str,
        version: int | None = None,
    ) -> OutputSchemaLike | None: ...


@dataclass
class PackageOutputSchemaCandidate:
    key: str
    version: int
    status: str
    kind: str
    name: str
    description: str | None
    json_schema: dict[str, Any]
    registry_refs: list[str]


def package_output_schema_candidate(
    *,
    key: str,
    name: str,
    description: str | None,
    json_schema: dict[str, Any],
) -> PackageOutputSchemaCandidate:
    return PackageOutputSchemaCandidate(
        key=key,
        version=1,
        status="published",
        kind="standalone",
        name=name,
        description=description,
        json_schema=json_schema,
        registry_refs=[],
    )


def _join_path(path: str, segment: str) -> str:
    if segment.startswith("["):
        return f"{path}{segment}"
    return f"{path}.{segment}" if path else segment


def _pascal_case(value: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", value)
    normalized_parts = [part.capitalize() for part in parts if part]
    return "".join(normalized_parts) or "Schema"


def _primitive_kind(value: JsonPrimitive) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    return "number"


class OutputSchemaValidationFailure(Exception):
    def __init__(self, issues: list[dict[str, str]]) -> None:
        super().__init__("Output schema validation failed")
        self.issues = issues


class OutputSchemaCompilerError(Exception):
    pass


@dataclass
class RegistryTarget:
    key: str
    version: int

    def __hash__(self) -> int:
        return hash((self.key, self.version))


@dataclass
class SchemaNodeBase:
    title: str | None
    description: str | None
    default_value: JsonValue | None
    has_default: bool
    nullable: bool


@dataclass
class SchemaPrimitive(SchemaNodeBase):
    schema_type: str


@dataclass
class SchemaEnum(SchemaNodeBase):
    values: tuple[JsonPrimitive, ...]


@dataclass
class SchemaLiteral(SchemaNodeBase):
    value: JsonPrimitive


@dataclass
class SchemaField:
    name: str
    required: bool
    schema: SchemaNode


@dataclass
class SchemaObject(SchemaNodeBase):
    fields: tuple[SchemaField, ...]


@dataclass
class SchemaArray(SchemaNodeBase):
    items: SchemaNode


@dataclass
class SchemaRef(SchemaNodeBase):
    key: str
    version: int


@dataclass
class SchemaDiscriminatedUnion(SchemaNodeBase):
    discriminator: str
    variants: tuple[SchemaNode, ...]


SchemaNode = (
    SchemaPrimitive
    | SchemaEnum
    | SchemaLiteral
    | SchemaObject
    | SchemaArray
    | SchemaRef
    | SchemaDiscriminatedUnion
)


@dataclass
class PreparedOutputSchema:
    json_schema: dict[str, Any]
    builder: OutputSchemaBuilderNode
    registry_refs: list[str]


class OutputSchemaCompiler:
    def __init__(self, registry_resolver: OutputSchemaRegistryResolver | None = None) -> None:
        self.registry_resolver = registry_resolver
        self._parsed_registry_cache: dict[RegistryTarget, SchemaNode] = {}
        self._runtime_model_cache: dict[tuple[str, int], type[BaseModel]] = {}

    def clear_caches(self) -> None:
        self._parsed_registry_cache.clear()
        self._runtime_model_cache.clear()

    def normalize_payload(
        self,
        *,
        builder: OutputSchemaBuilderNode | None,
        json_schema: dict[str, Any] | None,
    ) -> PreparedOutputSchema:
        issues: list[dict[str, str]] = []
        builder_node = (
            self._node_from_builder(builder, path="builder", seen_refs=(), issues=issues)
            if builder is not None
            else None
        )
        json_node = (
            self._node_from_json_schema(json_schema, path="jsonSchema", seen_refs=(), issues=issues)
            if json_schema is not None
            else None
        )
        if issues:
            raise OutputSchemaValidationFailure(issues)

        selected_node = builder_node or json_node
        if builder_node is not None and json_node is not None and builder_node != json_node:
            raise OutputSchemaValidationFailure(
                [
                    {"field": "builder", "issue": "Builder does not match jsonSchema"},
                    {"field": "jsonSchema", "issue": "jsonSchema does not match builder"},
                ]
            )
        if selected_node is None:
            raise OutputSchemaValidationFailure(
                [{"field": "jsonSchema", "issue": "A schema definition is required"}]
            )

        return PreparedOutputSchema(
            json_schema=self._node_to_json_schema(selected_node),
            builder=self._node_to_builder(selected_node),
            registry_refs=self._collect_direct_registry_refs(selected_node),
        )

    def render_stored_schema(self, schema: OutputSchemaLike) -> PreparedOutputSchema:
        issues: list[dict[str, str]] = []
        node = self._node_from_json_schema(
            schema.json_schema,
            path="jsonSchema",
            seen_refs=(
                (RegistryTarget(schema.key, schema.version),) if schema.kind == "shared" else ()
            ),
            issues=issues,
        )
        if issues:
            raise OutputSchemaValidationFailure(issues)
        return PreparedOutputSchema(
            json_schema=self._node_to_json_schema(node),
            builder=self._node_to_builder(node),
            registry_refs=self._collect_direct_registry_refs(node),
        )

    def parse_json_schema_node(
        self,
        json_schema: dict[str, Any],
        *,
        path: str = "jsonSchema",
    ) -> SchemaNode:
        issues: list[dict[str, str]] = []
        node = self._node_from_json_schema(
            json_schema,
            path=path,
            seen_refs=(),
            issues=issues,
        )
        if issues:
            raise OutputSchemaCompilerError(issues[0]["issue"])
        return node

    def parse_stored_schema_node(self, schema: OutputSchemaLike) -> SchemaNode:
        issues: list[dict[str, str]] = []
        node = self._node_from_json_schema(
            schema.json_schema,
            path=f"outputSchema[{schema.key}@{schema.version}]",
            seen_refs=(
                (RegistryTarget(schema.key, schema.version),) if schema.kind == "shared" else ()
            ),
            issues=issues,
        )
        if issues:
            raise OutputSchemaCompilerError(issues[0]["issue"])
        return node

    def build_runtime_model(self, schema: OutputSchemaLike) -> type[BaseModel]:
        cache_key = (schema.key, schema.version)
        cached_model = self._runtime_model_cache.get(cache_key)
        if cached_model is not None:
            return cached_model

        issues: list[dict[str, str]] = []
        node = self._node_from_json_schema(
            schema.json_schema,
            path=f"outputSchema[{schema.key}@{schema.version}]",
            seen_refs=(
                (RegistryTarget(schema.key, schema.version),) if schema.kind == "shared" else ()
            ),
            issues=issues,
        )
        if issues:
            raise OutputSchemaCompilerError(issues[0]["issue"])

        annotation = self._compile_annotation(
            node,
            model_name=self._model_name(schema.key, schema.version),
        )
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            model_type = annotation
        else:
            model_type = self._create_root_model(
                self._model_name(schema.key, schema.version), annotation
            )
        self._runtime_model_cache[cache_key] = model_type
        return model_type

    def _add_issue(self, issues: list[dict[str, str]], field: str, issue: str) -> None:
        issues.append({"field": field, "issue": issue})

    def _read_optional_string(
        self,
        value: object,
        *,
        path: str,
        field_name: str,
        issues: list[dict[str, str]],
    ) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            self._add_issue(issues, path, f"{field_name} must be a string")
            return None
        normalized = value.strip()
        return normalized or None

    def _builder_metadata(self, builder: OutputSchemaBuilderNode) -> dict[str, Any]:
        return {
            "title": builder.title,
            "description": builder.description,
            "default_value": builder.default_value,
            "has_default": "default_value" in builder.model_fields_set,
            "nullable": False,
        }

    def _json_schema_metadata(
        self,
        schema: dict[str, Any],
        *,
        path: str,
        issues: list[dict[str, str]],
    ) -> dict[str, Any]:
        default_value: JsonValue | None = None
        has_default = "default" in schema
        if has_default:
            default_value = self._parse_json_value(
                schema.get("default"),
                path=_join_path(path, "default"),
                issues=issues,
            )
        return {
            "title": self._read_optional_string(
                schema.get("title"),
                path=_join_path(path, "title"),
                field_name="title",
                issues=issues,
            ),
            "description": self._read_optional_string(
                schema.get("description"),
                path=_join_path(path, "description"),
                field_name="description",
                issues=issues,
            ),
            "default_value": default_value,
            "has_default": has_default,
            "nullable": False,
        }

    def _builder_metadata_kwargs(self, node: SchemaNodeBase) -> dict[str, Any]:
        metadata: dict[str, Any] = {"title": node.title, "description": node.description}
        if node.has_default:
            metadata["default_value"] = node.default_value
        return metadata

    def _placeholder_node(self) -> SchemaPrimitive:
        return SchemaPrimitive(
            title=None,
            description=None,
            default_value=None,
            has_default=False,
            nullable=False,
            schema_type="string",
        )

    def _schema_type_and_nullable(
        self,
        raw_type: object,
        *,
        path: str,
        issues: list[dict[str, str]],
    ) -> tuple[str | None, bool]:
        if isinstance(raw_type, str):
            return raw_type, False
        if isinstance(raw_type, list):
            raw_types = cast(list[object], raw_type)
            non_null_types = [item for item in raw_types if item != "null"]
            if len(raw_types) != 2 or len(non_null_types) != 1 or "null" not in raw_types:
                self._add_issue(
                    issues,
                    path,
                    "Nullable schema types must use exactly one schema type and 'null'",
                )
                return None, True
            schema_type = non_null_types[0]
            if not isinstance(schema_type, str):
                self._add_issue(issues, path, "Schema type entries must be strings")
                return None, True
            if schema_type not in {*_PRIMITIVE_TYPES, "array", "object"}:
                self._add_issue(
                    issues,
                    path,
                    "Nullable schema types support only primitive, array, and object schemas",
                )
                return None, True
            return schema_type, True
        self._add_issue(issues, path, "Schema type is required")
        return None, False

    def _with_validated_default(
        self,
        node: SchemaNode,
        *,
        path: str,
        default_key: str,
        seen_refs: tuple[RegistryTarget, ...],
        issues: list[dict[str, str]],
    ) -> SchemaNode:
        if node.has_default:
            self._validate_default_value(
                node.default_value,
                node,
                path=_join_path(path, default_key),
                seen_refs=seen_refs,
                issues=issues,
            )
        return node

    def _node_from_builder(
        self,
        builder: OutputSchemaBuilderNode,
        *,
        path: str,
        seen_refs: tuple[RegistryTarget, ...],
        issues: list[dict[str, str]],
    ) -> SchemaNode:
        metadata = self._builder_metadata(builder)
        node: SchemaNode
        if isinstance(builder, OutputSchemaBuilderString):
            node = SchemaPrimitive(schema_type="string", **metadata)
        elif isinstance(builder, OutputSchemaBuilderInteger):
            node = SchemaPrimitive(schema_type="integer", **metadata)
        elif isinstance(builder, OutputSchemaBuilderNumber):
            node = SchemaPrimitive(schema_type="number", **metadata)
        elif isinstance(builder, OutputSchemaBuilderBoolean):
            node = SchemaPrimitive(schema_type="boolean", **metadata)
        elif isinstance(builder, OutputSchemaBuilderEnum):
            node = SchemaEnum(values=tuple(builder.values), **metadata)
        elif isinstance(builder, OutputSchemaBuilderLiteral):
            node = SchemaLiteral(value=builder.value, **metadata)
        elif isinstance(builder, OutputSchemaBuilderObject):
            fields = tuple(
                SchemaField(
                    name=field.name,
                    required=field.required,
                    schema=self._node_from_builder(
                        field.definition,
                        path=_join_path(path, f"fields[{index}].schema"),
                        seen_refs=seen_refs,
                        issues=issues,
                    ),
                )
                for index, field in enumerate(builder.fields)
            )
            node = SchemaObject(
                fields=fields,
                **metadata,
            )
        elif isinstance(builder, OutputSchemaBuilderArray):
            node = SchemaArray(
                items=self._node_from_builder(
                    builder.items,
                    path=_join_path(path, "items"),
                    seen_refs=seen_refs,
                    issues=issues,
                ),
                **metadata,
            )
        elif isinstance(builder, OutputSchemaBuilderRef):
            target = self._resolve_registry_target(
                builder.schema_key,
                builder.schema_version,
                path=_join_path(path, "schemaKey"),
                issues=issues,
            )
            if target is None:
                return self._placeholder_node()
            self._load_registry_node_by_target(
                target,
                path=path,
                seen_refs=seen_refs,
                issues=issues,
            )
            node = SchemaRef(key=target.key, version=target.version, **metadata)
        else:
            variant_nodes = tuple(
                self._node_from_builder(
                    variant,
                    path=_join_path(path, f"variants[{index}]"),
                    seen_refs=seen_refs,
                    issues=issues,
                )
                for index, variant in enumerate(builder.variants)
            )
            self._validate_discriminator_variants(
                variant_nodes,
                builder.discriminator,
                path=path,
                variant_segment="variants",
                seen_refs=seen_refs,
                issues=issues,
            )
            node = SchemaDiscriminatedUnion(
                discriminator=builder.discriminator,
                variants=variant_nodes,
                **metadata,
            )
        return self._with_validated_default(
            node,
            path=path,
            default_key="defaultValue",
            seen_refs=seen_refs,
            issues=issues,
        )

    def _node_from_json_schema(
        self,
        schema: object,
        *,
        path: str,
        seen_refs: tuple[RegistryTarget, ...],
        issues: list[dict[str, str]],
    ) -> SchemaNode:
        if not isinstance(schema, dict):
            self._add_issue(issues, path, "Schema nodes must be objects")
            return self._placeholder_node()

        metadata = self._json_schema_metadata(schema, path=path, issues=issues)

        def with_default(node: SchemaNode) -> SchemaNode:
            return self._with_validated_default(
                node,
                path=path,
                default_key="default",
                seen_refs=seen_refs,
                issues=issues,
            )

        for key, message in (
            ("allOf", "allOf is not supported"),
            ("if", "if/then/else is not supported"),
            ("then", "if/then/else is not supported"),
            ("else", "if/then/else is not supported"),
            ("not", "not is not supported"),
            ("oneOf", "Only discriminated anyOf unions are supported"),
        ):
            if key in schema:
                self._add_issue(issues, _join_path(path, key), message)

        if "$ref" in schema:
            self._validate_allowed_keys(
                schema,
                allowed_keys={"$ref", "title", "description", "default"},
                path=path,
                issues=issues,
            )
            target = self._parse_registry_ref(schema.get("$ref"), path=path, issues=issues)
            if target is None:
                return self._placeholder_node()
            self._load_registry_node_by_target(
                target,
                path=path,
                seen_refs=seen_refs,
                issues=issues,
            )
            return with_default(SchemaRef(key=target.key, version=target.version, **metadata))

        if "anyOf" in schema:
            self._validate_allowed_keys(
                schema,
                allowed_keys={"anyOf", "discriminator", "title", "description", "default"},
                path=path,
                issues=issues,
            )
            if "discriminator" not in schema:
                self._add_issue(
                    issues,
                    _join_path(path, "anyOf"),
                    "Undiscriminated unions are not supported",
                )
            raw_variants = schema.get("anyOf")
            if not isinstance(raw_variants, list) or len(raw_variants) < 2:
                self._add_issue(
                    issues,
                    _join_path(path, "anyOf"),
                    "Discriminated unions must include at least two variants",
                )
                return self._placeholder_node()
            discriminator = self._parse_discriminator(
                schema.get("discriminator"),
                path=_join_path(path, "discriminator"),
                issues=issues,
            )
            variant_nodes = tuple(
                self._node_from_json_schema(
                    variant,
                    path=_join_path(path, f"anyOf[{index}]"),
                    seen_refs=seen_refs,
                    issues=issues,
                )
                for index, variant in enumerate(raw_variants)
            )
            if discriminator is None:
                return self._placeholder_node()
            self._validate_discriminator_variants(
                variant_nodes,
                discriminator,
                path=path,
                variant_segment="anyOf",
                seen_refs=seen_refs,
                issues=issues,
            )
            return with_default(
                SchemaDiscriminatedUnion(
                    discriminator=discriminator,
                    variants=variant_nodes,
                    **metadata,
                )
            )

        if "const" in schema:
            self._validate_allowed_keys(
                schema,
                allowed_keys={"const", "type", "title", "description", "default"},
                path=path,
                issues=issues,
            )
            value = self._parse_json_primitive(
                schema.get("const"),
                path=_join_path(path, "const"),
                issues=issues,
            )
            self._validate_declared_primitive_type(
                schema.get("type"),
                expected_type=_primitive_kind(value) if value is not None else None,
                path=_join_path(path, "type"),
                issues=issues,
            )
            if value is None:
                return self._placeholder_node()
            return with_default(SchemaLiteral(value=value, **metadata))

        if "enum" in schema:
            self._validate_allowed_keys(
                schema,
                allowed_keys={"enum", "type", "title", "description", "default"},
                path=path,
                issues=issues,
            )
            raw_values = schema.get("enum")
            if not isinstance(raw_values, list) or not raw_values:
                self._add_issue(
                    issues,
                    _join_path(path, "enum"),
                    "Enum values must be a non-empty array",
                )
                return self._placeholder_node()
            values: list[JsonPrimitive] = []
            for index, item in enumerate(raw_values):
                parsed_value = self._parse_json_primitive(
                    item,
                    path=_join_path(path, f"enum[{index}]"),
                    issues=issues,
                )
                if parsed_value is not None:
                    values.append(parsed_value)
            if values and len({_primitive_kind(item) for item in values}) != 1:
                self._add_issue(
                    issues,
                    _join_path(path, "enum"),
                    "Enum values must all use the same primitive type",
                )
            declared_type: str | None = None
            nullable = False
            if "type" in schema:
                declared_type, nullable = self._schema_type_and_nullable(
                    schema.get("type"),
                    path=_join_path(path, "type"),
                    issues=issues,
                )
                if declared_type is None:
                    return self._placeholder_node()
            self._validate_declared_primitive_type(
                declared_type,
                expected_type=_primitive_kind(values[0]) if values else None,
                path=_join_path(path, "type"),
                issues=issues,
            )
            if not values:
                return self._placeholder_node()
            metadata["nullable"] = nullable
            return with_default(SchemaEnum(values=tuple(values), **metadata))

        schema_type, nullable = self._schema_type_and_nullable(
            schema.get("type"),
            path=_join_path(path, "type"),
            issues=issues,
        )
        if schema_type is None:
            return self._placeholder_node()
        metadata["nullable"] = nullable
        if schema_type in _PRIMITIVE_TYPES:
            self._validate_allowed_keys(
                schema,
                allowed_keys={"type", "title", "description", "default"},
                path=path,
                issues=issues,
            )
            return with_default(SchemaPrimitive(schema_type=schema_type, **metadata))
        if schema_type == "array":
            self._validate_allowed_keys(
                schema,
                allowed_keys={"type", "items", "title", "description", "default"},
                path=path,
                issues=issues,
            )
            raw_items = schema.get("items")
            if isinstance(raw_items, list):
                self._add_issue(
                    issues,
                    _join_path(path, "items"),
                    "Tuple arrays are not supported",
                )
                return self._placeholder_node()
            if raw_items is None:
                self._add_issue(issues, _join_path(path, "items"), "Array items are required")
                return self._placeholder_node()
            return with_default(
                SchemaArray(
                    items=self._node_from_json_schema(
                        raw_items,
                        path=_join_path(path, "items"),
                        seen_refs=seen_refs,
                        issues=issues,
                    ),
                    **metadata,
                )
            )
        if schema_type == "object":
            self._validate_allowed_keys(
                schema,
                allowed_keys={
                    "type",
                    "properties",
                    "required",
                    "title",
                    "description",
                    "default",
                },
                path=path,
                issues=issues,
            )
            properties = schema.get("properties", {})
            if not isinstance(properties, dict):
                self._add_issue(
                    issues,
                    _join_path(path, "properties"),
                    "Object properties must be an object",
                )
                return self._placeholder_node()
            raw_required = schema.get("required", [])
            if not isinstance(raw_required, list):
                self._add_issue(
                    issues,
                    _join_path(path, "required"),
                    "Required fields must be an array",
                )
                raw_required = []
            required_names: set[str] = set()
            for index, item in enumerate(raw_required):
                if not isinstance(item, str) or not item.strip():
                    self._add_issue(
                        issues,
                        _join_path(path, f"required[{index}]"),
                        "Required field names must be non-empty strings",
                    )
                    continue
                required_names.add(item)
            fields = tuple(
                SchemaField(
                    name=name,
                    required=name in required_names,
                    schema=self._node_from_json_schema(
                        child_schema,
                        path=_join_path(path, f"properties.{name}"),
                        seen_refs=seen_refs,
                        issues=issues,
                    ),
                )
                for name, child_schema in properties.items()
            )
            defined_names = {field.name for field in fields}
            for name in sorted(required_names - defined_names):
                self._add_issue(
                    issues,
                    _join_path(path, "required"),
                    f"Required field {name!r} is not defined in properties",
                )
            return with_default(
                SchemaObject(
                    fields=fields,
                    **metadata,
                )
            )

        self._add_issue(
            issues,
            _join_path(path, "type"),
            f"Schema type {schema_type!r} is not supported",
        )
        return self._placeholder_node()

    def _validate_allowed_keys(
        self,
        schema: dict[str, Any],
        *,
        allowed_keys: set[str],
        path: str,
        issues: list[dict[str, str]],
    ) -> None:
        for key in sorted(set(schema) - allowed_keys):
            message = {
                "allOf": "allOf is not supported",
                "if": "if/then/else is not supported",
                "then": "if/then/else is not supported",
                "else": "if/then/else is not supported",
                "not": "not is not supported",
                "oneOf": "Only discriminated anyOf unions are supported",
                "patternProperties": "patternProperties is not supported",
            }.get(key, f"Keyword {key!r} is not supported")
            self._add_issue(issues, _join_path(path, key), message)

    def _parse_json_primitive(
        self,
        value: object,
        *,
        path: str,
        issues: list[dict[str, str]],
    ) -> JsonPrimitive | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return value
        self._add_issue(issues, path, "Values must be JSON primitives")
        return None

    def _parse_json_value(
        self,
        value: object,
        *,
        path: str,
        issues: list[dict[str, str]],
    ) -> JsonValue:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return value
        if isinstance(value, list):
            return [
                self._parse_json_value(
                    item,
                    path=_join_path(path, f"[{index}]"),
                    issues=issues,
                )
                for index, item in enumerate(value)
            ]
        if isinstance(value, dict):
            parsed: dict[str, JsonValue] = {}
            for index, (key, item) in enumerate(value.items()):
                if not isinstance(key, str):
                    self._add_issue(
                        issues,
                        _join_path(path, f"[{index}].key"),
                        "Default object keys must be strings",
                    )
                    continue
                parsed[key] = self._parse_json_value(
                    item,
                    path=_join_path(path, key),
                    issues=issues,
                )
            return parsed
        self._add_issue(issues, path, "Default values must be valid JSON values")
        return None

    def _validate_default_value(
        self,
        value: JsonValue | None,
        node: SchemaNode,
        *,
        path: str,
        seen_refs: tuple[RegistryTarget, ...],
        issues: list[dict[str, str]],
    ) -> None:
        if value is None:
            self._add_issue(issues, path, "Null defaults are not supported")
            return
        if isinstance(node, SchemaPrimitive):
            self._validate_primitive_default(value, node.schema_type, path=path, issues=issues)
            return
        if isinstance(node, SchemaEnum):
            if not any(self._json_values_equal(value, candidate) for candidate in node.values):
                self._add_issue(issues, path, "Default value must equal one enum value")
            return
        if isinstance(node, SchemaLiteral):
            if not self._json_values_equal(value, node.value):
                self._add_issue(issues, path, "Default value must equal the literal value")
            return
        if isinstance(node, SchemaArray):
            if not isinstance(value, list):
                self._add_issue(issues, path, "Default value must match schema type 'array'")
                return
            for index, item in enumerate(value):
                self._validate_default_value(
                    item,
                    node.items,
                    path=_join_path(path, f"[{index}]"),
                    seen_refs=seen_refs,
                    issues=issues,
                )
            return
        if isinstance(node, SchemaObject):
            self._validate_object_default(
                value,
                node,
                path=path,
                seen_refs=seen_refs,
                issues=issues,
            )
            return
        if isinstance(node, SchemaRef):
            target = RegistryTarget(node.key, node.version)
            resolved_node = self._load_registry_node_by_target(
                target,
                path=path,
                seen_refs=seen_refs,
                issues=issues,
            )
            self._validate_default_value(
                value,
                resolved_node,
                path=path,
                seen_refs=seen_refs + (target,),
                issues=issues,
            )
            return
        self._validate_discriminated_union_default(
            value,
            node,
            path=path,
            seen_refs=seen_refs,
            issues=issues,
        )

    def _validate_primitive_default(
        self,
        value: JsonValue,
        schema_type: str,
        *,
        path: str,
        issues: list[dict[str, str]],
    ) -> None:
        valid = False
        if schema_type == "string":
            valid = isinstance(value, str)
        elif schema_type == "integer":
            valid = isinstance(value, int) and not isinstance(value, bool)
        elif schema_type == "number":
            valid = self._is_finite_json_number(value)
        elif schema_type == "boolean":
            valid = isinstance(value, bool)
        if not valid:
            self._add_issue(issues, path, f"Default value must match schema type {schema_type!r}")

    def _validate_object_default(
        self,
        value: JsonValue,
        node: SchemaObject,
        *,
        path: str,
        seen_refs: tuple[RegistryTarget, ...],
        issues: list[dict[str, str]],
    ) -> None:
        if not isinstance(value, dict):
            self._add_issue(issues, path, "Default value must match schema type 'object'")
            return
        fields_by_name = {field.name: field for field in node.fields}
        for field in node.fields:
            if field.required and field.name not in value:
                self._add_issue(
                    issues,
                    _join_path(path, field.name),
                    f"Default object is missing required field {field.name!r}",
                )
        for key, item in value.items():
            schema_field = fields_by_name.get(key)
            item_path = _join_path(path, key)
            if schema_field is None:
                self._add_issue(
                    issues,
                    item_path,
                    f"Default object field {key!r} is not defined",
                )
                continue
            self._validate_default_value(
                item,
                schema_field.schema,
                path=item_path,
                seen_refs=seen_refs,
                issues=issues,
            )

    def _validate_discriminated_union_default(
        self,
        value: JsonValue,
        node: SchemaDiscriminatedUnion,
        *,
        path: str,
        seen_refs: tuple[RegistryTarget, ...],
        issues: list[dict[str, str]],
    ) -> None:
        if not isinstance(value, dict):
            self._add_issue(issues, path, "Default value must match discriminated union schema")
            return
        discriminator_path = _join_path(path, node.discriminator)
        if node.discriminator not in value:
            self._add_issue(
                issues,
                discriminator_path,
                f"Default object must include discriminator field {node.discriminator!r}",
            )
            return
        discriminator_value = value[node.discriminator]
        if discriminator_value is None:
            self._add_issue(issues, discriminator_path, "Null defaults are not supported")
            return
        matches: list[SchemaNode] = []
        for variant in node.variants:
            variant_issues: list[dict[str, str]] = []
            tag = self._extract_discriminator_tag(
                variant,
                node.discriminator,
                path=path,
                seen_refs=seen_refs,
                issues=variant_issues,
            )
            if tag is not None and self._json_values_equal(discriminator_value, tag):
                matches.append(variant)
        if len(matches) != 1:
            self._add_issue(
                issues,
                discriminator_path,
                "Default discriminator value must match exactly one variant",
            )
            return
        self._validate_default_value(
            value,
            matches[0],
            path=path,
            seen_refs=seen_refs,
            issues=issues,
        )

    @staticmethod
    def _is_finite_json_number(value: JsonValue) -> bool:
        if isinstance(value, bool):
            return False
        if isinstance(value, (int, float)):
            return isfinite(value)
        return False

    @staticmethod
    def _json_values_equal(left: JsonValue | None, right: JsonPrimitive) -> bool:
        if isinstance(left, bool) or isinstance(right, bool):
            return isinstance(left, bool) and isinstance(right, bool) and left == right
        return left == right

    def _validate_declared_primitive_type(
        self,
        declared_type: object,
        *,
        expected_type: str | None,
        path: str,
        issues: list[dict[str, str]],
    ) -> None:
        if declared_type is None or expected_type is None:
            return
        if not isinstance(declared_type, str):
            self._add_issue(issues, path, "Schema type must be a string")
            return
        if declared_type != expected_type:
            self._add_issue(
                issues,
                path,
                f"Declared type {declared_type!r} does not match the literal or enum values",
            )

    def _parse_discriminator(
        self,
        raw_discriminator: object,
        *,
        path: str,
        issues: list[dict[str, str]],
    ) -> str | None:
        if isinstance(raw_discriminator, str):
            normalized = raw_discriminator.strip()
            if normalized:
                return normalized
        elif isinstance(raw_discriminator, dict):
            property_name = raw_discriminator.get("propertyName")
            if isinstance(property_name, str) and property_name.strip():
                return property_name.strip()
        self._add_issue(issues, path, "Discriminator must define propertyName")
        return None

    def _parse_registry_ref(
        self,
        raw_ref: object,
        *,
        path: str,
        issues: list[dict[str, str]],
    ) -> RegistryTarget | None:
        if not isinstance(raw_ref, str):
            self._add_issue(issues, _join_path(path, "$ref"), "Registry refs must be strings")
            return None
        match = _REGISTRY_REF_RE.fullmatch(raw_ref.strip())
        if match is None:
            self._add_issue(
                issues,
                _join_path(path, "$ref"),
                "Registry refs must use registry://<key> or registry://<key>@<version>",
            )
            return None
        version = int(match.group("version")) if match.group("version") is not None else None
        return self._resolve_registry_target(
            match.group("key"),
            version,
            path=_join_path(path, "$ref"),
            issues=issues,
        )

    def _resolve_registry_target(
        self,
        key: str,
        version: int | None,
        *,
        path: str,
        issues: list[dict[str, str]],
    ) -> RegistryTarget | None:
        if self.registry_resolver is None:
            self._add_issue(
                issues,
                path,
                "Shared registry refs are not supported in package-local schemas",
            )
            return None
        row = self.registry_resolver.resolve_registry_ref(key, version)
        if row is None:
            issue = (
                f"Shared registry ref {key!r} v{version} was not found"
                if version is not None
                else f"Published shared registry ref {key!r} was not found"
            )
            self._add_issue(issues, path, issue)
            return None
        return RegistryTarget(key=row.key, version=row.version)

    def _load_registry_node_by_target(
        self,
        target: RegistryTarget,
        *,
        path: str,
        seen_refs: tuple[RegistryTarget, ...],
        issues: list[dict[str, str]],
    ) -> SchemaNode:
        if target in seen_refs:
            self._add_issue(
                issues,
                _join_path(path, "$ref"),
                "Recursive shared registry refs are not supported",
            )
            return self._placeholder_node()
        cached_node = self._parsed_registry_cache.get(target)
        if cached_node is not None:
            return cached_node
        if self.registry_resolver is None:
            self._add_issue(
                issues,
                _join_path(path, "$ref"),
                "Shared registry refs are not supported in package-local schemas",
            )
            return self._placeholder_node()
        row = self.registry_resolver.resolve_registry_ref(target.key, target.version)
        if row is None:
            self._add_issue(
                issues,
                _join_path(path, "$ref"),
                f"Shared registry ref {target.key!r} v{target.version} was not found",
            )
            return self._placeholder_node()
        node = self._node_from_json_schema(
            row.json_schema,
            path=f"registry[{target.key}@{target.version}]",
            seen_refs=seen_refs + (target,),
            issues=issues,
        )
        self._parsed_registry_cache[target] = node
        return node

    def _validate_discriminator_variants(
        self,
        variants: tuple[SchemaNode, ...],
        discriminator: str,
        *,
        path: str,
        variant_segment: str,
        seen_refs: tuple[RegistryTarget, ...],
        issues: list[dict[str, str]],
    ) -> None:
        seen_tags: dict[JsonPrimitive, int] = {}
        for index, variant in enumerate(variants):
            variant_path = _join_path(path, f"{variant_segment}[{index}]")
            tag = self._extract_discriminator_tag(
                variant,
                discriminator,
                path=variant_path,
                seen_refs=seen_refs,
                issues=issues,
            )
            if tag is None:
                continue
            if tag in seen_tags:
                self._add_issue(
                    issues,
                    variant_path,
                    f"Duplicate discriminator value {tag!r} is not allowed",
                )
                continue
            seen_tags[tag] = index

    def _extract_discriminator_tag(
        self,
        node: SchemaNode,
        discriminator: str,
        *,
        path: str,
        seen_refs: tuple[RegistryTarget, ...],
        issues: list[dict[str, str]],
    ) -> JsonPrimitive | None:
        if isinstance(node, SchemaRef):
            resolved_node = self._load_registry_node_by_target(
                RegistryTarget(node.key, node.version),
                path=path,
                seen_refs=seen_refs,
                issues=issues,
            )
            return self._extract_discriminator_tag(
                resolved_node,
                discriminator,
                path=path,
                seen_refs=seen_refs + (RegistryTarget(node.key, node.version),),
                issues=issues,
            )
        if not isinstance(node, SchemaObject):
            self._add_issue(
                issues,
                path,
                "Discriminated union variants must resolve to object schemas",
            )
            return None
        matching_field = next((field for field in node.fields if field.name == discriminator), None)
        if matching_field is None or not matching_field.required:
            self._add_issue(
                issues,
                path,
                f"Variant must require discriminator field {discriminator!r}",
            )
            return None
        return self._extract_literal_tag(
            matching_field.schema,
            path=_join_path(path, f"properties.{discriminator}"),
            seen_refs=seen_refs,
            issues=issues,
        )

    def _extract_literal_tag(
        self,
        node: SchemaNode,
        *,
        path: str,
        seen_refs: tuple[RegistryTarget, ...],
        issues: list[dict[str, str]],
    ) -> JsonPrimitive | None:
        if isinstance(node, SchemaLiteral):
            return node.value
        if isinstance(node, SchemaEnum) and len(node.values) == 1:
            return node.values[0]
        if isinstance(node, SchemaRef):
            resolved_node = self._load_registry_node_by_target(
                RegistryTarget(node.key, node.version),
                path=path,
                seen_refs=seen_refs,
                issues=issues,
            )
            return self._extract_literal_tag(
                resolved_node,
                path=path,
                seen_refs=seen_refs + (RegistryTarget(node.key, node.version),),
                issues=issues,
            )
        self._add_issue(
            issues,
            path,
            "Discriminator fields must use const or a single-value enum",
        )
        return None

    def _node_to_builder(self, node: SchemaNode) -> OutputSchemaBuilderNode:
        metadata = self._builder_metadata_kwargs(node)
        if isinstance(node, SchemaPrimitive):
            if node.schema_type == "string":
                return OutputSchemaBuilderString(**metadata)
            if node.schema_type == "integer":
                return OutputSchemaBuilderInteger(**metadata)
            if node.schema_type == "number":
                return OutputSchemaBuilderNumber(**metadata)
            return OutputSchemaBuilderBoolean(**metadata)
        if isinstance(node, SchemaEnum):
            return OutputSchemaBuilderEnum(values=list(node.values), **metadata)
        if isinstance(node, SchemaLiteral):
            return OutputSchemaBuilderLiteral(value=node.value, **metadata)
        if isinstance(node, SchemaObject):
            return OutputSchemaBuilderObject(
                fields=[
                    OutputSchemaBuilderField(
                        name=field.name,
                        required=field.required,
                        schema=self._node_to_builder(field.schema),
                    )
                    for field in node.fields
                ],
                **metadata,
            )
        if isinstance(node, SchemaArray):
            return OutputSchemaBuilderArray(
                items=self._node_to_builder(node.items),
                **metadata,
            )
        if isinstance(node, SchemaRef):
            return OutputSchemaBuilderRef(
                schema_key=node.key,
                schema_version=node.version,
                **metadata,
            )
        return OutputSchemaBuilderDiscriminatedUnion(
            discriminator=node.discriminator,
            variants=[self._node_to_builder(variant) for variant in node.variants],
            **metadata,
        )

    @staticmethod
    def _json_schema_type(schema_type: str, *, nullable: bool) -> str | list[str]:
        if nullable:
            return [schema_type, "null"]
        return schema_type

    def _node_to_json_schema(self, node: SchemaNode) -> dict[str, Any]:
        if isinstance(node, SchemaPrimitive):
            payload: dict[str, Any] = {
                "type": self._json_schema_type(node.schema_type, nullable=node.nullable)
            }
            return self._with_metadata(payload, node)
        if isinstance(node, SchemaEnum):
            payload = {
                "type": self._json_schema_type(
                    _primitive_kind(node.values[0]), nullable=node.nullable
                ),
                "enum": list(node.values),
            }
            return self._with_metadata(payload, node)
        if isinstance(node, SchemaLiteral):
            payload = {"type": _primitive_kind(node.value), "const": node.value}
            return self._with_metadata(payload, node)
        if isinstance(node, SchemaObject):
            payload = {
                "type": self._json_schema_type("object", nullable=node.nullable),
                "properties": {
                    field.name: self._node_to_json_schema(field.schema) for field in node.fields
                },
                "required": [field.name for field in node.fields if field.required],
            }
            return self._with_metadata(payload, node)
        if isinstance(node, SchemaArray):
            payload = {
                "type": self._json_schema_type("array", nullable=node.nullable),
                "items": self._node_to_json_schema(node.items),
            }
            return self._with_metadata(payload, node)
        if isinstance(node, SchemaRef):
            payload = {"$ref": f"registry://{node.key}@{node.version}"}
            return self._with_metadata(payload, node)
        payload = {
            "anyOf": [self._node_to_json_schema(variant) for variant in node.variants],
            "discriminator": {"propertyName": node.discriminator},
        }
        return self._with_metadata(payload, node)

    def _with_metadata(self, payload: dict[str, Any], node: SchemaNodeBase) -> dict[str, Any]:
        if node.title is not None:
            payload["title"] = node.title
        if node.description is not None:
            payload["description"] = node.description
        if node.has_default:
            payload["default"] = node.default_value
        return payload

    def _collect_direct_registry_refs(self, node: SchemaNode) -> list[str]:
        refs: list[str] = []
        self._collect_direct_registry_refs_into(node, refs, seen_keys=set())
        return refs

    def _collect_direct_registry_refs_into(
        self,
        node: SchemaNode,
        refs: list[str],
        *,
        seen_keys: set[str],
    ) -> None:
        if isinstance(node, SchemaRef):
            if node.key not in seen_keys:
                refs.append(node.key)
                seen_keys.add(node.key)
            return
        if isinstance(node, SchemaObject):
            for field in node.fields:
                self._collect_direct_registry_refs_into(field.schema, refs, seen_keys=seen_keys)
            return
        if isinstance(node, SchemaArray):
            self._collect_direct_registry_refs_into(node.items, refs, seen_keys=seen_keys)
            return
        if isinstance(node, SchemaDiscriminatedUnion):
            for variant in node.variants:
                self._collect_direct_registry_refs_into(variant, refs, seen_keys=seen_keys)

    def _compile_annotation(self, node: SchemaNode, *, model_name: str) -> Any:
        if isinstance(node, SchemaPrimitive):
            annotation = {
                "string": str,
                "integer": int,
                "number": float,
                "boolean": bool,
            }[node.schema_type]
        elif isinstance(node, SchemaEnum):
            if not node.values:
                raise OutputSchemaCompilerError("Enum schemas must include at least one value")
            annotation = cast(Any, Literal)[node.values]
        elif isinstance(node, SchemaLiteral):
            annotation = cast(Any, Literal)[(node.value,)]
        elif isinstance(node, SchemaObject):
            annotation = self._compile_object_model(node, model_name=model_name)
        elif isinstance(node, SchemaArray):
            item_annotation = self._compile_annotation(
                node.items,
                model_name=f"{model_name}Item",
            )
            annotation = cast(Any, list)[item_annotation]
        elif isinstance(node, SchemaRef):
            if self.registry_resolver is None:
                raise OutputSchemaCompilerError(
                    "Shared registry refs are not supported in package-local schemas"
                )
            row = self.registry_resolver.resolve_registry_ref(node.key, node.version)
            if row is None:
                raise OutputSchemaCompilerError(
                    f"Shared registry ref {node.key!r} v{node.version} was not found"
                )
            annotation = self.build_runtime_model(row)
        else:
            annotation = self._compile_discriminated_union(node, model_name=model_name)
        if node.nullable:
            return annotation | None
        return annotation

    def _compile_object_model(
        self,
        node: SchemaObject,
        *,
        model_name: str,
    ) -> type[BaseModel]:
        field_definitions: dict[str, tuple[Any, Any]] = {}
        for field in node.fields:
            annotation = self._compile_annotation(
                field.schema,
                model_name=f"{model_name}{_pascal_case(field.name)}",
            )
            if field.required:
                pydantic_field = Field(
                    default=...,
                    title=field.schema.title,
                    description=field.schema.description,
                )
            elif field.schema.has_default and isinstance(field.schema.default_value, (dict, list)):
                default_value = field.schema.default_value
                pydantic_field = Field(
                    default_factory=lambda value=default_value: deepcopy(value),
                    title=field.schema.title,
                    description=field.schema.description,
                )
            elif field.schema.has_default:
                pydantic_field = Field(
                    default=field.schema.default_value,
                    title=field.schema.title,
                    description=field.schema.description,
                )
            else:
                pydantic_field = Field(
                    default=None,
                    title=field.schema.title,
                    description=field.schema.description,
                )
            field_definitions[field.name] = (annotation, pydantic_field)
        create_model_fn = cast(Any, create_model)
        return cast(
            type[BaseModel],
            create_model_fn(
                model_name,
                __config__=ConfigDict(extra="forbid"),
                __module__=__name__,
                **field_definitions,
            ),
        )

    def _compile_discriminated_union(
        self,
        node: SchemaDiscriminatedUnion,
        *,
        model_name: str,
    ) -> Any:
        variant_models: list[type[BaseModel]] = []
        for index, variant in enumerate(node.variants, start=1):
            annotation = self._compile_annotation(
                variant,
                model_name=f"{model_name}Variant{index}",
            )
            if not isinstance(annotation, type) or not issubclass(annotation, BaseModel):
                raise OutputSchemaCompilerError(
                    "Discriminated union variants must compile to Pydantic models"
                )
            variant_models.append(annotation)
        union_members = cast(Any, variant_models[0])
        for variant_model in variant_models[1:]:
            union_members = union_members | variant_model
        return cast(Any, Annotated)[
            union_members,
            Field(discriminator=node.discriminator),
        ]

    def _create_root_model(self, model_name: str, annotation: Any) -> type[BaseModel]:
        return type(
            model_name,
            (RootModel[annotation],),
            {
                "__module__": __name__,
                "model_config": ConfigDict(title=model_name),
            },
        )

    def _model_name(self, key: str, version: int) -> str:
        return f"OutputSchema{_pascal_case(key)}V{version}"


__all__ = [
    "OutputSchemaCompiler",
    "OutputSchemaLike",
    "PackageOutputSchemaCandidate",
    "OutputSchemaCompilerError",
    "OutputSchemaValidationFailure",
    "PreparedOutputSchema",
    "package_output_schema_candidate",
]
