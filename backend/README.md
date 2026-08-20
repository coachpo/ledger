# SignalDeck Backend

SignalDeck 的 FastAPI backend，提供 Templates/Reports 扩展面和当前 agent-platform 面。

## 本地开发

最简单的全栈路径是在仓库根目录运行 `./start.sh`。它使用根目录 `docker-compose.yml`，从当前源代码构建仅用于本地/演示的应用镜像，并在 Docker 中启动 `db` 与 `app` 服务。

应用默认地址为 `http://localhost:${APP_PORT:-8080}`。Nginx 在 app 容器中运行，将 `/health`、`/ready`、`/api/` 和 `/api/v1/` 转发给内部 FastAPI backend。默认不会把 backend、scheduler 或 PostgreSQL/pgvector 直接发布到宿主机端口。

启动脚本保留根 Compose 的环境变量控制，包括 `APP_PORT`、`POSTGRES_PASSWORD`、`AGENT_PLATFORM_ENCRYPTION_KEY` 和 `VITE_API_BASE_URL`。

如果要在全栈之外直接运行 backend 测试：

```bash
uv sync
uv run pytest
```

backend 始终需要 PostgreSQL。全栈启动从根 Compose 的 `db:5432` 获取数据库；Docker 外运行测试时可使用 `TEST_DATABASE_URL` 或 `DATABASE_URL` 指定 PostgreSQL，否则测试 fixture 会启动或复用一个带可用 host port 的本地 PostgreSQL 容器。

## Model Connections

保持 `AGENT_PLATFORM_ENCRYPTION_KEY` 设置，使保存的 model-connection secret 静态加密。local/development 可以使用默认 placeholder；`SIGNALDECK_RUNTIME_MODE=production` 要求显式 `DATABASE_URL` 和非 placeholder 的 encryption key。

## API 面

- `/health`：进程存活；
- `/ready`：就绪状态，只有 backend 能连接 PostgreSQL 时返回 200；
- `/api/v1`：Templates 和 Reports；
- `/api/workflow-packages`：包 authoring、校验、导入、导出、preflight、launch metadata 和 launch；
- `/api/schedules`：面向 Workflow Package 的 Scheduled Task；
- `/api/model-connections`：全局 provider binding 和安全的 connection test；
- `/api/tools`：只读的 server-declared tool metadata；
- `/api/runs`：run list/detail、cancel、delete、root-parameter rerun 和 immutable snapshot provenance。

Scheduled Task 使用 `interval`、`daily`、`weekly` 或 `monthly` recurrence 和有效 IANA timezone。日、周、月计划按 local wall-clock 计算，DST spring gap 向前移动到下一个有效 minute，DST fall repeated local time 只在最早有效 instant 触发一次；月度无效日期跳过。overlap policy 为 `skip` 或 `queue`，misfire policy 为 `skip` 或 `catchUpOne`，后者受 `misfireGraceSeconds` 限制。

Scheduled input template 只能是 JSON object。renderer 支持 `schedule`、`fire`、`window`、`lastRun` 和 `vars` placeholder；完整占位符保留 JSON 类型，嵌入式 placeholder 转为字符串；渲染结果必须通过 package workflow input schema。未保存 preview 使用 `POST /api/schedules/preview`，保存后的 preview 使用 `POST /api/schedules/{scheduleId}/preview`，两者都是 ephemeral。schedule read 会省略 `inputTemplate` 和 `templateVars`，客户端应保存显式 draft。run-now 要求 `idempotencyKey` 与 `scheduledFor`，并通过 scheduled-run path 创建 manual fire。删除 schedule 返回 204，停止未来自动化并保留已有 run 的 `scheduleProvenance`。

Rerun endpoint 为 `GET /api/runs/{runId}/rerun-draft` 和 `POST /api/runs/{runId}/reruns`；它们使用 root launch `parameters`。`POST /api/runs/{runId}/cancel` 会立即取消 queued run，并在 running run 的 step boundary 协作停止。

## 测试

测试套件会创建并删除临时 PostgreSQL database。Docker 外运行 `uv run pytest` 时，`TEST_DATABASE_URL` 或 `DATABASE_URL` 必须指向有权限连接 `postgres` 并创建/删除 database 的 PostgreSQL。

```bash
uv run ruff check app tests
uv run black --check app tests
uv run isort --check-only app tests
uv run mypy app
uv run pytest
```

## Docker Compose

根目录 `docker-compose.yml` 是本地/演示全栈 Compose 文件，在 `db` 中启动 PostgreSQL/pgvector，在 `app` 中启动组合 Nginx/FastAPI/scheduler。

```bash
docker compose -f ../docker-compose.yml up --build --remove-orphans
```

从仓库根目录优先使用 `./start.sh`；它执行同一命令并在前台输出日志。宿主机只发布 app/Nginx 端口，PostgreSQL 保持在 Docker network，FastAPI 位于 Nginx 后面。

重置容器管理的 PostgreSQL 数据：

```bash
docker compose -f ../docker-compose.yml down -v
```

## 备注

- `app/db/session.py` 使用 `create_all`、bundled package seed 和 startup recovery；没有 live Alembic path。
- schema 变化需要重建数据库，直到项目具备明确的数据升级策略。
- Playwright E2E 通过 `frontend/scripts/start-playwright-backend.mjs` 在 8001 启动专用 backend，默认使用 `QUOTE_PROVIDER_BACKEND=deterministic`，并和 4173 的 frontend preview 配对。
- `frontend` E2E helper 默认 `VITE_API_BASE_URL=http://127.0.0.1:8001/api/v1`。
- `docs/` 包含产品、架构、数据模型和扩展编写文档。
- 根 workflow 检查 `backend/VERSION` 与 `backend/pyproject.toml`，并构建 linux/amd64 与 linux/arm64 的 backend/frontend GHCR image。
- 仓库级 setup、验证和 frontend wiring 见根 [`CONTRIBUTING.md`](../CONTRIBUTING.md)。
