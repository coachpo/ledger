# Backend Services Guide

## Overview

Services own SignalDeck transactions, orchestration, validation projection, run execution, provider calls, and scheduler semantics.

## Where To Look

| Task | Location | Notes |
| --- | --- | --- |
| Run launch/execution/projection | `run_service.py` | Central hot path for queued runs and evidence. |
| Queue claiming/leases | `run_queue_service.py` | Uses repository `FOR UPDATE SKIP LOCKED` behavior. |
| Scheduler materialization | `workflow_package_schedule_service.py` | Recurrence, fire history, run-now, stale package checks. |
| Manifest parse/compile | `workflow_package_manifest_parser.py`, `workflow_package_manifest_compiler.py` | YAML/package contract. |
| Preflight/diagnostics | `workflow_package_preflight.py` | Browser-visible validation diagnostics. |
| Execution plans | `execution_plan.py`, `package_execution_plan_builder.py` | Frozen runtime graph shape. |
| Output schemas | `output_schema_compiler.py` | JSON Schema to runtime node compilation. |
| OpenAI runtime | `model_gateway_openai.py` | Provider retries, tool calls, tracing metadata. |
| HTTP operation nodes | `http_operation_execution_service.py` | Request execution and evidence redaction. |

## Conventions

- Services receive a SQLAlchemy `Session` or repository factory and own commit/rollback behavior.
- Keep repository methods narrow; compose them in services for user-visible workflows.
- Preserve run immutability: execute from snapshots, not current mutable Workflow Package rows.
- Scheduler correctness depends on PostgreSQL advisory locks, lease heartbeats, stale lease recovery, and bounded executor threads.
- Preflight and compiler diagnostics must be deterministic and safe for browser display.
- Tool-call correction retries are bounded; provider retry metadata is evidence, not control flow hidden in logs.
- HTTP operation request metadata must be sanitized before persistence.
- Model runtime profiles are resolved from Model Connections once, then stored as safe run context.

## Anti-Patterns

- Do not read mutable package definitions during rerun execution.
- Do not make provider/network calls in repositories.
- Do not leak raw provider exceptions or secret-bearing request material into run evidence.
- Do not bypass schedule overlap/misfire policy helpers when creating due runs.
