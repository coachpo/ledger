from __future__ import annotations

from collections.abc import Collection, Sequence

from app.agents.mcp.tool_adapter import (
    ExecutionToolDescriptor,
    build_native_runtime_tool_descriptor,
    execution_tool_descriptor_to_openai_tool,
    execution_tool_descriptor_to_signaldeck_tool_declaration,
)
from app.agents.runtime_tools.declarations import SignalDeckToolDeclaration
from app.agents.runtime_tools.types import RuntimeToolContext, RuntimeToolError, RuntimeToolSpec


class RuntimeToolRegistry:
    def __init__(
        self,
        specs: Sequence[RuntimeToolSpec],
        *,
        enabled_extension_keys: Collection[str] | None = None,
    ) -> None:
        self._specs: tuple[RuntimeToolSpec, ...] = tuple(
            sorted(specs, key=lambda spec: (spec.sort_order, spec.key))
        )
        self._enabled_extension_keys: frozenset[str] | None = (
            None if enabled_extension_keys is None else frozenset(enabled_extension_keys)
        )
        self._specs_by_openai_function_name: dict[str, RuntimeToolSpec] = {}
        self._descriptors_by_openai_function_name: dict[str, ExecutionToolDescriptor] = {}
        self._validate_unique_specs(self._specs)
        for spec in self._specs:
            self._specs_by_openai_function_name[spec.openai_function_name] = spec
            self._descriptors_by_openai_function_name[spec.openai_function_name] = (
                self._descriptor_for_spec(spec)
            )

    def list_specs(self) -> tuple[RuntimeToolSpec, ...]:
        return self._specs

    def list_enabled_specs(self) -> tuple[RuntimeToolSpec, ...]:
        return tuple(spec for spec in self._specs if self._is_enabled_spec(spec))

    def list_execution_descriptors(self) -> tuple[ExecutionToolDescriptor, ...]:
        return tuple(
            self._descriptors_by_openai_function_name[spec.openai_function_name]
            for spec in self._specs
        )

    def get_execution_descriptors(
        self,
        granted_tool_keys: Collection[str],
    ) -> tuple[ExecutionToolDescriptor, ...]:
        return tuple(
            self._descriptors_by_openai_function_name[spec.openai_function_name]
            for spec in self._specs
            if spec.key in granted_tool_keys and self._is_enabled_spec(spec)
        )

    def get_tool_declarations(
        self,
        granted_tool_keys: Collection[str],
    ) -> tuple[SignalDeckToolDeclaration, ...]:
        return tuple(
            execution_tool_descriptor_to_signaldeck_tool_declaration(descriptor)
            for descriptor in self.get_execution_descriptors(granted_tool_keys)
        )

    def get_openai_tools(
        self,
        granted_tool_keys: Collection[str],
    ) -> list[dict[str, object]]:
        return [
            execution_tool_descriptor_to_openai_tool(descriptor)
            for descriptor in self.get_execution_descriptors(granted_tool_keys)
        ]

    def get_guidance(self, granted_tool_keys: Collection[str]) -> str:
        return "\n\n".join(
            spec.guidance
            for spec in self._specs
            if spec.key in granted_tool_keys and spec.guidance and self._is_enabled_spec(spec)
        )

    def dispatch(
        self,
        *,
        name: str,
        arguments_json: str,
        granted_tool_keys: Collection[str],
        context: RuntimeToolContext,
    ) -> dict[str, object]:
        spec = self._specs_by_openai_function_name.get(name)
        if spec is None:
            raise RuntimeToolError(
                code="agent_tool_call_unsupported",
                message=f"Agent requested unsupported server tool {name!r}.",
            )
        if not self._is_enabled_spec(spec):
            raise self._disabled_tool_error(spec)
        if spec.key not in granted_tool_keys:
            raise RuntimeToolError(code=spec.denied_code, message=spec.denied_message)
        arguments = spec.parser(arguments_json)
        return spec.executor(context, arguments)

    def _is_enabled_spec(self, spec: RuntimeToolSpec) -> bool:
        if self._enabled_extension_keys is None or spec.owner_extension_key is None:
            return True
        return spec.owner_extension_key in self._enabled_extension_keys

    @staticmethod
    def _disabled_tool_error(spec: RuntimeToolSpec) -> RuntimeToolError:
        extension_key = spec.owner_extension_key or "unknown"
        return RuntimeToolError(
            code="extension_disabled",
            message="Extension is disabled",
            details=[
                {
                    "extensionKey": extension_key,
                    "surface": f"runtime.tool.{spec.key}",
                }
            ],
        )

    @staticmethod
    def _descriptor_for_spec(spec: RuntimeToolSpec) -> ExecutionToolDescriptor:
        return build_native_runtime_tool_descriptor(
            key=spec.key,
            openai_function_name=spec.openai_function_name,
            description=spec.description,
            parameters_schema=spec.parameters_schema,
            owner_extension_key=spec.owner_extension_key,
        )

    @staticmethod
    def _validate_unique_specs(specs: Sequence[RuntimeToolSpec]) -> None:
        seen_keys: set[str] = set()
        seen_openai_function_names: set[str] = set()
        for spec in specs:
            if spec.key in seen_keys:
                raise ValueError(f"Duplicate runtime tool key {spec.key!r}.")
            if spec.openai_function_name in seen_openai_function_names:
                raise ValueError(
                    f"Duplicate runtime tool OpenAI function name {spec.openai_function_name!r}."
                )
            seen_keys.add(spec.key)
            seen_openai_function_names.add(spec.openai_function_name)


__all__ = ["RuntimeToolRegistry"]
