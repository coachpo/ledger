# 贡献指南

本文件是本地开发、验证和完成定义的入口。项目事实分别由 [`STATUS.md`](STATUS.md)、[`docs/产品说明.md`](docs/产品说明.md) 和 [`docs/架构说明.md`](docs/架构说明.md) 维护；项目特有技术规则由 [`docs/开发规范.md`](docs/开发规范.md) 维护。

## 开发环境与依赖

- Backend：Python 3.13，使用 uv；依赖和锁文件位于 `backend/`。
- Frontend：Node 24、pnpm 10.30.1；依赖和锁文件位于 `frontend/`。
- 本地运行需要 Docker Compose v2 和 PostgreSQL/pgvector；完整本地栈优先使用根目录 `start.sh`。

安装依赖：

```bash
(cd backend && uv sync)
(cd frontend && pnpm install)
```

## 开发启动

本地/演示组合栈：

```bash
./start.sh
docker compose -f docker-compose.yml down
docker compose -f docker-compose.yml down -v
```

`start.sh` 默认暴露 `http://localhost:${APP_PORT:-8080}`。根镜像同时运行 Nginx、FastAPI 和 scheduler，只用于本地/演示；生产拆分拓扑和环境变量以 [`docs/架构说明.md`](docs/架构说明.md) 与 [`docker/compose.production.example.yml`](docker/compose.production.example.yml) 为准。

如果单独运行 backend 测试，必须提供可连接且具备测试数据库权限的 PostgreSQL；可使用 `TEST_DATABASE_URL` 或 `DATABASE_URL`。

## 检查、测试与构建

Backend：

```bash
(cd backend && uv run ruff check app tests)
(cd backend && uv run black --check app tests)
(cd backend && uv run isort --check-only app tests)
(cd backend && uv run mypy app)
(cd backend && uv run pytest)
```

Frontend：

```bash
(cd frontend && pnpm lint)
(cd frontend && pnpm typecheck)
(cd frontend && pnpm build)
(cd frontend && pnpm test:run)
(cd frontend && pnpm exec playwright install --with-deps chromium)
(cd frontend && pnpm test:e2e)
```

若变更了根 Dockerfile，补充运行：

```bash
docker build .
```

所有变更最后运行：

```bash
git diff --check
```

## 开发工作流

1. 先读取与任务相关的 `STATUS.md`、产品说明、架构说明、开发规范和适用的子目录 `AGENTS.md`。
2. 搜索已有实现、接口和测试，确认变更所属模块及允许的依赖方向；不要为假设中的未来需求添加抽象、依赖或兼容层。
3. 先运行与改动直接相关的最小检查；完成后按影响范围运行 backend/frontend 质量门禁，并保持 demo、API contract、snapshot/provenance 和文档同步。
4. 检查 secret、错误详情、包导出、运行读取和日志路径，确认没有原始凭据或内部信息泄露。
5. 检查精确 diff、未纳入无关文件，并按下方共享完成定义交付。

## 项目文档

规范文档的索引和权威边界见 [`docs/README.md`](docs/README.md)。数据表见 [`docs/data-model.md`](docs/data-model.md)，扩展编写见 [`docs/writing-extensions.md`](docs/writing-extensions.md)，依赖遗留事项见 [`docs/handover-deps-follow-up.md`](docs/handover-deps-follow-up.md)。

<!-- write-project-docs:derived-iteration-strategy:start -->
<!-- write-project-docs:derived-iteration-strategy:metadata {"contentSha256":"sha256:f440df2388c4f4748b1d642e0d4b8f3996360782cd68a638261739f2f29ea3ef","schemaVersion":1,"sources":[{"normalization":"without-visible-exact-mvp-control-line-terminal-lf-v2","path":"STATUS.md","sha256":"sha256:fe32da860633c44684c1501e35bb14e99200464bb066b58e3fc438d3fbcffaf3"},{"path":"docs/产品说明.md","sha256":"sha256:f205632f1c0c001ca5feee5c24efeee39fe96f8a0c1fdf0165c9f7ec66f54904"},{"path":"docs/架构说明.md","sha256":"sha256:45585ae7ed9559a1d74b4b4a8942b9e029d26a635a416ef72245e698825da216"},{"path":"docs/开发规范.md","sha256":"sha256:4f69b91702a3a81b475c1908f9bd7f0bc80523676d94e942eb7fb0a6f5f1d649"}]} -->
## 当前迭代策略

以本地内网个人使用的可重复开发调试闭环为最高执行优先级，在不降低现有正确性、数据完整性、密钥处理和必需检查的前提下优先改善开发与使用便利度。

派生依据（事实权威仍在原文档）：[`STATUS.md`](STATUS.md)、[`docs/产品说明.md`](docs/产品说明.md)、[`docs/架构说明.md`](docs/架构说明.md)、[`docs/开发规范.md`](docs/开发规范.md)。

> 本区块只约束当前迭代，不改变 MVP 快速验证开关，也不得降低安全、隐私、权限、数据完整性、已有兼容承诺或更高优先级要求。

### 本轮必须完成

- 保持 start.sh 和 Docker Compose 本地闭环可重复启动，并验证健康、就绪和核心运行路径。
- 围绕 Workflow Package、Scheduled Task、Model Connection、Run evidence、Templates/Reports 的已确认范围实现和修复，使用现有 API、服务和静态扩展边界。
- 对受影响变更运行适用的后端检查、前端检查、构建和测试，并用 git diff --check 收尾。

### 本轮不主动投入

- 公网或生产级安全加固、认证/RBAC、多租户和高可用：当前部署是个人本地内网且没有相应验收触发；当出现公网暴露、外部用户、生产部署或明确安全验收时重新评估。
- 容量、并发、性能和灾备专项：当前目的为本地开发调试且没有对应性能验收；当出现吞吐/延迟/并发目标或真实负载时重新评估。

### 不可降低的边界

- 保留密钥与 secret 的加密存储、读取/导出/日志/诊断脱敏，以及 API 错误详情的安全过滤。
- 保留 Workflow Package YAML 解析安全、语义校验、确定性编译、闭合 schema 和 HTTP/MCP 边界。
- 保留数据库完整性、不可变运行快照、队列/调度状态和适用质量检查；不以便利度跳过相关测试或改变生产镜像边界。

### 重新推导条件

- 生命周期从本地开发调试转为生产运行，或部署从本地内网扩展到公网。
- 出现外部用户、真实或不可丢弃数据、明确兼容承诺、性能/容量验收或新的安全/隐私/权限要求。
- STATUS.md、产品范围、架构边界、开发规范或仓库必需检查发生变化。
<!-- write-project-docs:derived-iteration-strategy:end -->

<!-- write-project-docs:shared-contributing:start -->
## 通用设计原则

在满足已确认的功能范围、架构边界、质量属性、安全性、兼容性和运行约束的前提下，按以下顺序选择设计方案：

1. 项目中已有、经验证且仍适用的设计、模式、接口或组件；
2. 适用的正式标准、标准协议，以及平台或框架的官方推荐方案；
3. 在相似场景中被广泛采用、持续维护且有可靠实践证据的成熟行业方案；
4. 只有上述方案不能满足已核实约束时，才采用满足当前需求的最小定制设计。

“广泛使用”只是候选信号，不是充分的采用理由。采用前按风险核对需求适配、安全与兼容、主要失败模式、维护与迁移成本；不得为套用惯例引入当前范围不需要的能力、抽象或依赖。

涉及架构边界、依赖方向、数据责任、安全边界或长期依赖的重要设计选择，应在设计结果中记录适用依据、主要权衡和验证方式。采用定制设计时，同时说明成熟方案不适用的已核实约束。高风险且证据不足时，先定义可观察的成功、失败和退出条件，再执行当前权限允许的最小可逆验证；不得把未接受或未实现的候选写成当前架构事实。

## 通用实现原则

在满足功能范围、架构边界、正确性、安全性和可验证性的前提下，按以下顺序选择实现方式：

1. 项目中已有的实现；
2. 语言标准库；
3. 平台原生能力；
4. 项目已安装且适合当前场景的依赖；
5. 适合当前环境、成熟、活跃并被广泛使用的第三方库；
6. 满足当前需求的最小自定义实现。

新增代码前先搜索已有实现。不要为小功能引入大型依赖；不要为假设中的未来需求创建抽象层、扩展层或兼容层；保持自定义实现局部、简单且可测试。

实现必须遵守 [`docs/架构说明.md`](docs/架构说明.md) 的项目架构事实、[`docs/开发规范.md`](docs/开发规范.md) 的项目/技术专属规则，以及 [`docs/源代码规模与职责规则.md`](docs/源代码规模与职责规则.md) 的统一规模与职责规则。

## 完成定义

一项变更只有在以下条件全部满足时才算完成：

- 实现符合已确认的功能范围和验收条件；
- 重要设计选择已验证成熟方案的适用性；采用定制方案时，已记录不适用约束、主要权衡和验证方式；
- 保持既有架构边界和依赖方向，没有加入无关职责或顺手改动；
- 已满足适用的项目/技术专属开发规范；
- 相关测试、静态检查、格式检查和构建验证已经通过；
- 已按开发规范完成唯一权威文档、机器合同和验证的同步；
- 没有提交密钥、凭据、个人数据、生成产物或无关文件；
- 已按源代码规模与职责规则完成检查，并报告需要说明的长文件。
<!-- write-project-docs:shared-contributing:end -->
