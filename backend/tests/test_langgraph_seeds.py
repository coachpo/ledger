from __future__ import annotations

from app.langgraph.seeds import (
    SEED_PATTERN_MENTION_POLICY,
    SEEDED_BUILTIN_REGISTRY,
    SEEDED_BUILTIN_SPECS,
)


def test_seeded_builtin_specs_expose_plain_handles_while_registry_stays_canonical() -> None:
    assert tuple(spec.handle for spec in SEEDED_BUILTIN_SPECS) == ("librarian", "explore")
    assert set(SEEDED_BUILTIN_REGISTRY) == {"builtin:librarian", "builtin:explore"}
    assert SEEDED_BUILTIN_REGISTRY["builtin:librarian"].handle == "librarian"
    assert SEEDED_BUILTIN_REGISTRY["builtin:librarian"].display_name == "Librarian"
    assert SEEDED_BUILTIN_REGISTRY["builtin:explore"].handle == "explore"
    assert SEEDED_BUILTIN_REGISTRY["builtin:explore"].display_name == "Explore"


def test_seeded_pattern_mention_policy_defines_allowed_builtins() -> None:
    assert SEED_PATTERN_MENTION_POLICY.version == 1
    assert SEED_PATTERN_MENTION_POLICY.allow_characters is False
    assert SEED_PATTERN_MENTION_POLICY.allowed_builtin_handles == ("librarian", "explore")
