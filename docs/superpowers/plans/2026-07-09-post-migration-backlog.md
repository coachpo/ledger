# 迁移终审遗留待办（2026-07-09 验收产出）

迁移 24/24 Task 完成、已合 main、本地三套件全绿（backend 731 / frontend 289 / e2e 22）。以下是终审（6 路核验 + 对抗验证）确认的遗留问题，按优先级。执行方式沿用 handoff 文档协议。

## P0 — 部署阻断（不修完不能算"可生产部署"）

### B1: main 上 CI 红
CI run（commit `ba2b85cc`）frontend-e2e 失败：`reports.spec.ts:61 "generate report from template, view, edit, download, delete"`，CI 内跨重试稳定失败；**本地同 spec 通过**。先在 CI 环境复现定位（大概率时序/资源差异——report-detail 渲染等待不足），修测试或修页面。CI 不绿一切免谈。

### B2: 生产镜像跑不了 run —— scheduler 没有容器拓扑
`backend/Dockerfile` 唯一入口是 uvicorn；launch 只入队（queued），执行全靠 scheduler worker；`RUN_SCHEDULER` 只有 local-demo entrypoint 消费。**用 GHCR 镜像部署 = run 永远 queued。** 修法（选一，推荐 a）：
- (a) README + 示例 compose：backend 镜像起第二个容器，command `python -m app.workers.run_scheduler`（advisory lock 已保证多副本安全）；
- (b) backend 镜像加 env 开关在 lifespan 内起 scheduler 线程。

### B3: 镜像 arm64-only
`.github/workflows/docker-images.yml:35` `BUILD_PLATFORM: linux/arm64`，多数自托管主机（含本机，x86_64）跑不了。改 `linux/amd64,linux/arm64` 多架构构建。

### B4: 前端生产镜像离开 localhost 即坏
CI 构建时 `VITE_API_BASE_URL` 为空，api-client 回退硬编码 `http://127.0.0.1:8000/api/v1`；`frontend/nginx.conf` 无 `/api` 反代。修法：nginx.conf 加 `/api` proxy_pass 到 backend 服务名 + api-client 空值时用同源 `/api`（二选一或都做），并在 README 写清拓扑。

## P1 — 生产运维必要

- **B5:** README 备份 runbook 补一句：`AGENT_PLATFORM_ENCRYPTION_KEY` 必须与 pg_dump 一起备份——丢 key = 所有 model-connection 密钥不可恢复（读取时 500）。同时把"无 key 轮换机制"写为已知限制（单 key Fernet，无 MultiFernet/重加密工具）。
- **B6:** MCP 默认关闭是安全默认，但 `enabled=False` 负路径零测试覆盖（所有测试都 enabled=True）。加一条：`MCP_RUNTIME_ENABLED` 未设时 manifest 声明的 MCP server 不被调度。[backend/app/agents/mcp/runtime.py:162]
- **B7:** 非 localhost 前端源需要 `CORS_ALLOWED_ORIGINS`，README 部署段落明确写出（现只有一处提及）。

## P2 — 小项（一个 commit 可扫完的与可延后的）

- 取消功能文档缺失：product.md/README 只写 rerun 不写 cancel；README 环境变量表漏 `MCP_RUNTIME_ENABLED`/`MCP_RUNTIME_TIMEOUT`。
- cancel 无前端测试（e2e runs.spec 只测 rerun；按钮 `runs-detail-cancel` 无人点）。
- retention 用 `created_at` 而非 `finished_at` 判定——长时间 queued 的 run 刚结束就可能被剪。改 finished_at。
- auth：非 ASCII Authorization 头触发 `secrets.compare_digest` TypeError → 500（仍拒绝，但应干净 401）。捕获 TypeError 返回 401。
- MCP stdio allowlist 按 basename 匹配，`/tmp/x/python` 可过——改全路径解析或 shutil.which 校验。
- SSRF 校验解析 DNS 后 httpx 再次解析，存在 DNS-rebinding TOCTOU 窗口——单用户自托管风险低，加 `# ponytail:` 注释标注即可。
- Fernet key 为无盐单轮 SHA-256 派生——文档建议高熵 key（production 已拒占位值）；或换 PBKDF2。
- startup_recovery 子行修复 UPDATE join 到所有 status='failed' 的 run（不限本次恢复标记的）——历史 failed run 的残留 running 子行会被顺带改写,行为可接受但值得收紧。
- cancel 两个窄窗口边缘：finalize 竞态下终态为 succeeded 而非 cancelled；宽扇出 step 内部不检查 cancel。均可接受，加 ponytail 注释声明天花板。

## 明确不修（终审对抗验证裁定可接受）

镜像 root 用户运行（单用户自托管，nginx 非特权口）、双进程 supervisord 无 SIGTERM 精细处理（lease+启动恢复兜底）、schedule/DI/compiler 等原"明确不做"清单继续有效。
