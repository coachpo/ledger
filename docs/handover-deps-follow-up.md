# 交接：依赖升级遗留问题（2026-07-09）

背景：15 个 Dependabot PR 已全部合并。其中两个 PR 为了合入做了临时妥协，需要后续收尾。本文保留当前状态、验收标准与验证命令。

## 当前状态

- `react-hooks/set-state-in-effect` 前端收尾已完成；`frontend/eslint.config.js` 不再降级该规则。
- FastAPI `<0.137` 封顶仍未解锁；PyPI 上 Logfire 4.37.0 仍要求 `opentelemetry-sdk<1.43.0`。
- 两个 FastAPI 路由挂载测试已预先改为从 `app.openapi()["paths"]` 读取公开路径集合。

## 已完成：`react-hooks/set-state-in-effect` 降级为 warn（来自 PR #12）

### 现状

`eslint-plugin-react-hooks` 已升到 7.1.1。v7 的 recommended 配置新增 `set-state-in-effect` 规则。16 处存量违规已重构，`frontend/eslint.config.js` 不再覆盖该规则。

### 验收

```bash
cd frontend && pnpm lint && pnpm typecheck && pnpm test:run && pnpm test:e2e
```

要求 lint 为 0 error、0 warning，且该规则不再出现；`frontend/eslint.config.js` 中无 `set-state-in-effect` override。

## 遗留：FastAPI 封顶 `<0.137`（来自 PR #6）

### 现状

`backend/pyproject.toml` 中 FastAPI 被钉在 `>=0.136.3,<0.137`。原因链：

1. FastAPI 0.137 起，`include_router` 挂载的路由不再平铺进 `app.routes`，而是嵌套在私有的 `_IncludedRouter` 对象里；
2. `opentelemetry-instrumentation-fastapi` `<0.64b0` 的 `_get_route_details` 在 partial route match（典型是 POST 打到 GET-only 路由返回 405）时访问 `starlette_route.path`，`_IncludedRouter` 没有该属性，运行时会直接 `AttributeError`；
3. 修复版 `0.64b0` 依赖 otel-sdk 1.43，而 Logfire（截至 4.37.0，当时最新）要求 `opentelemetry-sdk<1.43.0`，形成依赖死锁。

### 解锁条件

Logfire 发布支持 otel-sdk 1.43 的版本。检查方式：

```bash
curl -s https://pypi.org/pypi/logfire/json | python3 -c "
import json,sys; d=json.load(sys.stdin)
print(d['info']['version'])
print([r for r in d['info'].get('requires_dist') or [] if 'opentelemetry-sdk' in r])"
```

看到 sdk 上限放宽到 `<1.44` 或更高后再动手。

### 解锁后的操作

1. 修改 `backend/pyproject.toml`：删除 FastAPI 的封顶注释，将约束恢复为当时确认的目标范围，例如 `"fastapi>=0.139.0,<1.0"`。
2. 重新解析锁文件并确认 otel instrumentation 达到 `>=0.64b0`：

   ```bash
   cd backend
   uv lock --upgrade-package fastapi --upgrade-package logfire \
           --upgrade-package opentelemetry-instrumentation-fastapi
   grep -A2 'name = "opentelemetry-instrumentation-fastapi"' uv.lock | grep version
   ```

3. 保留两个已修复的路由测试；它们不应重新依赖私有 `_IncludedRouter`：
   - `backend/tests/test_api.py::test_agent_platform_routes_mount_package_first_api`
   - `backend/tests/test_api.py::test_finance_workspace_product_routes_remain_mounted_for_templates_and_reports`

   当前做法是从公开 OpenAPI 读取路径集合：

   ```python
   route_paths = set(app.openapi()["paths"])
   ```

4. 确认 405 场景不再崩：`backend/tests/test_tool_catalog_api.py::test_tools_catalog_route_is_get_only` 必须通过。

### 验收

```bash
docker run -d --name pg-test -e POSTGRES_DB=signaldeck -e POSTGRES_USER=signaldeck \
  -e POSTGRES_PASSWORD=signaldeck -p 25432:5432 postgres:16-alpine

cd backend
export DATABASE_URL=postgresql+psycopg://signaldeck:signaldeck@127.0.0.1:25432/signaldeck
export TEST_DATABASE_URL=$DATABASE_URL
uv sync
uv run ruff check app tests && uv run black --check app tests \
  && uv run isort --check-only app tests && uv run mypy app && uv run pytest
```

要求全绿，且 `pyproject.toml` 不再保留 FastAPI 封顶注释。

## 附注

- 本文相关 `ponytail:` 待办只剩 `backend/pyproject.toml` 的 FastAPI 封顶注释；仓库中还有其他不属于本交接范围的 `ponytail:` 技术债标记。
- 根目录 `Dockerfile` 与 `frontend/Dockerfile` 已改为 `npm install -g pnpm`（Node 26 移除了内置 corepack）；这不是遗留，后续升级 Node 镜像不要把 `corepack enable` 加回来。
- 根目录 Dockerfile CI 不构建（docker-images workflow 只构建 `./frontend`、`./backend` 两个 context），改动它时需要本地 `docker build .` 自验。
