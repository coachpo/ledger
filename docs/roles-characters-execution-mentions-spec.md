# Roles, Characters, and Execution-Time `@` Mentions Specification

## Status

Proposed implementation-ready specification for the next stage of Ledger's prompt-driven orchestration design.

This document extends:

- `docs/prompt-driven-role-orchestration-architecture.md`
- `docs/backtest-first-orchestration-blueprint.md`

It defines how Ledger should support:

- user-defined roles
- user-created characters built from those roles
- execution-time `@mentions` for characters and exposed built-ins such as `@librarian` and `@explore`

## Goal

Allow the user to:

- create reusable roles
- define each role's system prompt
- create app-wide characters from those roles
- call those characters in prompts with `@handle`
- call exposed built-ins such as `@librarian` and `@explore` in the same execution-time mention system

without expanding beyond the current backtest-first execution boundary.

## Spec Acceptance Criteria

This specification is complete only if it does all of the following:

- keeps `BacktestService` and `BacktestCycleService` as the live execution entry/lifecycle owners
- keeps `TemplateCompilerService` literal with respect to `@mentions`
- keeps `app/langgraph/runner.py` execution-focused and free of persistence logic
- defines roles and characters as separate persisted concepts
- defines built-ins as reserved code-backed entries, not CRUD-managed rows
- defines exact table fields for roles, characters, and orchestration snapshots
- defines exact API payloads for role and character CRUD plus mention-catalog reading
- defines an execution-time `ResolvedMention[]` contract
- defines mention grammar, normalization, and validation rules
- limits mention parsing to the user-authored entry prompt body only
- defines per-cycle snapshot/version semantics
- keeps mention resolution from bypassing `orchestrationPatternKey`

## Settled Decisions

These decisions are already made and should not be reopened in this stage.

- Characters are app-wide.
- `@mentions` work only during execution.
- The template compiler treats `@mentions` as ordinary markdown content.
- Roles are distinct from characters.
- Built-ins are reserved, code-backed entries.
- Internal agents remain non-mentionable.
- Internal dispatch uses canonical IDs, not raw `@name` text.
- Mention parsing must inspect only the user-authored entry prompt body.
- Mention resolution must not bypass the selected `orchestrationPatternKey`.
- Per-cycle provenance is required; run-level-only provenance is insufficient.

## Scope

### In scope

- app-wide role CRUD
- app-wide character CRUD
- read-only mention-catalog API for UI assistance
- execution-time mention parsing and resolution for backtests
- per-cycle orchestration snapshot persistence
- built-in plus user-character mention coexistence rules

### Out of scope

- workspace/project scoping
- mention resolution during template preview or inline compile
- arbitrary prompt-only spawning with no validation
- full role-level tool routing or custom model routing for user-defined roles
- generic orchestration product surfaces outside the current backtest-first boundary

## Repo Evidence Anchors

- persisted named-entity CRUD precedent:
  - `backend/app/models/text_template.py`
  - `backend/app/schemas/text_template.py`
  - `backend/app/services/text_template_service.py`
  - `backend/app/api/templates.py`
- artifact and metadata precedent:
  - `backend/app/models/report.py`
  - `backend/app/schemas/report.py`
- current backtest prompt ingress:
  - `backend/app/services/backtest_engine.py`
  - `backend/app/services/backtest_cycle_service.py`
- current execution boundary:
  - `backend/app/langgraph/runner.py`
  - `backend/app/langgraph/seeds.py`
- current backtest orchestration selection seam:
  - `backend/app/models/backtest.py`
  - `backend/app/schemas/backtest.py`
  - `backend/app/services/backtest_service.py`
- frontend authoring and assistance surfaces:
  - `frontend/src/pages/templates/editor.tsx`
  - `frontend/src/components/templates/template-placeholder-reference.tsx`
  - `frontend/src/hooks/use-templates.ts`

## Canonical Concepts

### Built-in agent

A code-backed, reserved orchestration target defined by Ledger.

Examples:

- `builtin:librarian`
- `builtin:explore`

Some built-ins may be exposed for mention resolution. Internal orchestration agents remain hidden and non-mentionable.

### Role

A persisted reusable prompt definition. Roles are not the main user-facing mention target.

### Character

A persisted user-facing entity built from exactly one role. Characters are the main mention target for custom prompt behavior.

### Mentionable registry

The merged execution-time registry of:

- exposed built-ins
- enabled characters whose referenced role is also enabled

### Canonical target ID

The internal immutable dispatch target.

Examples:

- `builtin:librarian`
- `builtin:explore`
- `character:macro_researcher`

## Persistence Specification

### 1. `orchestration_roles`

Purpose: persisted reusable role definitions.

Recommended fields:

- `id` - integer primary key
- `key` - `VARCHAR(100)`, unique, not null, immutable
- `name` - `VARCHAR(100)`, unique, not null
- `description` - `TEXT`, nullable
- `system_prompt` - `TEXT`, not null
- `enabled` - `BOOLEAN`, not null, default `TRUE`
- `version` - `INTEGER`, not null, default `1`
- `created_at` - timestamp
- `updated_at` - timestamp

Constraints:

- unique constraint on `key`
- unique constraint on `name`

Notes:

- This stage intentionally keeps role fields narrow.
- Advanced role-level tool policy and model override fields are deferred rather than persisted as inactive promises.

### 2. `orchestration_characters`

Purpose: persisted app-wide user-facing mention targets built from roles.

Recommended fields:

- `id` - integer primary key
- `handle` - `VARCHAR(100)`, unique, not null, immutable
- `display_name` - `VARCHAR(100)`, not null
- `description` - `TEXT`, nullable
- `role_id` - foreign key to `orchestration_roles.id`, not null, `ON DELETE RESTRICT`
- `prompt_append` - `TEXT`, nullable
- `enabled` - `BOOLEAN`, not null, default `TRUE`
- `version` - `INTEGER`, not null, default `1`
- `created_at` - timestamp
- `updated_at` - timestamp

Constraints:

- unique constraint on `handle`
- `handle` immutable after creation
- character must reference exactly one role

Notes:

- `handle` is the only `@mention` lookup key.
- `display_name` is UI text and may change without changing mention syntax.

### 3. `backtest_orchestration_snapshots`

Purpose: durable per-cycle orchestration provenance.

Recommended fields:

- `id` - integer primary key
- `backtest_id` - foreign key to `backtests.id`, not null, `ON DELETE CASCADE`
- `cycle_date` - `DATE`, not null
- `prompt_report_slug` - `VARCHAR(200)`, not null
- `orchestration_pattern_key` - `VARCHAR(120)`, not null
- `pattern_policy_version` - `INTEGER`, not null
- `entry_prompt_hash` - `VARCHAR(64)`, not null
- `full_user_prompt_hash` - `VARCHAR(64)`, not null
- `resolved_mentions` - `JSONB`, not null, default `[]`
- `mentioned_target_outputs` - `JSONB`, not null, default `[]`
- `resolved_builtin_versions` - `JSONB`, not null, default `[]`
- `resolved_role_versions` - `JSONB`, not null, default `[]`
- `resolved_character_versions` - `JSONB`, not null, default `[]`
- `created_at` - timestamp
- `updated_at` - timestamp

Constraints:

- unique constraint on `(backtest_id, cycle_date)`

Rationale:

- A single backtest run can compile a different prompt on each cycle.
- A single run-level snapshot is therefore too weak.
- This table must remain separate from `backtests.results` and `_run_state`.

Hash semantics:

- `entry_prompt_hash` hashes `authored_entry_prompt_body`
- `full_user_prompt_hash` hashes the authoritative post-mention `full_user_prompt`

## Versioning Rules

### Roles

- `version` increments on any successful update to:
  - `name`
  - `description`
  - `system_prompt`
  - `enabled`

### Characters

- `version` increments on any successful update to:
  - `display_name`
  - `description`
  - `role_id`
  - `prompt_append`
  - `enabled`
- `handle` does not change and therefore does not participate in rename semantics.

### Snapshots

Each snapshot must store the exact versions used for the cycle so later edits do not rewrite historical behavior.

## Built-in Registry Rules

Built-ins are code-backed, not CRUD-managed.

This stage should expose a reserved registry with at least:

- `builtin:librarian`
- `builtin:explore`

Each built-in entry should define:

- `canonical_target_id`
- `handle`
- `display_name`
- `description`
- `revision`
- `mentionable`
- `internal_only`

Rules:

- built-in handles are reserved
- characters may not reuse a reserved built-in handle
- internal-only built-ins never appear in the mentionable registry or autocomplete catalog

## API Specification

### Roles

#### `GET /api/v1/orchestration/roles`

Response:

```json
[
  {
    "id": 1,
    "key": "macro_research_role",
    "name": "Macro Research Role",
    "description": "Investigates macro drivers.",
    "systemPrompt": "You are a macro researcher...",
    "enabled": true,
    "version": 1,
    "createdAt": "2026-04-09T12:00:00Z",
    "updatedAt": "2026-04-09T12:00:00Z"
  }
]
```

#### `POST /api/v1/orchestration/roles`

Request:

```json
{
  "key": "macro_research_role",
  "name": "Macro Research Role",
  "description": "Investigates macro drivers.",
  "systemPrompt": "You are a macro researcher...",
  "enabled": true
}
```

Response: `RoleRead`

#### `GET /api/v1/orchestration/roles/{role_id}`

Response: `RoleRead`

#### `PATCH /api/v1/orchestration/roles/{role_id}`

Request:

```json
{
  "name": "Macro Research Role",
  "description": "Updated description",
  "systemPrompt": "Updated prompt",
  "enabled": true
}
```

Rules:

- `key` is not patchable
- at least one field must be provided

Response: `RoleRead`

#### `DELETE /api/v1/orchestration/roles/{role_id}`

Rules:

- delete must be rejected if any character still references the role

### Characters

#### `GET /api/v1/orchestration/characters`

Response:

```json
[
  {
    "id": 1,
    "handle": "macro_researcher",
    "displayName": "Macro Researcher",
    "description": "My macro character",
    "roleId": 1,
    "roleKey": "macro_research_role",
    "promptAppend": "Focus on global rates.",
    "enabled": true,
    "version": 1,
    "createdAt": "2026-04-09T12:00:00Z",
    "updatedAt": "2026-04-09T12:00:00Z"
  }
]
```

#### `POST /api/v1/orchestration/characters`

Request:

```json
{
  "handle": "macro_researcher",
  "displayName": "Macro Researcher",
  "description": "My macro character",
  "roleId": 1,
  "promptAppend": "Focus on global rates.",
  "enabled": true
}
```

Response: `CharacterRead`

#### `GET /api/v1/orchestration/characters/{character_id}`

Response: `CharacterRead`

#### `PATCH /api/v1/orchestration/characters/{character_id}`

Request:

```json
{
  "displayName": "Macro Researcher",
  "description": "Updated description",
  "roleId": 2,
  "promptAppend": "Focus on liquidity.",
  "enabled": true
}
```

Rules:

- `handle` is not patchable
- at least one field must be provided

Response: `CharacterRead`

#### `DELETE /api/v1/orchestration/characters/{character_id}`

Response: `204 No Content`

### Mention catalog

#### `GET /api/v1/orchestration/mentions/catalog`

Purpose: provide mention assistance/autocomplete in the UI.

Response:

```json
{
  "targets": [
    {
      "handle": "librarian",
      "kind": "builtin",
      "canonicalTargetId": "builtin:librarian",
      "displayName": "Librarian",
      "description": "External reference and docs search"
    },
    {
      "handle": "macro_researcher",
      "kind": "character",
      "canonicalTargetId": "character:macro_researcher",
      "displayName": "Macro Researcher",
      "description": "My macro character",
      "roleKey": "macro_research_role"
    }
  ]
}
```

Rules:

- include only mentionable built-ins
- include only enabled characters whose referenced role is also enabled
- do not include internal-only built-ins

## Schema Rules

### RoleCreate

- `key`: required, 1-100 chars, trimmed, lowercase underscore-style stable identifier
- `name`: required, 1-100 chars, trimmed
- `description`: optional, trimmed to `null` if blank
- `systemPrompt`: required, non-blank
- `enabled`: default `true`

### CharacterCreate

- `handle`: required, immutable, 1-100 chars, normalized to lowercase, must match handle grammar
- `displayName`: required, 1-100 chars, trimmed
- `description`: optional, trimmed to `null` if blank
- `roleId`: required
- `promptAppend`: optional, trimmed to `null` if blank
- `enabled`: default `true`

### MentionCatalogRead

- `targets`: list of mentionable entries with stable `canonicalTargetId`

## Mention Grammar

### Handle grammar

Handles use the same broad style as existing Ledger stable identifiers.

Allowed handle regex:

```text
^[a-z][a-z0-9_]{0,99}$
```

### Mention token grammar

Execution-time parsing should treat only this pattern as a valid candidate:

```text
(?<![@A-Za-z0-9_])@(?P<handle>[A-Za-z][A-Za-z0-9_]*)\b
```

Implications:

- `@macro_researcher` is valid
- `@Librarian` normalizes to `librarian`
- `email@domain.com` is not a valid mention because `@` is preceded by a word character
- `@@name` does not create a valid mention target

### Normalization

Mention resolution normalizes:

- leading `@` removed
- handle lowercased
- no fuzzy matching

## Validation Errors

Recommended API/runtime error codes:

### Roles

- `duplicate_role_key`
- `duplicate_role_name`
- `invalid_role_key`
- `role_not_found`
- `role_in_use`

### Characters

- `duplicate_character_handle`
- `invalid_character_handle`
- `reserved_mention_handle`
- `character_not_found`
- `character_role_not_found`
- `character_role_disabled`

### Execution-time mention resolution

- `mention_target_not_found`
- `mention_target_disabled`
- `ambiguous_mention_target`
- `mention_target_reserved`
- `mention_target_not_allowed_by_pattern`

## Internal Execution Contracts

### Required prompt bundle

The current backtest prompt flow is too collapsed for safe mention parsing. This stage should introduce an internal bundle shape similar to:

```python
class BacktestPromptBundle(TypedDict):
    system_prompt: str
    authored_entry_prompt_body: str
    compiled_entry_prompt_body: str
    execution_context_body: str
    full_user_prompt: str
    prompt_report_slug: str
```

Rules:

- `authored_entry_prompt_body` is the raw template markdown exactly as stored by the user
- `compiled_entry_prompt_body` is the result of placeholder compilation applied to the template body
- `execution_context_body` contains portfolio state, market context, benchmark context, prior reports, and other generated context
- the stored prompt report remains a pre-mention audit artifact composed from `compiled_entry_prompt_body` plus generated context
- `full_user_prompt` is the authoritative post-mention runtime input used downstream by execution
- `BacktestEngine.execute_cycle()` must carry `authored_entry_prompt_body`, `compiled_entry_prompt_body`, and `execution_context_body` in `cycle_ctx`
- mention resolution must consume `cycle_ctx.authored_entry_prompt_body`; it must not reconstruct the entry prompt by parsing the stored merged prompt report
- `full_user_prompt` must be recomputed with this exact formula:

```text
full_user_prompt = "\n\n".join([
  execution_context_body,
  compiled_entry_prompt_body,
])
```

- `execution_context_body` must preserve the existing `BacktestEngine._build_prompts()` context ordering:
  1. portfolio state
  2. market context
  3. benchmark context
  4. prior reports
  5. mentioned-target outputs (appended after resolution)

### Required resolved mention contract

```python
class ResolvedMention(TypedDict):
    original_text: str
    handle: str
    canonical_target_id: str
    target_type: Literal["builtin", "character"]
    role_id: int | None
    role_version: int | None
    character_id: int | None
    character_version: int | None
    mention_order: int
```

### Required LangGraph request expansion

`BacktestLangGraphRequest` should be expanded to include:

- `authored_entry_prompt_body`
- `compiled_entry_prompt_body`
- `execution_context_body`
- `full_user_prompt`
- `resolved_mentions`
- `orchestration_pattern_key`

It should continue carrying:

- `backtest_id`
- `cycle_date`
- `prompt_report_slug`
- `prompt_report`

Rules:

- `prompt_report` remains the persisted pre-mention audit artifact
- `full_user_prompt` is the authoritative post-mention runtime input
- `runner.py` must not treat `prompt_report` as the authoritative execution prompt once mention dispatch is enabled

### Required mention dispatch semantics

This stage must define what resolved mentions actually do at runtime.

#### Repeated mentions

- preserve first-appearance order
- de-duplicate repeated mentions by `canonical_target_id` within a cycle

#### Built-in targets

- `builtin:librarian` runs a research helper step before `runner.run_cycle(...)`
- `builtin:explore` runs an internal codebase/context helper step before `runner.run_cycle(...)`

Each built-in target returns one markdown summary artifact.

#### Character targets

- each resolved `character:*` target creates one character-worker invocation before `runner.run_cycle(...)`
- the character worker receives:
  - resolved role `system_prompt`
  - character `prompt_append`, if present
  - `compiled_entry_prompt_body`
  - `execution_context_body`
- each character worker returns one markdown summary artifact

#### Mentioned-target artifact integration

Built-in and character artifacts are appended to `execution_context_body` under a dedicated section:

```text
## Mentioned Target Outputs
- librarian: ...summary...
- explore: ...summary...
- macro_researcher: ...summary...
```

This gives mentions concrete execution meaning without requiring raw prompt-only spawning inside `runner.py`.

## Execution Sequence

1. Backtest template content is authored and stored unchanged, including any `@mentions`.
2. During cycle preparation, `BacktestEngine` loads the template and compiles placeholders through `TemplateCompilerService`.
3. `BacktestEngine` carries the raw stored template body as `authored_entry_prompt_body`.
4. `BacktestEngine` compiles that body into `compiled_entry_prompt_body`.
5. `BacktestEngine` separately renders `execution_context_body`.
6. `BacktestEngine` stores the combined pre-mention prompt report as an audit artifact.
7. `BacktestCycleService` receives the prompt bundle from `cycle_ctx` and resolves mentions from `authored_entry_prompt_body` only.
8. Mention resolution normalizes handles and resolves them against the mentionable registry.
9. Resolution validates:
   - target exists
   - target is enabled
   - target is not internal-only
   - target is allowed by the selected `orchestrationPatternKey`
10. `BacktestCycleService` dispatches resolved built-in mentions and character mentions before `runner.run_cycle(...)`.
11. Mention outputs are appended to `execution_context_body` under `## Mentioned Target Outputs`.
12. `BacktestCycleService` recomputes `full_user_prompt` from `compiled_entry_prompt_body` plus the updated `execution_context_body`.
13. Ledger persists a per-cycle orchestration snapshot that records mention resolution and the authoritative post-mention prompt hashes/artifacts.
14. `BacktestCycleService` passes `compiled_entry_prompt_body`, `execution_context_body`, `full_user_prompt`, `resolved_mentions`, and `orchestration_pattern_key` into `runner.run_cycle(...)`.
15. Internal dispatch uses canonical target IDs only.
16. Final analysis/trade decisions proceed through the existing backtest/report lifecycle.

## Orchestration Pattern Interaction Rules

Mentions do not bypass orchestration pattern selection.

Required rule:

- every resolved mention must be validated against the selected `orchestrationPatternKey`

Required code-backed pattern-policy shape:

```python
class PatternMentionPolicy(TypedDict):
    version: int
    allow_characters: bool
    allowed_builtin_handles: list[str]
```

Required built-in pattern policies for this stage:

- `seeded_internal_backtest_v1`
  - `allow_characters = False`
  - `allowed_builtin_handles = ["librarian", "explore"]`
- `analyst_reviewer_v1`
  - `allow_characters = True`
  - `allowed_builtin_handles = ["librarian", "explore"]`

Implications:

- a pattern may allow only built-in research helpers
- a pattern may allow only specific character execution modes in later phases
- a prompt may mention a valid character that is still rejected for the current pattern

The per-cycle snapshot must persist the exact `pattern_policy_version` used for the cycle.

## Boundary Rules

### `TemplateCompilerService`

- compiles `{{...}}` placeholders only
- does not resolve or validate `@mentions`

### `BacktestEngine`

- must produce first-class `authored_entry_prompt_body` and `compiled_entry_prompt_body`
- must return `authored_entry_prompt_body`, `compiled_entry_prompt_body`, and `execution_context_body` in `cycle_ctx`
- must not itself decide mention targets

### `BacktestCycleService`

- owns execution-time mention parsing and resolution
- owns snapshot persistence orchestration
- owns passing resolved targets into the runtime boundary
- owns recomputing the authoritative post-mention `full_user_prompt`

### `app/langgraph/runner.py`

- consumes resolved execution inputs
- does not parse raw `@mentions`
- does not persist ORM state
- treats `full_user_prompt` as authoritative runtime input once mention dispatch is enabled

## Frontend Behavior Specification

### Template editor

- mention assistance/autocomplete should be added to the template editor authoring surface
- assistance should use the mention-catalog API
- compile preview remains literal markdown and does not resolve `@mentions`

### Role and character CRUD UI

- add role list/create/edit flows modeled after template CRUD
- add character list/create/edit flows modeled after template CRUD
- character creation UI should select exactly one role
- character handle must be shown as immutable after creation

## Lifecycle Rules

### Database/init wiring

Implementation must include:

- model imports so tables are created by `init_db()`
- router registration in `api/router.py`
- dependency factories in `api/dependencies.py`
- code-based schema upgrade handling in `app/db/upgrades.py`

### Deletion behavior

- deleting a role in use by a character must fail
- deleting a character does not rewrite existing snapshots
- deleting a backtest must cascade-delete its orchestration snapshots

### Disabled-role behavior

- character create/update must reject references to disabled roles
- execution must also reject a resolved character whose role is disabled at run time
- execution-time rejection uses `character_role_disabled`

## Mention Parsing Failure Rules

- text that does not match mention-token grammar is treated as ordinary markdown
- invalid sequences such as `@@name` are ignored as literal text, not execution errors
- only successfully parsed mention tokens enter validation and resolution

## TDD Verification Plan

### Backend model/schema/API tests

Extend patterns from:

- `backend/tests/test_api.py`
- `backend/tests/test_backtests_api.py`

Add coverage for:

- role CRUD
- character CRUD
- handle immutability
- reserved built-in handle rejection
- mention-catalog response

### Execution-path tests

Extend:

- `backend/tests/test_backtest_cycle_service.py`
- `backend/tests/test_langgraph_runner.py`

Add coverage for:

- `authored_entry_prompt_body` vs `compiled_entry_prompt_body` isolation
- parse-only-entry-prompt behavior
- mention resolution failure cases
- canonical ID payload passed to runner ingress
- snapshot persistence per cycle

### Frontend tests

Add coverage near:

- template editor mention assistance UI
- role CRUD pages
- character CRUD pages

### E2E

Add a backtest execution flow that:

- authors a template with `@character` and `@librarian`
- launches a backtest
- verifies execution succeeds when mentions are valid
- verifies execution fails clearly when mentions are unknown or disabled

## Final Decision Summary

- Roles are persisted reusable system-prompt definitions.
- Characters are app-wide persisted mentionable entities built from roles.
- Built-ins remain reserved code-backed targets.
- `@mentions` are execution-only and stay literal during compile/preview.
- Mention parsing operates only on `authored_entry_prompt_body`.
- Resolution yields canonical IDs and `ResolvedMention[]` metadata.
- Per-cycle snapshots store the exact resolved role/character versions used by each cycle.
- The current backtest-first boundary stays intact.
