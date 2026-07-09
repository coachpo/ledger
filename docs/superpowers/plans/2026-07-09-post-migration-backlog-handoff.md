# 终审遗留待办执行交接 — Post-Migration Backlog

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to execute task-by-task. Steps use checkbox (`- [ ]`) syntax.

**读者：** 执行本轮修复的开发者（Claude Code + superpowers）。
**需求来源：** [`2026-07-09-post-migration-backlog.md`](./2026-07-09-post-migration-backlog.md)（终审发现清单）+ 本文档的任务分解。两者冲突以本文档为准。
**目标：** 修完全部 P0 + P1，使**以 GHCR 发布镜像方式的生产部署**真实可用；P2 一次清扫。
**协议继承：** 执行协议、防偏差硬规则、审查参数、进度 ledger 全部沿用 [`2026-07-08-mini-jenkins-migration-handoff.md`](./2026-07-08-mini-jenkins-migration-handoff.md) §3-§6，本文档只写差异。原 D1-D5 决策与"明确不修"清单（backlog 末节）继续有效。

## Global Constraints

- 分支：`fix/post-migration-backlog`，基于 main。Conventional Commits。
- 后端全量校验（不变）：
  ```bash
  cd backend && uv run ruff check app tests && uv run black --check app tests \
    && uv run isort --check-only app tests && uv run mypy app && uv run pytest
  ```
  Postgres：容器 `signaldeck-local-postgres` 已在 127.0.0.1:25432（db/user/pass 均 `signaldeck`）；`export TEST_DATABASE_URL='postgresql+psycopg://signaldeck:signaldeck@127.0.0.1:25432/signaldeck'; export DATABASE_URL="$TEST_DATABASE_URL"`。
- 前端全量校验（不变）：`cd frontend && pnpm lint && pnpm typecheck && pnpm test:run && pnpm build`；e2e：`pnpm test:e2e`。
- 每个 Task 完成即 push；**B1 完成后必须等 GitHub Actions CI 转绿再继续**（这是本轮的核心验收物）。
- 模型档位：B1 最强档；B2/B4/B6/B8 中档；B3/B5 便宜档。

---

### Task B1: 修复 main 上 CI 红（最优先）

**现象：** CI run（commit `ba2b85cc`，run id 28999488918）frontend-e2e 失败 `reports.spec.ts:61 "generate report from template, view, edit, download, delete"`，报 report-detail 元素 hidden；`retries: 2` 下跨重试稳定失败 ⇒ 确定性问题，非抖动。**本地通过**——差异在 CI 环境（`workers: 1`、慢 CPU、无头）。

**Files:**
- Modify: `frontend/e2e/reports.spec.ts`（最可能）或 `frontend/src/pages/reports/` 下渲染时序问题（次可能）
- 参考: `frontend/playwright.config.ts`（CI 分支配置）

**诊断步骤（按序）：**
- [ ] **Step 1:** `gh run view 28999488918 --log-failed | grep -B5 -A30 "reports.spec"` 取完整失败断言与 DOM 快照；`gh run download 28999488918` 若有 playwright-report/trace 工件则下载并 `pnpm exec playwright show-trace` 看失败瞬间。
- [ ] **Step 2:** 本地复现 CI 条件：`cd frontend && CI=1 pnpm exec playwright test e2e/reports.spec.ts --workers=1 --repeat-each=5`。若仍不复现，加 `--headed --slow-mo=200` 观察 generate→detail 跳转的中间态。
- [ ] **Step 3:** 定位根因。两类候选：(a) 测试缺等待——generate 后未 `await expect(...).toBeVisible()` 就断言 detail 内容，CI 慢机上渲染未完成；(b) 页面真 bug——detail 依赖的 query 未 invalidate，本地因速度掩盖。**修根因**：(a) 补语义等待（等 URL 变化 + 等具体元素，不用 `waitForTimeout`）；(b) 修页面并保留测试原断言。
- [ ] **Step 4:** `CI=1 pnpm exec playwright test e2e/reports.spec.ts --workers=1 --repeat-each=10` 全过 → 全量 e2e → Commit `fix(e2e): stabilize report generate flow under CI timing`（若是页面 bug 则 `fix(reports): ...`）。
- [ ] **Step 5:** push 后确认 GitHub Actions CI 全绿。**不绿不进 B2。**

**BLOCKED 条件：** trace 显示后端 500（非前端时序）→ 上报，附完整响应体。

### Task B2: 生产镜像 scheduler 拓扑 + 部署示例 compose

**问题：** backend 生产镜像唯一入口 uvicorn；launch 只入队，执行靠 scheduler worker；`RUN_SCHEDULER`/`SCHEDULER_CMD` 只有 local-demo `docker/entrypoint.sh:6,41` 消费。GHCR 镜像部署 = run 永远 queued。

**方案（已定，勿改道）：** 不改镜像入口——同一 backend 镜像以不同 command 起第二个容器。交付一份可用的示例 compose + README 章节。

**Files:**
- Create: `docker/compose.production.example.yml`：
```yaml
# Production example: GHCR images, split topology.
# Prereq: external PostgreSQL (managed or self-run); set env in .env file.
services:
  backend:
    image: ghcr.io/OWNER/signaldeck-backend:latest
    environment:
      DATABASE_URL: ${DATABASE_URL}
      AGENT_PLATFORM_ENCRYPTION_KEY: ${AGENT_PLATFORM_ENCRYPTION_KEY}
      SIGNALDECK_API_TOKEN: ${SIGNALDECK_API_TOKEN}
      CORS_ALLOWED_ORIGINS: ${CORS_ALLOWED_ORIGINS:-}
    ports:
      - "127.0.0.1:8000:8000"

  scheduler:
    image: ghcr.io/OWNER/signaldeck-backend:latest
    command: ["python", "-m", "app.workers.run_scheduler"]
    environment:
      DATABASE_URL: ${DATABASE_URL}
      AGENT_PLATFORM_ENCRYPTION_KEY: ${AGENT_PLATFORM_ENCRYPTION_KEY}
    # No HTTP healthcheck: worker exposes none. pg advisory lock makes replicas safe.
    restart: unless-stopped

  frontend:
    image: ghcr.io/OWNER/signaldeck-frontend:latest
    environment:
      PORT: 8080
      BACKEND_UPSTREAM: backend:8000   # consumed by nginx template (Task B4)
    ports:
      - "8080:8080"
    depends_on:
      - backend
```
- Modify: `README.md` "Production Release Images" 节新增 "Split deployment topology" 小节：三容器职责、scheduler 必须存在否则 run 永远排队、多 scheduler 副本安全（advisory lock）、指向示例 compose。

- [ ] **Step 1:** 写 compose + README（compose 中 BACKEND_UPSTREAM 依赖 B4——**先做 B4 再做本任务**，或同分支顺序执行）。
- [ ] **Step 2:** `docker compose -f docker/compose.production.example.yml config` 通过（用假 env 值）。
- [ ] **Step 3:** 本地烟测：用本地构建镜像替换 image 字段跑一次，POST 一个 launch，确认 scheduler 容器日志领取并执行（fake key 下 run 失败也算执行——状态离开 queued 即可）。
- [ ] **Step 4:** Commit `docs(deploy): production split topology with scheduler service`

### Task B3: 镜像多架构构建

**Files:** Modify `.github/workflows/docker-images.yml`

- [ ] **Step 1:** line 35 `BUILD_PLATFORM: linux/arm64` 改 `BUILD_PLATFORM: linux/amd64,linux/arm64`。
- [ ] **Step 2:** 确认 workflow 已有 `docker/setup-qemu-action`（grep；缺则在 buildx setup 前加一步）。
- [ ] **Step 3:** push 后看 PR 的 Docker Images job 构建通过（PR 不推送但会构建）。Commit `ci(docker): build multi-arch amd64+arm64 images`

### Task B4: 前端镜像 API 布线（离开 localhost 可用）

**问题：** CI 构建时 `VITE_API_BASE_URL` 为空 → [api-client.ts:31,73](frontend/src/lib/api-client.ts) 回退硬编码 `http://127.0.0.1:8000/api/v1`；[frontend/nginx.conf](frontend/nginx.conf) 无 `/api` 反代。发布的前端镜像任何非 localhost 访问全 404。

**方案：** 生产构建默认同源相对路径 `/api`，nginx 模板加 `/api/` 反代（镜像已用 envsubst 模板机制：`Dockerfile:28` COPY 到 `/etc/nginx/templates/default.conf.template`）。

**Files:**
- Modify: `frontend/nginx.conf` —— `location /` 之前加：
```nginx
  location /api/ {
    proxy_pass http://${BACKEND_UPSTREAM}/api/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_read_timeout 120s;
  }
```
- Modify: `frontend/Dockerfile` —— `ENV PORT=3000` 后加 `ENV BACKEND_UPSTREAM=127.0.0.1:8000`（默认值保证单机跑不炸）。
- Modify: `frontend/src/lib/api-client.ts` —— 空 `VITE_API_BASE_URL` 时的回退改为：dev 模式维持 `http://127.0.0.1:8000/api/v1`（vite dev server 无反代），生产构建用同源相对 `/api`：
```ts
const DEFAULT_API_BASE_URL = import.meta.env.DEV
  ? "http://127.0.0.1:8000/api"
  : "/api";
```
以现有 `normalizeApiBaseUrl`/`toVersionedApiBaseUrl`/`toPlatformApiBaseUrl`（[api-client.ts:32-36](frontend/src/lib/api-client.ts)）为准接入——相对路径必须能通过这三个函数（若 normalize 假定绝对 URL,同步修并补单测）。
- Test: `frontend/src/lib/api.test.ts`（或就近既有测试文件）补两条：空 env + DEV=false ⇒ 相对 `/api/v1`；显式 `VITE_API_BASE_URL` ⇒ 原行为不变。

- [ ] **Step 1:** 失败测试 → **Step 2:** 实现 → **Step 3:** 前端全量校验 + `pnpm test:e2e`（e2e 显式设了 API base，应不受影响——红了就是改坏了 normalize）。
- [ ] **Step 4:** 镜像级验证：`docker build -t sd-frontend frontend/` 后与本地 backend 联跑，`curl -s http://127.0.0.1:8080/api/v1/reports` 经 nginx 反代返回 JSON（或 401,若设了 token——都证明布线通）。
- [ ] **Step 5:** Commit `fix(frontend): same-origin /api default + nginx proxy for published image`

### Task B5: 部署文档补漏（含 CORS，一个 commit）

**Files:** Modify `README.md`、`docs/product.md`

- [ ] **Step 1:** README Backup 节加粗提示：**`AGENT_PLATFORM_ENCRYPTION_KEY` 必须与 pg_dump 同时备份**——丢 key 后所有 model-connection 密钥不可解密（API 读取报 500），无轮换/重加密工具（单 key Fernet，known limitation，写明重新录入密钥是唯一恢复路径）；建议高熵随机 key（`openssl rand -base64 32`）。
- [ ] **Step 2:** README 部署节写明：非 localhost 前端源必须设 `CORS_ALLOWED_ORIGINS`（同源反代部署——B4 拓扑——则无需）。环境变量表补 `MCP_RUNTIME_ENABLED`（default false）、`MCP_RUNTIME_TIMEOUT`、`SIGNALDECK_RUN_RETENTION_DAYS`（若已有则核对）。
- [ ] **Step 3:** README 与 docs/product.md 的 Runs 描述补 cancel：`POST /api/runs/{id}/cancel`，queued 立即取消、running 在步边界协作停止。
- [ ] **Step 4:** Commit `docs: key backup warning, CORS guidance, cancel and MCP env documentation`

### Task B6: MCP default-off 负路径测试

**Files:** Modify `backend/tests/test_mcp_runtime.py`

- [ ] **Step 1:** 读 [backend/app/agents/mcp/runtime.py:159-162](backend/app/agents/mcp/runtime.py#L159-L162) 确认 disabled 语义（`if not enabled or not mcp_server_refs` 返回空 dispatcher），照本文件现有测试的构造方式写：
```python
def test_dispatcher_disabled_ignores_declared_mcp_servers():
    # Same manifest/server-ref fixtures as the enabled=True tests in this file,
    # but enabled=False: dispatcher must expose zero MCP tools and spawn nothing.
    dispatcher = build_dispatcher(..., enabled=False)  # 按本文件既有调用形状
    assert dispatcher.tool_names() == []  # 以实际公开接口为准，断言零工具、零子进程
```
（具体断言接口以 runtime.py 实际返回类型为准；核心：**声明了 MCP server + enabled=False ⇒ 无任何 MCP 工具可被调度、无子进程启动**。）
- [ ] **Step 2:** 先证明测试有效：临时把 runtime.py:162 的 `not enabled or` 删掉跑一次，测试必须红；还原后绿。此验证写进报告。
- [ ] **Step 3:** 后端全量校验 → Commit `test(mcp): assert disabled runtime dispatches no MCP tools`

### Task B7: P2 清扫（一个 Task，按条 commit 或合并均可）

逐条，每条附验证：

- [ ] **retention 改 finished_at：** [repositories/run.py:163-168](backend/app/repositories/run.py#L163-L168) 过滤从 `created_at < cutoff` 改为终态时间列（读 Run 模型确认列名，`finished_at`/`completed_at`；若无此列——加列）。改 `test_runtime_repositories.py` 对应测试：长期 queued 后刚结束的 run 不被剪。
- [ ] **auth 非 ASCII 头 500→401：** [core/auth.py:28](backend/app/core/auth.py#L28) `compare_digest` 包 try/except TypeError 返回 401。测试：`client.get("/api/runs", headers={"Authorization": "Bearer tokén"})` 得 401 非 500。
- [ ] **MCP stdio 允许列表收紧：** [agents/mcp/security.py:92](backend/app/agents/mcp/security.py#L92) basename 匹配改为：命令含 `/` 时,其 `os.path.realpath` 必须等于 `shutil.which(basename)` 的 realpath,否则拒绝；裸命令名维持原判定。补两条测试：`/tmp/evil/python` 拒绝、裸 `python` 通过。
- [ ] **cancel e2e：** `frontend/e2e/runs.spec.ts` 加一条：API 直接创建 launch（e2e 后端无 scheduler,run 停在 queued——正好），进 run detail 点 `data-testid=runs-detail-cancel`（[pages/runs/detail.tsx:302](frontend/src/pages/runs/detail.tsx#L302)），断言状态徽章变 cancelled。
- [ ] **startup_recovery join 收紧：** `app/db/startup_recovery.py` 子行修复 UPDATE 当前 join 所有 `status='failed'` 的 run——改为只作用于本次恢复标记的 run id 集合（CTE 或先 SELECT id 再 UPDATE ... WHERE run_id IN）。既有测试不变绿 + 加一条：历史 failed run 的残留 running 子行不被本函数触碰。
- [ ] **ponytail 天花板注释三处：** SSRF DNS-rebinding TOCTOU（`app/core/config.py` 或校验函数处）、cancel 仅步边界检查（`agent_execution_service.py` 检查点处）、cancel finalize 竞态（`run_service.py` finalize 处）。格式 `# ponytail: <ceiling>, <upgrade path>`。
- [ ] 后端 + 前端全量校验 + e2e → Commit（示例）`fix: retention by finish time, clean 401 on bad auth header, strict mcp allowlist` / `test(e2e): cancel queued run` / `chore: ponytail ceiling comments`

### Task B8: 终检

- [ ] 前后端全量校验 + e2e 全绿；push 后 **GitHub Actions CI 全绿**（含 Docker Images job 多架构构建）。
- [ ] 发布镜像端到端演练：按 `docker/compose.production.example.yml`（本地镜像替代 GHCR tag,linux/amd64）full stack 起来——浏览器访问 8080、登录 token、创建 launch、scheduler 容器执行、run detail 看到终态、cancel 一个 queued run。此演练即"发布镜像方式正经部署"的验收。
- [ ] Commit `chore: post-migration backlog complete`，message 附验收演练结果一行。

## 求助规则（差异项）

- B1 若根因是后端 bug（非测试时序）：修后端算 in-scope,但先报 owner 一行说明再动手。
- B4 若 `normalizeApiBaseUrl` 系列与相对路径根本不兼容、改动波及超过 api-client + 测试两个文件：BLOCKED 上报,附影响面清单。
- backlog "明确不修"清单里的项（root 用户镜像、SIGTERM 精细化、Fernet KDF 换 PBKDF2 等）：不做,reviewer 提出也不做。
