# 数据模型

SignalDeck 使用 PostgreSQL 保存 mini-Jenkins 运行时数据，包括 finance templates/reports、Workflow Package artifact、schedules、Model Connections、runs、run evidence 和加密的 package secrets。live schema 由 `backend/app/db/` 使用 SQLAlchemy `create_all` 创建；schema 变化需要重建数据库。

## Finance 表

| 表 | 作用 |
| --- | --- |
| `text_templates` | 保存报告工作流使用的可复用 markdown 模板。 |
| `reports` | 保存按唯一 `name` 和 `slug` 标识的 markdown 报告快照、source 和 JSON metadata。 |
| `market_quotes` | 按 provider、symbol、`as_of` 保存可重建的市场报价缓存。 |
| `symbol_name_cache` | 保存可重建的 symbol 展示名称缓存。 |

## Platform 表

| 表 | 作用 |
| --- | --- |
| `workflow_packages` | 按 stable key 保存当前 package，包括 manifest source、package definition、compiled plan、hash、扩展依赖面和时间戳。 |
| `workflow_package_secret_bindings` | 按 package 和 binding key 保存加密的包内 secret；读取只显示存在性和时间戳。 |
| `workflow_package_schedules` | 保存 Workflow Package schedule 定义，包括 package/workflow target、启用状态、recurrence、timezone、policy、next fire、input template 和 template vars。 |
| `workflow_package_schedule_fires` | 保存 schedule-owned fire，包括渲染参数、local scheduled 字段、状态、skip/error；schedule 存在时 run 通过 `runs.schedule_fire_id` 关联。 |
| `model_connections` | 保存全局 provider/model binding、`protocol_profile`、endpoint/model、加密 API key、capability/policy/probe/test metadata 和时间戳。 |
| `runs` | 保存 queued/执行中的 Workflow Package run，包括生命周期、输入/输出、queue/progress、scheduler lease、cancel、token、trace、rerun link、package/schedule provenance 和 extension dependencies。 |
| `run_workflow_package_snapshots` | 每个 run 的不可变 executable package snapshot，包括 package/workflow identity、hash、安全 manifest material、compiled plan、launch inputs、非 secret runtime profile 和 preflight summary。 |
| `run_steps` | 保存 workflow node 的计划、来源、graph metadata、step error 和时间戳。 |
| `run_agent_invocations` | 保存 agent invocation identity、input mode、wiring、resolved input/origin、output、error、token usage、duration 和可选 span id。 |
| `run_operation_invocations` | 保存 HTTP operation invocation identity、脱敏 request metadata、有界 response metadata、output、error、duration 和可选 span id。 |

Package-local agents、output schemas、capability profiles、private MCP configs、HTTP operation nodes 和 workflow graphs 保存在 package artifact 内，而不是拆成全局 authoring 表。run 创建时将可执行 artifact 复制到 run-owned snapshot。

## 完整性规则

- Backend 对外 JSON 使用 camelCase，内部使用 snake_case。
- Money、quantity 和 market value 跨 API 边界使用 decimal-safe string。
- API-owned error envelope 为 `{code, message, details[]}`。
- Report 创建后的 `name`、`slug`、`source` 和 metadata 保持不变，只有 content 可编辑。
- Report source 为 `compiled`、`uploaded`、`external` 或 `agent`。
- Workflow Package 将依赖保存为 artifact ref；readiness 根据 live Model Connection、静态扩展工具和 package secret binding 计算。
- manifest read、export 和 run provenance 不包含私有 MCP 的 `env`、`headers`、`query`、database id、run history、package secret binding row 或 raw secret；API envelope 可以包含 `packageId`、`packageKey` 等安全 identity。
- Package secret binding value 和 Model Connection API key 静态加密，不能出现在 reads、exports、run details、logs、diagnostics 或 metadata。
- Tools 是静态扩展提供的只读 server-declared metadata，由 package-local capability profile 引用。
- Run 保存 immutable package provenance、scheduler metadata、run-owned schedule provenance、queue/progress、typed failure、`toolCallRetries` 和 provider transient retry metadata。
- Run status 为 `queued`、`running`、`succeeded`、`failed` 和 `cancelled`。
- retention 只删除 `finished_at` 早于 `SIGNALDECK_RUN_RETENTION_DAYS` 的终态 run。
- HTTP operation request metadata 会脱敏敏感 query name，以及所有 secret-backed header、query 和 body 字段；response metadata 有界且可安全脱敏。
- 删除 schedule 会删除 schedule-owned fire 并停止未来自动化，但现有 run 通过自己的 schedule provenance 保持可读。
- 删除 Workflow Package 会删除其拥有的 runs。
- Rerun 只保存 source-run link，并允许编辑 root launch parameters。

## Schema 边界

以上表是当前 shipped data contract。已经移除或 retired 的产品面不属于本数据模型，除非 live code 重新引入它们。
