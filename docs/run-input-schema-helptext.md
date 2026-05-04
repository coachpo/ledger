# Run Input Schema Help Text

> Status: Live runtime-input help text as of 2026-05-04 (`b4ac445`).

Agent and workflow run input schemas can include optional `title` and `description` fields on supported JSON Schema nodes. These fields are display metadata for generated forms.

## Supported Metadata

1. `title` supplies the generated form label for that schema node.
2. `description` supplies generated help text near that form field or group.
3. Both fields are optional. If they are absent, the form falls back to contextual labels and existing helper copy.

## Runtime Behavior

`title` and `description` don't change runtime execution semantics. They don't change runtime input JSON, value-entry encoding, validation semantics, workflow wiring, or agent invocation.

Use them to make run launch forms clearer for people. Don't use them to pass data to a workflow or agent.

## Unsupported Help Text Mechanisms

YAML comments aren't read as help text. A new `comment` field isn't supported. `x-ledger-*` metadata isn't supported.

Unsupported JSON Schema keys remain unsupported, including `patternProperties`, `oneOf`, `allOf`, `if`, `then`, `else`, `not`, and schema-valued `additionalProperties`.
