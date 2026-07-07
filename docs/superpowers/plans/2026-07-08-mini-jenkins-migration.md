# Mini-Jenkins-for-LLM-Agents 迁移实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 SignalDeck 从"多租户 LLM 平台 PaaS"降维成它的本意——一个自托管的迷你 Jenkins for LLM agents：YAML 定义多 Agent 工作流（A 的输出 → B 的输入）、手动/定时触发、队列执行、查看运行结果。

**Architecture:** 三类动作。①删除：memory 治理子系统、fork 血缘、插件框架机制、portfolio 记账域、hand-rolled 迁移机器、重复测试（约 -5 万行）。②折叠：extension registry → 直接 import，model_gateway 9 文件 → 3 文件。③补齐生产短板：Bearer token 鉴权、run 取消、Fernet 加密、logfire 插桩、run 保留期（约 +500 行）。

**Tech Stack:** FastAPI + SQLAlchemy 2 + PostgreSQL 16 / React 19 + Vite + TanStack Query / pytest + Vitest + Playwright / uv + pnpm。

## Global Constraints

- 无兼容性要求，无数据保留要求。破坏性变更随意，数据库随时可以 drop 重建。
- Python 3.13、uv 0.9.8;Node 24、pnpm 10。
- 后端全量校验命令（每个 Task 结束时必须全绿）：
  ```bash
  cd backend && uv run ruff check app tests && uv run black --check app tests \
    && uv run isort --check-only app tests && uv run mypy app && uv run pytest
  ```
- 后端测试需要 Postgres。本地一次性启动：
  ```bash
  docker run -d --name signaldeck-test-pg -e POSTGRES_DB=signaldeck \
    -e POSTGRES_USER=signaldeck -e POSTGRES_PASSWORD=signaldeck \
    -p 25432:5432 postgres:16-alpine
  export TEST_DATABASE_URL='postgresql+psycopg://signaldeck:signaldeck@127.0.0.1:25432/signaldeck'
  export DATABASE_URL="$TEST_DATABASE_URL"
  ```
- 前端全量校验命令：
  ```bash
  cd frontend && pnpm lint && pnpm typecheck && pnpm test:run && pnpm build
  ```
- e2e（Phase 收尾时跑，不必每个 Task 跑）：`cd frontend && pnpm test:e2e`
- 分支：`migration/mini-jenkins`，基于 `main`。Conventional Commits；每条 commit message 结尾加 `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`。
- 删除代码时的通用手法：先删文件 → `uv run mypy app`（或 `pnpm typecheck`）列出所有断裂引用 → 逐个删掉引用点（不是注释掉）→ 跑测试。mypy/tsc 的报错清单就是完整的接缝清单，不要靠记忆。
- 删功能时同步删它的测试文件；"测试瘦身"阶段只处理**存活功能**的冗余测试。

## 保留 / 删除 / 明确不做 总表

**保留（迷你 Jenkins 核心）：** workflow-packages（manifest YAML、导入/导出、launch）、runs（列表/详情/rerun + 新增 cancel）、scheduled-tasks、model-connections、tools 目录、reports + templates（分析工作流的产出物）、market-data/news/sentiment 服务与 runtime tools（股票/经济分析工作流的工具箱）、MCP runtime（默认关闭）、调度器 lease/advisory-lock 机制、CI 四段门禁、SSRF 加固。

**删除：** workflow-memory 治理子系统（全栈）、fork 血缘、runtime-input preset/history 注册表、run 生命周期钩子（死代码）、manifest decompiler、`db/upgrades.py` 迁移机器、插件**市场机制**（动态发现/registrar Protocol/依赖解析/启停管理面——插件**契约**保留并文档化，见 Phase 5）、前端插件宿主、portfolio 记账域（全栈，见 Phase 4 DECISION）、路由元数据注册表、33 个目录级 AGENTS.md、重复测试。

**明确不做（有意跳过，每条一行理由）：**
- schedule 三文件合并：纯装饰性搬家，2.5k 行有测试的工作代码，churn 无收益。
- 手写 recurrence 数学换 croniter/rrule：能用、有测试，重写只添风险。
- `output_schema_compiler.py` 重写为 `pydantic.create_model`：LLM 结构化输出核心路径，1,641 行工作代码换 ~800 行节省，风险收益比不划算。加 `# ponytail:` 注释标注天花板即可。
- DI 依赖图扁平化：每请求多构造几个对象是纳秒级成本，无 IO，纯洁癖。
- manifest compiler+builder 合并为一趟：见 Phase 10（可选，默认不排期）。
- Alembic：无数据可保，`create_all` + 文档声明"schema 变更 = drop 重建"即可；等真有数据要保时再引入。

---

## Phase 0 — 基线

### Task 0.1: 建分支、记录基线

**Files:** 无代码改动。

- [ ] **Step 1: 建分支**
```bash
cd /home/qing/Documents/projects/ledger
git checkout -b migration/mini-jenkins
```
- [ ] **Step 2: 起测试库并跑后端基线**（Global Constraints 中的 Postgres + 后端全量校验命令）。预期：全绿。若基线即红，先修再开工，单独提交。
- [ ] **Step 3: 跑前端基线**（前端全量校验 + `pnpm test:e2e`）。预期：全绿。
- [ ] **Step 4: 记录基线 LOC**
```bash
git ls-files '*.py' '*.ts' '*.tsx' | xargs wc -l | tail -1 > /tmp/loc-baseline.txt
```
- [ ] **Step 5: Commit**（若 Step 2/3 有修复）`fix: green baseline before migration`

---

## Phase 1 — 删除 db/upgrades.py 迁移机器

不保留数据 ⇒ 每次部署都是新库 ⇒ 1,771 行幂等修复脚本整体失效。`create_all` 负责建表；其中两块**活功能**要搬走：预置包种子、重启时把 in-flight run 标失败。

### Task 1.1: 抽出活功能，删除 upgrades.py

**Files:**
- Create: `backend/app/db/seed.py`（预置包种子）
- Create: `backend/app/db/startup_recovery.py`（in-flight run 标失败）
- Delete: `backend/app/db/upgrades.py`
- Modify: `backend/app/db/session.py`（替换 `apply_startup_schema_repairs` 调用）
- Delete: `backend/tests/test_runtime_db_upgrades.py`、`backend/tests/test_workflow_package_db_upgrades.py`
- Test: `backend/tests/test_db_bootstrap.py`（新建）

**Interfaces:**
- Produces: `seed.seed_preset_packages(engine) -> None`（幂等）、`startup_recovery.fail_inflight_runs(engine) -> int`（返回标记数）。`session.py` 启动顺序：`create_all → seed_preset_packages → fail_inflight_runs`。

- [ ] **Step 1: 定位要搬的两块活代码**
```bash
cd backend
grep -n "_AGENT_PLATFORM_RESTART_FAILURE_MESSAGE" app/db/upgrades.py
grep -n "\.sql" app/db/upgrades.py
```
把重启恢复函数和 `.sql` 种子加载逻辑**原样**搬到 `startup_recovery.py` 和 `seed.py`（保留原实现，只改模块归属和函数名为上面 Interfaces 的签名）。
- [ ] **Step 2: 写失败测试** `tests/test_db_bootstrap.py`：
```python
from sqlalchemy import inspect, text

def test_fresh_bootstrap_creates_schema_and_seeds(engine):
    # conftest 的 engine fixture 已初始化 schema
    names = set(inspect(engine).get_table_names())
    assert {"workflow_packages", "runs", "run_steps"} <= names
    with engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM workflow_packages")).scalar()
    assert count >= 1  # 预置包已种入

def test_bootstrap_is_idempotent(engine):
    from app.db.session import init_db
    init_db()  # 第二次初始化不得报错、不得重复种子
    init_db()
```
（`init_db` 若实际名不同，以 `app/db/session.py` 中被 main.py 启动时调用的初始化入口为准，同名替换。）
- [ ] **Step 3: 跑新测试确认失败**：`uv run pytest tests/test_db_bootstrap.py -v`，预期 FAIL（seed 未接线）。
- [ ] **Step 4: 改 `session.py`**：删除 `from app.db.upgrades import ...` 与 `apply_startup_schema_repairs(engine)` 调用，改为 `create_all` 后调用 `seed_preset_packages(engine)`、`fail_inflight_runs(engine)`。然后 `git rm app/db/upgrades.py tests/test_runtime_db_upgrades.py tests/test_workflow_package_db_upgrades.py`。
- [ ] **Step 5: mypy 清扫断裂引用**：`uv run mypy app`，删除所有指向 `app.db.upgrades` 的残余 import（预期只在 `session.py`、`main.py`、`workers/run_scheduler.py` 附近）。
- [ ] **Step 6: 后端全量校验**，预期全绿。
- [ ] **Step 7: 在 `startup_recovery.py` 顶部加注释** `# ponytail: no migration framework — schema changes require DB reset; adopt Alembic when data must survive.`
- [ ] **Step 8: Commit** `refactor(db): replace hand-rolled schema repairs with create_all + seed`

---

## Phase 2 — 删除 workflow-memory 治理子系统（全栈）

全仓只有一个测试 fixture 启用它。整个提案/审批/隔离区/整合/审计/检查点子系统连根拔。

### Task 2.1: 后端删除

**Files:**
- Delete（已核实存在）:
  - `backend/app/services/workflow_memory_middleware.py`、`workflow_memory_policy_service.py`、`workflow_memory_proposal_service.py`、`workflow_memory_consolidation_service.py`、`workflow_memory_context_service.py`、`workflow_memory_detection.py`、`workflow_checkpoint_service.py`
  - `backend/app/repositories/workflow_memory.py`、`workflow_checkpoints.py`
  - `backend/app/models/workflow_memory.py`、`workflow_checkpoint.py`
  - `backend/app/schemas/workflow_memory.py`、`memory_report.py`
  - `backend/app/api/memory.py`
- Delete tests: `test_workflow_memory_middleware.py`、`test_api_memory.py`、`test_workflow_memory_persistence.py`、`test_workflow_memory_context.py`、`test_workflow_memory_consolidation.py`、`test_workflow_memory_policy.py`、`test_workflow_memory_checkpoints.py`、`test_workflow_memory_manifest.py`、`test_workflow_runtime_memory_integration.py`、`test_agent_execution_memory_context.py`
- Modify: `backend/app/api/platform_router.py:5,14`（删 memory router 注册）、`backend/app/api/dependencies.py`、`backend/app/services/run_service.py`、`run_read_projection.py`、`agent_execution_service.py`、`workflow_package_manifest_parser.py`、`workflow_package_manifest_compiler.py`、`workflow_package_preflight.py`、`backend/app/models/__init__.py`

**Interfaces:**
- Produces: manifest 中 `memory:` 段从此为**解析错误**（未知字段），`/api/memory/*` 路由消失，Run 读投影中不再有 memory 字段。

- [ ] **Step 1: 删文件**：`git rm` 上面 Delete 列表的全部文件（app 15 个 + tests 10 个）。
- [ ] **Step 2: mypy 列接缝**：`uv run mypy app`。逐个处理报错：删除 import、删除引用 memory 服务/模型的方法与分支（`run_service.py` 中 memory finalize 相关方法约 400 行、`run_read_projection.py` 中 memory 投影约 250 行、parser/compiler 中 `memory:` 段解析、preflight 中 memory 校验、`dependencies.py` 中 memory 服务 provider、`agent_execution_service.py` 中 `workflow_memory_middleware.prepare_invocation` 调用点）。原则：**删调用链，不留空壳函数**。
- [ ] **Step 3: 清扫测试内残留**：
```bash
grep -rln "memory" tests/ --include="*.py" | grep -v test_db_bootstrap
```
对每个命中文件，删除引用 memory manifest 段/断言 memory 行为的测试函数和 fixture（重点：`test_workflow_package_preflight.py`、`test_workflow_package_runtime_api.py`、`test_workflow_package_run_contracts.py`、`conftest.py`、`advisory_research_memory.yaml` 之类 fixture 文件——整个文件删）。
- [ ] **Step 4: 后端全量校验**，预期全绿。
- [ ] **Step 5: Commit** `refactor!: remove workflow-memory governance subsystem`

### Task 2.2: 前端删除

**Files:**
- Delete: `frontend/src/pages/memory/`（整目录）、`frontend/src/hooks/use-memory.ts`、`use-memory.test.ts`、`frontend/src/lib/api/memory.ts`、`frontend/e2e/memory.spec.ts`
- Modify: `frontend/src/routes.ts`（约 line 81 的 memory 路由项）、`frontend/src/routes.metadata.ts`、`frontend/src/lib/query-keys.ts`、侧边栏导航组件（用 `grep -rn "memory" src/components/` 定位）

- [ ] **Step 1: 删文件** + **Step 2: `pnpm typecheck` 列接缝**，删 routes 项、metadata 项、query-keys 段、导航项、`lib/types` 中 memory 类型。
- [ ] **Step 3: 清 routes.test.tsx 中 memory 断言**：`grep -n "memory" src/routes.test.tsx src/App.test.tsx`，删除相关用例。
- [ ] **Step 4: 前端全量校验**，预期全绿。
- [ ] **Step 5: Commit** `refactor!: remove memory UI surface`

---

## Phase 3 — 删除 fork 血缘、preset/history 注册表、死钩子、decompiler

### Task 3.1: 删 fork（保留 rerun）

**Files:**
- Modify: `backend/app/services/run_rerun_fork.py`（删 fork 一半，rerun 保留；改名为 `run_rerun.py`）、`backend/app/api/runs.py`（删 line 66 `fork-draft`、line 75 `forks` 两个端点）、`backend/app/services/run_service.py`（fork 方法）、`backend/app/schemas/` 中 fork 类型
- Delete: `backend/app/models/run_fork.py`、`backend/app/repositories/run_fork.py`
- Tests: 删 fork 相关测试函数（`grep -rln "fork" tests/`，重点 `test_workflow_package_run_contracts.py`、`test_agent_execution_responses_manual_replay.py`）
- 前端：`grep -rln "fork" frontend/src frontend/e2e` → 删 runs 详情页 fork 按钮/对话框、`lib/api/runs.ts` fork 函数、相关测试。

**Interfaces:**
- Produces: `Run` 模型保留 `source_run_id`（若 rerun 已有等价字段则不新增）；`POST /api/runs/{run_id}/reruns` 不变。

- [ ] Step 1: 删文件与端点 → Step 2: mypy/typecheck 清扫（删 `copy_lineage_context_rows`、fork-draft 机器）→ Step 3: 前后端全量校验 → Step 4: Commit `refactor!: remove run fork lineage, keep rerun`

### Task 3.2: 删 runtime-input preset/history 注册表

**Files:**
- Delete: `backend/app/services/workflow_package_runtime_input_registry.py`、`workflow_package_runtime_inputs.py`
- Modify: `backend/app/api/workflow_packages.py`（删 preset/history 相关端点，`grep -n "runtime.input\|preset\|history" app/api/workflow_packages.py` 定位）、`backend/app/repositories/workflow_package.py`（删 slot/fingerprint 方法）
- 前端: Delete `frontend/src/components/shared/saved-runtime-input-registry-panel.tsx`；`frontend/src/lib/runtime-inputs.ts` **先查再删**：`grep -rn "runtime-inputs" src/pages/workflow-packages/` — launch 页面引用的输入编码函数保留，仅 preset/history 相关导出删除。
- Tests: 删除引用上述服务的测试（`grep -rln "runtime_input" tests/`）。

- [ ] Step 1-4 同上模式（删 → mypy/tsc 清扫 → 全量校验 → Commit `refactor!: remove runtime-input preset/history registry`）。注意保留 `run_input_validation.py`（launch 参数校验，别误删）。

### Task 3.3: 删死钩子与 decompiler

**Files:**
- Delete: `backend/app/services/run_lifecycle.py`、`backend/app/extensions/signaldeck_finance/hooks.py`、`backend/app/services/workflow_package_manifest_decompiler.py`
- Modify: `backend/app/services/run_service.py:1754-1766`（删遍历必空钩子列表的循环）、`backend/app/extensions/signaldeck_finance/registrars.py:50-52`、extension registry 中 `list_run_lifecycle_hooks`、`backend/app/services/workflow_package_export.py`（decompiler 调用改为直接返回存储的 `WorkflowPackage.manifest_source`）
- Tests: `git rm tests/test_workflow_package_manifest_decompiler.py`；export 测试改断言"导出 == 存储的 manifest_source（密钥字段剔除后）"。

- [ ] **Step 1: export 先写失败测试**（在 `test_workflow_package_export.py`）：
```python
def test_export_returns_stored_manifest_source(client, sample_package):
    resp = client.get(f"/api/workflow-packages/{sample_package['id']}/export")
    assert resp.status_code == 200
    assert "apiVersion: signaldeck" in resp.text  # 原文原样，非重组 YAML
```
- [ ] Step 2: 跑它确认失败（当前走 decompiler 重组）→ Step 3: 改 export 实现 + 删文件 → Step 4: mypy 清扫 → Step 5: 全量校验 → Step 6: Commit `refactor: export stored manifest source, drop decompiler and dead lifecycle hooks`

---

## Phase 4 — 删除 portfolio 记账域（全栈）

> **DECISION（用户可否决本 Phase）：** portfolios/balances/positions/trading-operations 是记账 CRUD 应用，不属于"迷你 Jenkins"。**保留** reports、templates（工作流产出物）与 market-data/news/sentiment **服务层**（agent 工具依赖）。若你想留着记账功能，跳过本 Phase，其余 Phase 不受影响。

### Task 4.1: 后端删除

**Files:**
- Delete: `backend/app/api/portfolios.py`、`balances.py`、`positions.py`、`trading_operations.py`、`market_data.py`（market-data 的 HTTP API 仅供 portfolio UI 用；服务层保留给 runtime tools）
- Delete: `backend/app/models/portfolio.py`、`position.py`、`balance.py`、`trading_operation.py`（保留 `market_quote.py`、`symbol_name_cache.py`、`report.py`、`text_template.py`）
- Delete: 对应 `repositories/`、`schemas/` 文件（`grep -l "portfolio\|position\|balance\|trading" app/repositories/ app/schemas/` 定位）
- Modify: `backend/app/api/reports.py:32,41`（删 `portfolioSlug` 过滤参数及 service 对应分支）、finance extension 的 registrar/router 贡献清单（删 portfolio 路由贡献，留 reports/templates/tools）
- Tests: `test_api.py` 删 portfolio/balance/position/trading 测试类（保留 reports/templates 部分）；`test_formatting.py` 若测 portfolio 格式化则相应删。

- [ ] Step 1: 删文件 → Step 2: mypy 清扫 → Step 3: 全量校验 → Step 4: Commit `refactor!: remove portfolio bookkeeping domain from backend`

### Task 4.2: 前端删除 + dashboard 重写

**Files:**
- Delete: `frontend/src/pages/portfolios/`、`frontend/src/hooks/use-portfolios*.ts`、`use-balances.ts`、`use-positions.ts`、`use-trading-operations.ts`、`use-market-data.ts`、`frontend/src/lib/api/portfolios.ts`、`balances.ts`、`positions.ts`、`trading-operations.ts`、`market-data.ts`、`frontend/src/lib/portfolio-analytics.ts`、`portfolio-analytics.test.ts`、`frontend/e2e/portfolios.spec.ts`、`frontend/e2e/functional.spec.ts`（内容即 Portfolio CRUD）
- Modify: `frontend/src/pages/dashboard.tsx` 重写为最近运行概览：
```tsx
import { PageContextBar } from "@/components/shared/page-context-bar";
import { useRuns } from "@/hooks/use-runs";
// 列表渲染复用 runs 列表页已有的行组件；dashboard = 最近 10 条 run + 各状态计数。
```
（具体行组件名以 `src/pages/runs/` 现有实现为准，直接复用，不新建组件。）
- Modify: finance scaffold 的路由清单（portfolio 路由项删除——scaffold 本身在 Phase 5 整体拆掉，这里只需让 typecheck 过）。
- Tests: `dashboard.test.tsx` 改为断言渲染最近运行标题（或直接删，e2e smoke 已覆盖 dashboard 可达）。

- [ ] Step 1: 删文件 → Step 2: 重写 dashboard → Step 3: tsc 清扫（query-keys、types、导航项）→ Step 4: 全量校验 + e2e → Step 5: Commit `refactor!: remove portfolio UI, dashboard shows recent runs`

---

## Phase 5 — 插件框架收拢为静态插件契约（全栈）

> **设计意图（用户确认）：** 插件是长期扩展点——后期要能容易地加新插件提供更多 tools，包括同能力不同实现。**保留插件契约，删除市场机制。**
>
> - **保留并强化：** owner 限定的 tool key 命名空间（`<extension>.<tool>` 天然支持同能力多实现）、manifest capability profile 按 key 选工具、扩展包私有代码边界、"新增插件 = 新包 + 注册一行"的路径。
> - **删除：** `import_module` 动态发现、registrar Protocol 层、`extension_dependency_service` 依赖解析、`ConstructionResult`/`Failure` 结果包装、启停 DB 状态 + 管理 API + 管理 UI。启停语义由"编辑一行静态列表"和 per-workflow capability profile 承担；真需要运行时开关再加回一个布尔列即可。

### Task 5.1: 定义最小插件契约

**Files:**
- Create: `backend/app/extensions/contract.py`：
```python
"""Extension contract: what a plugin contributes, declared statically."""
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from fastapi import APIRouter

# ToolDeclaration / provider 类型以 app/agents/runtime_tools/declarations.py
# 中现有类型为准（grep -n "class" app/agents/runtime_tools/declarations.py），
# 此处签名同名对齐，不新造平行类型。


@dataclass(frozen=True)
class Extension:
    key: str  # tool key 的 owner 前缀，如 "signaldeck_finance"
    api_routers: tuple[APIRouter, ...] = ()
    tool_declarations: tuple["ToolDeclaration", ...] = ()
    provider_factories: Mapping[str, Callable[..., object]] = field(default_factory=dict)
```
- Rewrite: `backend/app/extensions/registry.py` 收缩为静态清单（~30 行替换原 309 行）：
```python
from app.extensions.contract import Extension
from app.extensions.signaldeck_digital_oracle import EXTENSION as DIGITAL_ORACLE
from app.extensions.signaldeck_finance import EXTENSION as FINANCE

INSTALLED_EXTENSIONS: tuple[Extension, ...] = (FINANCE, DIGITAL_ORACLE)


def _assert_unique_tool_keys() -> None:
    seen: set[str] = set()
    for ext in INSTALLED_EXTENSIONS:
        for decl in ext.tool_declarations:
            key = f"{ext.key}.{decl.name}"  # 字段名对齐现有 declaration 类型
            if key in seen:
                raise RuntimeError(f"duplicate tool key: {key}")
            seen.add(key)


_assert_unique_tool_keys()  # import 时炸，装错插件起不来
```
- Test: `backend/tests/test_extension_contract.py`：
```python
from app.extensions.registry import INSTALLED_EXTENSIONS

def test_installed_extensions_expose_unique_tool_keys():
    keys = [
        f"{ext.key}.{decl.name}"
        for ext in INSTALLED_EXTENSIONS
        for decl in ext.tool_declarations
    ]
    assert len(keys) == len(set(keys))

def test_every_extension_declares_key():
    assert all(ext.key for ext in INSTALLED_EXTENSIONS)
```

- [ ] **Step 1:** 写 contract.py + 失败测试 → **Step 2:** 两个扩展包各建 `EXTENSION` 实例（内容从各自 `registrars.py` 现有贡献平移：`grep -n "def register\|APIRouter" app/extensions/*/registrars.py` 列贡献清单）→ **Step 3:** 测试转绿 → **Step 4:** Commit `refactor(extensions): static Extension contract`

### Task 5.2: 消费方切换 + 删市场机制

**Files:**
- Modify: `backend/app/api/router.py`——registry 循环改为遍历 `INSTALLED_EXTENSIONS` 的 `api_routers`：
```python
api_router = APIRouter(prefix="/api/v1")
for ext in INSTALLED_EXTENSIONS:
    for router in ext.api_routers:
        api_router.include_router(router)
```
- Modify: `backend/app/agents/runtime_tools/registry.py` / `tool_catalog`——工具目录从 `INSTALLED_EXTENSIONS` 的 `tool_declarations` 构建（owner 限定 key 生成逻辑保留不动）。
- Modify: `dependencies.py`——`get_execution_provider_bundle` 从 `provider_factories` 直接构造；删 extension service provider。
- Delete: 两个扩展的 `registrars.py`、`signaldeck_finance/provider_factories.py` 与 `signaldeck_digital_oracle/factory.py` 中的 `ConstructionResult`/`Failure` 包装（工厂改普通函数直接返回实例，构造失败就抛异常）、`backend/app/services/extension_service.py`、`extension_dependency_service.py`、`extension_gate.py`、`backend/app/models/extension.py`、`backend/app/api/extensions.py`
- Delete tests: `test_extension_registry.py`、`test_extensions_api.py`、`test_extension_lifecycle_matrix.py`
- Modify: `platform_router.py`（删 extensions router 注册）
- Create: `docs/writing-extensions.md`（≤60 行）：Extension 契约字段说明、新插件三步（建包 → 声明 `EXTENSION` → `INSTALLED_EXTENSIONS` 加一行）、同能力多实现示例（两个插件声明同名 tool，key 前缀区分，manifest capability profile 选用哪个）。

**Interfaces:**
- Consumes: Task 5.1 的 `INSTALLED_EXTENSIONS`、`Extension`。
- Produces: `/api/tools` 返回全部已装插件的工具（无 disabled 状态）；`/api/extensions` 消失；manifest capability profile 校验逻辑不变。

- [ ] **Step 1:** 切换三个消费方（router/tool_catalog/dependencies），旧机制暂存，跑全量校验（应绿）→ **Step 2:** 删市场机制文件 → **Step 3:** mypy 清扫（重点 `run_service.py`、`workflow_package_preflight.py` 中 extension_disabled 分支——整个分支删除）→ **Step 4:** 清扫测试中 `extension_disabled` 断言（`grep -rln "extension_disabled\|disabled_tool" tests/`）→ **Step 5:** 写 `docs/writing-extensions.md` → **Step 6:** 全量校验 → **Step 7:** Commit `refactor!: replace plugin marketplace machinery with static extension contract`

### Task 5.3: 前端插件宿主拆除

插件贡献的是 **tools（后端侧，agent 消费）**，不是 UI。新插件不需要注入前端路由；reports/templates 路由随 Phase 4 后已是仅存贡献，内联为静态路由。若未来某插件真要带 UI，届时再加前端注入点。

**Files:**
- Modify: `frontend/src/routes.ts:5,16`——删 `assembleFinanceWorkspaceRoutes()` 调用，把 `src/extensions/signaldeck-finance/scaffold.ts` 中 reports/templates 路由对象（Phase 4 后仅剩这些）按现有格式**手工内联**进 `routes.ts` 的静态数组（lazy import 语法照抄 scaffold 中的 `Component: (await import("@/pages/templates/list")).TemplateListPage` 形式）。
- Delete: `frontend/src/extensions/`（整目录：registry.ts、runtime.tsx、runtime-helpers.ts、types.ts、两个 scaffold）、`frontend/src/pages/extensions/`、`frontend/src/hooks/use-extensions*.ts`、`frontend/src/lib/api/extensions.ts`、`frontend/e2e/extensions.spec.ts`
- Modify: routes.ts 删 `extensions` 路由项（line 19）、导航项、query-keys、routes.test.tsx 相关断言。

- [ ] Step 1: 内联路由 → Step 2: 删目录 → Step 3: tsc 清扫 → Step 4: 全量校验 + e2e → Step 5: Commit `refactor!: inline extension routes, remove frontend plugin host`

---

## Phase 6 — 后端收拢

### Task 6.1: model_gateway 9 文件折叠为 3

**Files:**
- Merge into `backend/app/services/model_gateway_openai.py`: `model_gateway_tool_strategy.py`、`model_gateway_policy_strategy.py`、`model_gateway_tool_retry.py`、`model_gateway_provider_retry.py`（各自的 select/retry 函数以私有函数形式并入；每个"strategy 选择器"本质是一个 if/else，直接内联到调用点）
- Modify: `model_gateway_dto.py`——删 `ModelProtocolAdapter` Protocol（单实现），调用方直接用 `OpenAIProtocolAdapter` 具体类型；删除未被 `invoke` 调用的 `_selected_strategies_for_request` 聚合器（先 `grep -rn "_selected_strategies_for_request" app tests` 确认无调用方）。
- 保留: `model_gateway.py`（入口）、`model_gateway_openai.py`、`model_gateway_openai_responses.py`、`model_gateway_output_validation.py`。
- Tests: `test_execution_providers.py` 等现有测试是安全网；import 路径变更处同步改。

- [ ] Step 1: 逐文件搬函数（搬一个跑一次 pytest，防大爆炸）→ Step 2: 删空文件 → Step 3: 全量校验 → Step 4: Commit `refactor: collapse model_gateway strategy modules into openai adapter`

### Task 6.2: 仓储层去伪装 + 微模块折叠

**Files:**
- Modify: `backend/app/repositories/base.py`——删 `create`/`update`（均为 `add` 的一行转发），调用方直接用 `add`；`get`/`_list` 保留（有类型收窄价值）。
- Modify: `backend/app/services/execution_ownership.py`（15 行）内容并入唯一调用方后删除（`grep -rn "execution_ownership" app` 定位）。
- 删除 Phase 2-5 后残留的单实现 Protocol：`grep -rn "class.*Protocol" app --include="*.py"` 列清单，对每个只有一个实现且实现同仓的：删 Protocol，调用方直接标注具体类。已知目标：`run_queue_service.RunExecutor`、`StaleMemoryRunService`（Phase 2 后应已死）、`workflow_package_schedule_service.RunServiceFactory`。
- [ ] Step 1: repo 别名删除 + mypy 清扫 → Step 2: Protocol 清单逐个处理 → Step 3: 全量校验 → Step 4: Commit `refactor: drop pass-through repo aliases and single-impl protocols`

---

## Phase 7 — 生产短板补齐

### Task 7.1: 密钥加密换 Fernet

**Files:**
- Modify: `backend/pyproject.toml`（`cd backend && uv add "cryptography>=43"`）
- Modify: `backend/app/models/base.py:47-160` 附近——`EncryptedJSONB` 的加解密内核替换：
```python
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def _build_fernet(key_material: str) -> Fernet:
    digest = hashlib.sha256(key_material.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))
```
`process_bind_param` 用 `fernet.encrypt(json.dumps(value).encode())`，`process_result_value` 用 `fernet.decrypt(...)`，捕获 `InvalidToken` 抛出与现状同类的解密错误。删除手写的 nonce/keystream/XOR/HMAC 代码。payload `version` 字段写 `2`。
- Test: 在现有加密测试文件（`grep -rln "EncryptedJSONB\|encryption" tests/` 定位）中替换为：round-trip 加解密、错 key 解密抛错、密文非明文三条行为测试。

- [ ] Step 1: 写/改失败测试 → Step 2: 换实现 → Step 3: 全量校验 → Step 4: Commit `feat(security): replace hand-rolled cipher with Fernet`

### Task 7.2: Bearer token 鉴权（可选启用）

**Files:**
- Create: `backend/app/core/auth.py`：
```python
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

_EXEMPT_PATHS = {"/health", "/ready"}


class BearerTokenMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: str) -> None:
        super().__init__(app)
        self._expected = f"Bearer {token}"

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _EXEMPT_PATHS or request.method == "OPTIONS":
            return await call_next(request)
        if request.headers.get("Authorization") != self._expected:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return await call_next(request)
```
- Modify: `backend/app/core/config.py` 加 `api_token: str | None = None`（env `SIGNALDECK_API_TOKEN`，遵循现有 settings 命名前缀写法）；production 模式校验处（`config.py:160-180` 附近）追加：production 且未设 token → 启动时打 WARNING 日志（不硬性拒绝——反向代理鉴权也是合法部署）。
- Modify: `backend/app/main.py`：CORS 中间件之后
```python
if settings.api_token:
    app.add_middleware(BearerTokenMiddleware, token=settings.api_token)
```
- Modify: `frontend/src/lib/api-client.ts`——请求统一加头：
```ts
const token = localStorage.getItem("signaldeck.apiToken");
if (token) headers.set("Authorization", `Bearer ${token}`);
```
401 响应时：`const t = window.prompt("API token"); if (t) { localStorage.setItem("signaldeck.apiToken", t); /* retry once */ }`
（`// ponytail: prompt-based token entry; build a settings page if multi-user ever happens.`）
- Test: `backend/tests/test_auth_middleware.py`：
```python
def test_requests_rejected_without_token(client_with_token):
    assert client_with_token.get("/api/runs").status_code == 401

def test_requests_accepted_with_token(client_with_token):
    resp = client_with_token.get(
        "/api/runs", headers={"Authorization": "Bearer test-token"}
    )
    assert resp.status_code == 200

def test_health_exempt(client_with_token):
    assert client_with_token.get("/health").status_code == 200
```
（`client_with_token` fixture：复制 conftest 现有 client fixture，设 `api_token="test-token"`。）

- [ ] Step 1: 失败测试 → Step 2: 实现 → Step 3: 前后端全量校验（e2e 不设 token，行为不变）→ Step 4: Commit `feat(security): optional bearer-token auth via SIGNALDECK_API_TOKEN`

### Task 7.3: Run 取消

**Files:**
- Modify: `backend/app/models/run.py`——加列 `cancel_requested_at: Mapped[datetime | None]`；run 状态枚举加 `cancelled`（枚举定义位置 `grep -rn "queued" app/models/run.py app/schemas/` 定位）。
- Modify: `backend/app/api/runs.py`——新端点：
```python
@router.post("/{run_id}/cancel", response_model=RunRead)
def cancel_run(run_id: int, service: RunServiceDep) -> RunRead:
    return service.cancel_run(run_id)
```
- Modify: `backend/app/services/run_service.py`——`cancel_run`：状态 `queued` → 直接置 `cancelled`（并释放队列行，复用现有 lease 释放路径）；`running` → 写 `cancel_requested_at`；终态 → 409。
- Modify: 执行循环（`agent_execution_service.py` / `run_scheduler.py`，用 `grep -n "for step\|next_step" app/services/agent_execution_service.py app/workers/run_scheduler.py` 定位步进点）——每个 step 开始前重读 run 行，`cancel_requested_at` 非空 → 置 `cancelled`、停止执行、写入终止说明（复用现有失败落库路径，消息 `"cancelled by operator"`）。
- Modify: 前端 `src/pages/runs/` 详情页——状态为 queued/running 时显示 Cancel 按钮；`lib/api/runs.ts` 加 `cancelRun`；`use-runs.ts` 加 mutation + invalidate。
- Test: `backend/tests/test_run_cancel.py`：
```python
def test_cancel_queued_run_marks_cancelled(client, queued_run):
    resp = client.post(f"/api/runs/{queued_run['id']}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"

def test_cancel_finished_run_conflicts(client, succeeded_run):
    assert client.post(f"/api/runs/{succeeded_run['id']}/cancel").status_code == 409

def test_running_run_stops_at_next_step_boundary(...):
    # 用 tests/fake_openai_provider.py 的假 provider 驱动一个两步 run，
    # 第一步完成后调 cancel，断言 run 终态 cancelled 且 step 2 未执行。
```
（fixture 构造照抄 `test_workflow_package_run_contracts.py` 现有 run 提交流程。）

- [ ] Step 1: 失败测试 → Step 2: 模型/端点/服务实现 → Step 3: 执行循环协作检查 → Step 4: 前端按钮 → Step 5: 前后端全量校验 → Step 6: Commit `feat(runs): cancel endpoint with cooperative worker check`

### Task 7.4: 请求级可观测性

**Files:**
- Modify: `backend/app/core/telemetry.py` 或 `main.py`——logfire 配置后加 `logfire.instrument_fastapi(app)`（放在 app 构造处，token 未设时 logfire 为 no-op，零成本）。
- [ ] Step 1: 加一行 + 启动 smoke（`uv run uvicorn app.main:app` 起得来即可）→ Step 2: 全量校验 → Step 3: Commit `feat(observability): instrument FastAPI with logfire`

### Task 7.5: Run 保留期

**Files:**
- Modify: `backend/app/core/config.py` 加 `run_retention_days: int | None = None`。
- Modify: `backend/app/workers/run_scheduler.py`——主循环每 tick 后（已持 advisory lock，天然单实例）：
```python
if settings.run_retention_days is not None:
    pruned = run_repository.delete_runs_older_than(settings.run_retention_days)
```
- Modify: `backend/app/repositories/run.py` 加 `delete_runs_older_than(days) -> int`——按 `created_at` 删终态 run（queued/running 不删）；先 `grep -n "cascade" app/models/run*.py` 确认子表级联，无级联则先删子表行。
- Test: `test_run_retention.py`——造一条 30 天前的 succeeded run（直接 UPDATE created_at），调用 repo 方法，断言删除且 running run 保留。
- [ ] Step 1: 失败测试 → Step 2: 实现 → Step 3: 全量校验 → Step 4: Commit `feat(runs): optional run retention pruning`

### Task 7.6: 部署文档

**Files:**
- Modify: `README.md`——新增 "Security" 一节（**必须**二选一：设 `SIGNALDECK_API_TOKEN`，或置于鉴权反向代理/oauth2-proxy/Tailscale 之后；给一段 nginx `auth_basic` 示例）；新增 "Backup" 一节（`pg_dump` 一行 + 恢复一行 + "run 历史可通过 SIGNALDECK_RUN_RETENTION_DAYS 控制"）；"Schema changes" 一句：无迁移框架，schema 变更需重建库。
- [ ] Step 1: 写 → Step 2: Commit `docs: security, backup, and schema-change policy`

---

## Phase 8 — 测试瘦身（只处理存活功能的冗余）

### Task 8.1: 共享 manifest fixture 模块

**Files:**
- Create: `backend/tests/fixtures/workflow_manifests.py`：
```python
"""Single source for test workflow-package manifests."""
import textwrap

_BASE = textwrap.dedent("""\
    apiVersion: signaldeck.workflowPackage/v1
    ...  # 以 tests 中出现频率最高的那份 52 行 manifest 为蓝本，原样收编
""")

def base_manifest(**overrides: str) -> str:
    """overrides 支持 name=, model_binding=, tools=<yaml片段>, output_schema=<yaml片段>."""
```
实现方式：解析为 dict（用 ruamel.yaml，已是依赖）→ 应用 overrides → dump。**不用字符串 replace**。
- Modify: `grep -rln "apiVersion: signaldeck" tests/ --include="*.py"` 命中的每个文件（Phase 2-5 后预计 ~12 个）——内联 YAML 块替换为 `base_manifest(...)` 调用；`test_workflow_package_runtime_api.py` 的 10 个 `_package_source_with_*` 字符串替换变体全部改为 builder 参数。
- [ ] Step 1: 建 builder + 自测（round-trip 解析断言）→ Step 2: 逐文件替换，每 3 个文件跑一次 pytest → Step 3: 全量校验 → Step 4: Commit `test: shared manifest fixture builder replaces 50+ inline YAML blocks`

### Task 8.2: 校验断言归位，删 preflight 测试文件

**Files:**
- Delete: `backend/tests/test_workflow_package_preflight.py`（Phase 2/5 清扫后的残余整文件删）
- Modify: `backend/tests/test_workflow_package_runtime_api.py`——该文件中逐字段快照错误信封（`issue`/`code`/`field`/`surface` 44 处字面断言）的测试收缩为：HTTP 层只断言 `status_code == 422` + 错误列表非空 + 顶层 `code` 值；字段级校验断言只允许存在于 `test_workflow_package_manifest_parser.py`/`_compiler.py`。保留 ~5 条行为测试覆盖原 preflight 关键场景（无效 model binding、缺失 tool key、坏 output schema、坏 workflow 图、重复 agent 名）——若 parser/compiler 测试已覆盖则不新增。
- [ ] Step 1: 对照 preflight 文件列出其独有场景清单 → Step 2: 迁移独有场景到 parser 测试（用 8.1 的 builder）→ Step 3: 删文件 + 收缩信封断言 → Step 4: 全量校验 → Step 5: Commit `test: single-layer validation assertions, drop preflight suite`

### Task 8.3: test_runtime_tools.py 减肥（10,316 行 → 目标 ≤5,500）

**Files:** Modify `backend/tests/test_runtime_tools.py`
- 删：28 个 Pydantic 序列化/camelCase/`reject_raw`/frozen 测试（测框架不测业务）。
- 合：16 个 registry 测试 → 4 个 `@pytest.mark.parametrize` 用例（dedup、排序、深拷贝、目录形状）。
- 并：20 个 `_Fake*`/`_Recording*` provider 类 → 2-3 个可配置 fake（构造参数控制返回/异常/记录），放 `tests/fixtures/fake_providers.py` 与现有 `fake_openai_provider.py` 并列。
- [ ] Step 1: 删框架测试 → Step 2: parametrize → Step 3: 合 fake → Step 4: 全量校验（业务用例数不减：`uv run pytest tests/test_runtime_tools.py --collect-only -q | tail -1` 前后对比，只允许框架类用例消失）→ Step 5: Commit `test: dedupe runtime tools suite, consolidate fakes`

### Task 8.4: 删 OpenAPI 快照类测试

**Files:** `grep -rln "openapi" backend/tests/ --include="*.py"` → `test_workflow_package_openapi.py` 整文件删；其余文件中对 OpenAPI schema 逐字段断言的测试删除（FastAPI 生成器不需要我们测）。保留：断言"某端点存在于 schema"的一条冒烟即可。
- [ ] Step 1: 删 → Step 2: 全量校验 → Step 3: Commit `test: drop OpenAPI generator snapshots`

### Task 8.5: 前端 jsdom 重复渲染测试删除

**Files:**
- Delete（与 e2e 重复覆盖的整页渲染测试）: `frontend/src/pages/runs/detail.test.tsx`（3,682 行）、`frontend/src/pages/scheduled-tasks/` 下 `detail.test.tsx`、`list.test.tsx`、`frontend/src/pages/workflow-packages/` 下 `launch.test.tsx`、`resource-editors.test.tsx`
- 保留：纯逻辑测试（`lib/format.test.ts`、`report-grouping.test.ts`、`workflow-options.test.ts`、hooks 状态机测试如 `use-resource-filter-state.test.ts`）。
- 前置校验：对每个待删文件，确认对应 e2e spec 覆盖同一路由主流程（`runs.spec.ts`、`scheduled-tasks.spec.ts`、`workflow-packages.spec.ts` 中 `grep` 路由路径）。若某关键交互仅 jsdom 测试覆盖（如 launch 表单的某编辑器分支），把该场景**加进对应 e2e spec**再删。
- [ ] Step 1: 覆盖比对 → Step 2: 缺口补进 e2e → Step 3: 删文件 → Step 4: 全量校验 + e2e → Step 5: Commit `test: drop jsdom page tests duplicated by e2e`

### Task 8.6: e2e 壳测试三合一

**Files:**
- Create: `frontend/e2e/shell.spec.ts` = `smoke.spec.ts`(22) + `navigation.spec.ts`(159) + `shell-regression.spec.ts`(405) 去重合并：一条"侧边栏含全部主路由并可导航"、一条"未知路由渲染壳"、一条"移动端 overflow/宽度模式"。三文件删除。
- [ ] Step 1: 合并（保留断言最全的版本，删语义重复者）→ Step 2: `pnpm test:e2e` → Step 3: Commit `test: merge three shell e2e specs into one`

### Task 8.7: 路由元数据注册表内联

**Files:**
- Modify: `frontend/src/routes.ts`——`routes.metadata.ts`（584 行）的 title/breadcrumb/nav 字段直接内联进各路由对象的 `handle`（照抄现有 scaffold 内联格式）；删 `assertRouteMetadataCoverage()` 运行时断言。
- Delete: `frontend/src/routes.metadata.ts`；`routes.test.tsx`（1,124 行）收缩为一条"每个路由渲染不炸"的循环用例（~60 行）。
- [ ] Step 1: 内联 → Step 2: tsc 清扫 → Step 3: 全量校验 + e2e → Step 4: Commit `refactor: inline route metadata, drop coverage assertion`

---

## Phase 9 — 死代码清扫与文档重写

### Task 9.1: 前端死导出清扫

- [ ] **Step 1:** `git rm frontend/src/components/shared/resource-row-card.tsx frontend/src/components/shared/resource-row-card.test.tsx`（已核实零非测试引用者）。
- [ ] **Step 2:** `cd frontend && pnpm dlx knip` → 对报告中每个未使用导出/文件：确认后删除。已知候选：`constraint-inspector`、`metric-card`、`resource-toolbar` 等单引用"shared"组件若在 Phase 4/5 后失去唯一调用方则死；`query-keys.ts` 删掉已无对应 API 的 key 段；`lib/platform-authoring/` 中 schema-composer 相关文件若 knip 报告无引用则删（launch 用的 `generated-form`/`launch-input-state` 保留）。
- [ ] **Step 3:** 全量校验 + e2e → Commit `chore: remove dead exports and components`

### Task 9.2: 后端死代码清扫

- [ ] **Step 1:** `cd backend && uv run ruff check app --select F401,F841`；再用 `uv run python -c "import app.main"` 冒烟。
- [ ] **Step 2:** `grep -rn "class.*Protocol" app --include="*.py"` 复查 Phase 6 后残余单实现 Protocol，同法处理。`api/memory.py` 已删，确认 `WorkflowMemoryReviewService` Protocol 无残留：`grep -rn "WorkflowMemoryReviewService" app`。
- [ ] **Step 3:** 全量校验 → Commit `chore: backend dead code sweep`

### Task 9.3: AGENTS.md 收编 + docs/ 重写

- [ ] **Step 1:** `git ls-files "*AGENTS.md"` 列全部（预计 35+）。保留：仓库根 `AGENTS.md`。其余全删；根文件重写为 ≤80 行：项目定位（迷你 Jenkins for LLM agents）、目录一览、全量校验命令、"schema 变更 = 重建库"、安全部署两句。`frontend/src/components/shared/docs/` 四个 md 删除。
- [ ] **Step 2:** `docs/` 重写：`prd.md`/`spec.md`/`requirements.md` 合并为一个 `docs/product.md`（≤150 行，描述迁移后的实际形态）；`data-model.md` 更新（删 memory/portfolio/fork/extension 表）；`test-plan.md` 删除（CI 即测试计划）。
- [ ] **Step 3:** README.md 首段重写：从 "portfolio-tracking stack" 改为 workflow runner 定位；删除已亡路由/API 的描述段落。
- [ ] **Step 4:** Commit `docs: rewrite for mini-jenkins scope`

### Task 9.4: 终检

- [ ] **Step 1:** 前后端全量校验 + e2e 全绿。
- [ ] **Step 2:** LOC 对比：`git ls-files '*.py' '*.ts' '*.tsx' | xargs wc -l | tail -1` vs `/tmp/loc-baseline.txt`，把差值写进最终 commit message。
- [ ] **Step 3:** Docker 冒烟：`docker build -t signaldeck . && docker compose up -d`，访问 `/ready` 与前端首页。
- [ ] **Step 4:** Commit `chore: migration complete — mini-jenkins scope` + 汇总（删除行数、新增功能清单）。

---

## Phase 10 —（可选，默认不排期）manifest 编译管线合并

`parser → compiler → PackageExecutionPlanBuilder`（24 个中间 dataclass）合并为 parser → 单趟 plan 构建。收益 ~1,500 行；风险：核心执行引擎重写。**仅当 Phase 8 后的行为级测试套件全绿且团队仍觉得管线维护痛时再做**。做法：以 `test_workflow_package_execution_plan.py` + runtime_api 行为测试为安全网，把 `package_execution_plan_builder.py` 的输出类型作为 compiler 的直接产物，删除中间 `packageDefinition`/`compiledPlan` 双表示。此处不展开步骤——届时按 writing-plans 流程单独出计划。

---

## Self-Review 记录

- 审计四份报告的每条发现均有对应 Task 或"明确不做"条目（memory→P2、fork/preset/钩子/decompiler→P3、portfolio→P4、插件框架→P5、gateway/repo/Protocol→P6、鉴权/取消/Fernet/logfire/保留期/备份文档→P7、测试六项→P8、死组件/AGENTS.md/docs→P9、管线合并/schema-compiler/schedule 合并/DI→不做清单）。
- 类型一致性：`seed_preset_packages`/`fail_inflight_runs`（P1 定义，P1 使用）；`base_manifest`（8.1 定义，8.1-8.2 使用）；`cancel_run`/`delete_runs_older_than`（P7 内自洽）。
- 已知不确定点均给出 grep 定位命令而非虚构行号；虚构文件名为零（全部来自实际 `ls`/`grep` 输出）。
