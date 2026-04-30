from __future__ import annotations

from collections.abc import Collection, Sequence
from copy import deepcopy

from app.agents.runtime_tools.types import RuntimeToolContext, RuntimeToolError, RuntimeToolSpec


class RuntimeToolRegistry:
    def __init__(self, specs: Sequence[RuntimeToolSpec]) -> None:
        self._specs: tuple[RuntimeToolSpec, ...] = tuple(
            sorted(specs, key=lambda spec: (spec.sort_order, spec.key))
        )
        self._specs_by_openai_function_name: dict[str, RuntimeToolSpec] = {}
        self._validate_unique_specs(self._specs)
        for spec in self._specs:
            self._specs_by_openai_function_name[spec.openai_function_name] = spec

    def list_specs(self) -> tuple[RuntimeToolSpec, ...]:
        return self._specs

    def get_openai_tool_definitions(
        self,
        granted_tool_keys: Collection[str],
    ) -> list[dict[str, object]]:
        return [
            self._build_openai_tool_definition(spec)
            for spec in self._specs
            if spec.key in granted_tool_keys
        ]

    def get_guidance(self, granted_tool_keys: Collection[str]) -> str:
        return "\n\n".join(
            spec.guidance for spec in self._specs if spec.key in granted_tool_keys and spec.guidance
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
        if spec.key not in granted_tool_keys:
            raise RuntimeToolError(code=spec.denied_code, message=spec.denied_message)
        arguments = spec.parser(arguments_json)
        return spec.executor(context, arguments)

    @staticmethod
    def _build_openai_tool_definition(spec: RuntimeToolSpec) -> dict[str, object]:
        return {
            "type": "function",
            "name": spec.openai_function_name,
            "description": spec.description,
            "strict": True,
            "parameters": deepcopy(spec.parameters_schema),
        }

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
