# SignalDeck

[English](README.md) | 简体中文

SignalDeck 是一个自托管的 LLM agent 流水线运行器——可以理解为迷你 Jenkins,只不过任务不是构建脚本,而是多 agent 工作流。它面向所有想用 YAML 定义 agent 流水线、手动或定时运行、并在事后清楚看到发生了什么的人。

## 工作方式

- 编写一个 **Workflow Package**(工作流包):用一个 YAML 文件描述整条流水线——输入、参与的 agent、它们可以调用的工具,以及步骤之间如何连接(sequence、fan-out、loop、普通 HTTP 调用)。
- 添加一个 **Model Connection**(模型连接):保存的 LLM 提供商绑定(endpoint、模型、API key,静态加密存储),包通过名称引用它。
- 在 Web UI 中手动发起运行,或挂上一个 **Scheduled Task**(定时任务):按 interval、每日、每周或每月的周期规则(支持时区)自动触发运行。
- 每次运行都保留证据:步骤状态、每次 agent 调用的实际输入与输出、HTTP 调用、token 用量、重试、失败信息以及最终结果。运行基于包的不可变快照执行,所以你看到的就是实际运行过的内容。
- 输出可以生成 **Report**(报告):由模板生成的 markdown 快照,可在 UI 中编辑和下载。

技术栈为 FastAPI + PostgreSQL 后端和 React/Vite 前端。

## 快速开始

你需要带 Compose v2 的 Docker,以及一个 LLM 提供商的 API key。

```bash
git clone https://github.com/coachpo/signaldeck.git
cd signaldeck
./start.sh
```

这会构建本地组合镜像,启动 PostgreSQL 和应用,并在 `http://localhost:8080` 提供全部服务(可用 `APP_PORT` 覆盖端口)。按 `Ctrl+C` 停止;用 `docker compose down` 清理(加 `-v` 同时删除数据库)。

首次运行:

1. 打开 `http://localhost:8080`,进入 **Model Connections**,添加你的 LLM 提供商和 API key。
2. 启动时会预置两个演示包。打开 **Workflow Packages**,选一个——*Digital Oracle Researcher* 是两者中较简单的——发起一次运行。
3. 在 **Runs** 中观察运行,并深入查看逐步执行证据。

两个演示包的 YAML 源文件在 [`demo/`](demo/) 目录中,同时也是编写你自己的包的参考示例。如果你更喜欢直接用 Compose 而不是启动脚本,`docker compose up --build --remove-orphans` 效果相同。

## 生产部署

根镜像仅用于本地/演示,并拒绝以生产模式启动。CI 发布的是拆分镜像:

- `ghcr.io/<owner>/signaldeck-backend` — API;同一镜像以 `python -m app.workers.run_scheduler` 启动即为 scheduler worker
- `ghcr.io/<owner>/signaldeck-frontend` — 浏览器应用,内置 nginx 将 `/api` 代理到后端

生产环境运行三个容器:backend、scheduler、frontend。scheduler 不是可选项——发起运行只是入队,没有 scheduler worker 时运行会永远停在 `queued` 状态。多个 scheduler 副本是安全的;协调通过 PostgreSQL advisory lock 实现。

从 [`docker/compose.production.example.yml`](docker/compose.production.example.yml) 开始。把 `SIGNALDECK_IMAGE_TAG` 固定到不可变的 tag 或 digest,并设置:

- `DATABASE_URL` — 托管的 PostgreSQL 16+。
- `AGENT_PLATFORM_ENCRYPTION_KEY` — 加密存储的 API key 和包 secret。**每次数据库备份时都要一并备份这个密钥。** 它是单一 Fernet 密钥,目前没有轮换工具;一旦丢失,所有已存 secret 都得重新录入。用 `openssl rand -base64 32` 可以生成一个高强度密钥。
- `SIGNALDECK_API_TOKEN` — 整个 API 的 bearer token 保护。SignalDeck 是没有登录系统的单用户软件,所以要么设置它,要么把应用放在带认证的反向代理后面(oauth2-proxy、Tailscale 等)。
- `MCP_RUNTIME_ENABLED` — 如果你的包使用 MCP 工具,请在 *scheduler* 容器上设置它。它默认关闭,只在 API 容器上设置没有任何效果,因为执行运行的是 scheduler。

在正式托管数据之前,还有两件事值得知道:

- 没有迁移框架。schema 通过 SQLAlchemy `create_all` 创建,涉及 schema 变更的升级意味着重建数据库。
- 除非设置 `SIGNALDECK_RUN_RETENTION_DAYS`,运行历史会无限增长。

用普通的 PostgreSQL 工具(`pg_dump` / `psql`)备份,并附上上面提到的加密密钥。

## 开发

后端:FastAPI、SQLAlchemy、Pydantic,基于 PostgreSQL,用 uv 管理(Python 3.13+)。前端:React 19、Vite、TanStack Query,用 Vitest 和 Playwright 测试(Node 24+、pnpm 10+)。

```bash
# Backend
(cd backend && uv sync)
(cd backend && uv run ruff check app tests && uv run mypy app && uv run pytest)

# Frontend
(cd frontend && pnpm install)
(cd frontend && pnpm lint && pnpm typecheck && pnpm test:run)
```

CI 会运行完整的质量门禁(格式化、类型、单元测试、Playwright E2E、Docker 镜像构建);`docs/development.md` 有精确的命令和工具链版本锁定。

## 仓库结构

- `backend/` — API、scheduler worker 和测试
- `frontend/` — Web UI
- `demo/` — Workflow Package YAML 示例
- `docs/` — 产品形态、数据模型、开发和扩展指南
- `docker/` — 生产 compose 示例和根镜像支持文件

## 设计说明

几个刻意的取舍,浓缩自 `docs/`:

- 可信单用户应用。没有账户体系、RBAC 或多租户;访问控制就是 bearer token 或你的反向代理。
- Workflow Package 是自包含的。agent、输出 schema、capability profile(包内的清单,列出该包可以使用哪些服务端声明的工具)以及私有 MCP 配置都放在包内部,而不是共享的全局表中。
- 工具集成是编译进后端的静态 Python 扩展:`signaldeck.finance`(行情、新闻、情绪和报告工具)和 `signaldeck.digital_oracle`(预测市场、SEC 文件、宏观和衍生品工具)。没有插件市场;添加工具意味着写代码——见 `docs/writing-extensions.md`。
- secret 永不离开服务器。API key 和包 secret 静态加密存储,包导出和运行溯源会剥离含 secret 的值、数据库 id 和运行历史。
