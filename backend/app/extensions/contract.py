"""Extension contract: what a bundled extension contributes statically."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import APIRouter

if TYPE_CHECKING:
    from app.extensions import BundledServerDeclaredToolContribution as ToolDeclaration


@dataclass(frozen=True, slots=True)
class Extension:
    key: str
    api_routers: tuple[APIRouter, ...] = ()
    tool_declarations: tuple[ToolDeclaration, ...] = ()
    provider_factories: Mapping[str, Callable[..., object]] = field(default_factory=dict)


__all__ = ["Extension"]
