# Platform Authoring Lib Guide

## Overview

This library owns pure schema, value, resource-reference, launch input, and Workflow Package transformation helpers shared by package editor, launch forms, schedules, and run inspection.

## Structure

| Path | Purpose |
| --- | --- |
| `common/` | Path tokens, diagnostics, shared resource reference utilities. |
| `schema/` | JSON Schema to internal schema IR helpers. |
| `values/` | Value-entry IR, defaults, coercion, and validation. |
| `workflow-packages/` | Package YAML/manifests, graph/resource refs, launch inputs. |

## Conventions

- Keep modules pure: no React hooks, DOM reads, network calls, toasts, or query invalidation.
- Preserve schema/value-entry shape, optional-field add/remove behavior, discriminated union variants, and path token semantics.
- Use structured JSON/YAML parsers and existing codecs. Do not parse manifests with regex or string splitting.
- Diagnostics should be deterministic, path-addressable, and safe for browser display.
- Schema `title` and `description` are display metadata only and must not alter runtime payloads.
- Resource refs target `inputs.<path>` or `nodes.<nodeId>.outputs.<slot>[.<path>]`; workflow outputs reference node outputs.
- Secret references `${{ secrets.<key> }}` are accepted only in HTTP request fields.

## Anti-Patterns

- Do not allow YAML aliases, anchors, merge keys, unsupported tags, non-finite numbers, duplicate keys, or unknown manifest fields.
- Do not smuggle DB ids or secret-like fields into package definitions.
- Do not duplicate schema/value logic in page components.
