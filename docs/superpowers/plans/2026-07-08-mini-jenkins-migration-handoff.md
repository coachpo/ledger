# 迁移执行交接文档 — Mini-Jenkins Migration

**读者：** 负责执行本次迁移的开发者（假定使用 Claude Code + superpowers 插件）。
**执行对象：** [`2026-07-08-mini-jenkins-migration.md`](./2026-07-08-mini-jenkins-migration.md)（下称"计划"）。计划共 10 个 Phase、24 个 Task，每个 Task 自带文件清单、代码、验证命令、commit message。
**执行方式：** superpowers:subagent-driven-development（每个 Task 派全新 implementer subagent，任务级双重审查，最后全分支终审）。

---

## 0. 一句话背景

这个仓库（SignalDeck）的真实目标是"迷你 Jenkins for LLM agents"——YAML 定义多 Agent 工作流、手动/定时触发、队列执行、看结果。现状被建成了多租户 PaaS。四份审计（后端架构、后端测试、前端、生产差距）结论：约 -5 万行可删，+500 行生产短板要补。计划就是按此产出的。

## 1. 已拍板的决策 — 不要重新讨论，不要"好心"改进

以下全部是 owner 明确确认过的，执行中任何人（包括 subagent、reviewer）提出异议时，答案都在这里：

| 决策 | 内容 | 出处 |
|---|---|---|
| D1 | **无兼容性要求、无数据保留要求。** 破坏性变更随意，DB 随时 drop 重建。不写迁移脚本、不写 deprecation 警告、不留旧 API 别名。 | owner 原话 |
| D2 | **Phase 4 删 portfolio 记账域：已确认执行。** reports/templates 保留，market-data 服务层保留（agent 工具依赖）。 | owner 默认批准 |
| D3 | **插件契约保留，插件市场机制删除。** owner 明确要求未来能容易加新插件提供 tools（含同能力多实现）。方案：静态 `Extension` dataclass + `INSTALLED_EXTENSIONS` 清单 + owner 限定 tool key + capability profile 选实现。删的是动态发现/registrar Protocol/依赖解析/启停管理面。**不要把 import_module 机制加回来，也不要把契约进一步删成散装直连。** | owner 2026-07-08 |
| D4 | **"明确不做"清单**（计划开头）：schedule 三文件合并、recurrence 重写、output_schema_compiler 重写、DI 扁平化、Alembic、Phase 10 管线合并。即使顺手、即使 reviewer 建议，也不做。 | 计划批准时确认 |
| D5 | 鉴权 = 可选 Bearer token（env 未设则关闭）。不做登录页、不做 RBAC、不做多用户。 | 审计结论 + owner 批准 |

## 2. 开工前置

```bash
cd /home/qing/Documents/projects/ledger
git checkout main && git pull
# 测试用 Postgres（后端 pytest 硬依赖）：
docker run -d --name signaldeck-test-pg -e POSTGRES_DB=signaldeck \
  -e POSTGRES_USER=signaldeck -e POSTGRES_PASSWORD=signaldeck \
  -p 25432:5432 postgres:16-alpine
export TEST_DATABASE_URL='postgresql+psycopg://signaldeck:signaldeck@127.0.0.1:25432/signaldeck'
export DATABASE_URL="$TEST_DATABASE_URL"
cd backend && uv sync --frozen
cd ../frontend && pnpm install --frozen-lockfile && pnpm exec playwright install --with-deps chromium
```

- 工具版本：Python 3.13 / uv 0.9.8 / Node 24 / pnpm 10（与 `.github/workflows/ci.yml` 一致）。
- e2e 前先看 `frontend/playwright.config.ts` 的 `webServer` 段确认它如何起前后端（CI 里 e2e job 同时装了 uv 和 pnpm，说明它自起后端）。
- 分支：`migration/mini-jenkins`。**绝不在 main 上直接实现。**

## 3. 执行协议（subagent-driven-development 的本项目参数）

启动时向会话声明："I'm using Subagent-Driven Development to execute docs/superpowers/plans/2026-07-08-mini-jenkins-migration.md"，然后按技能流程走。以下是本项目的具体化参数：

### 3.1 任务顺序

**严格按计划顺序串行：Phase 0 → 9，Phase 内按 Task 编号。** Phase 之间有真实依赖（例：P2 删 memory 之后 P5 的 mypy 清扫目标才成立；P8 测试瘦身只能在功能删除全部完成后做）。**禁止并行派多个 implementer**（技能红线，本计划尤甚——全是大面积删除，必然冲突）。

注意：计划的 Task 编号是 `N.M` 格式（Task 2.1、Task 8.5）。若 `scripts/task-brief PLAN_FILE N` 按整数编号提取失败，手工把该 Task 的完整章节（从 `### Task N.M` 到下一个 `###`/`##`）复制到 brief 文件，**并且必须附上计划的 Global Constraints 全文**——每个 brief 都要带，这是 implementer 和 reviewer 的共同约束。

### 3.2 模型选型（按技能的 Model Selection 规则映射到本计划）

| 档位 | 适用 Task | 理由 |
|---|---|---|
| 最便宜档 | 0.1、7.4、7.6、8.4、8.6、9.3 | 纯转写/文档/单文件机械操作，计划里代码是完整的 |
| 中档（默认） | 2.2、3.1、3.2、3.3、4.1、4.2、5.2、5.3、6.1、6.2、7.1、7.2、7.5、8.2、8.3、8.7、9.1、9.2、9.4 | 多文件删除+接缝清扫，机械但需要跨文件核对 |
| 最强档 | 1.1、2.1、5.1、7.3、8.1、8.5、最终全分支 review | 1.1/2.1 动 `run_service.py`/启动链（高纠缠）；5.1 是契约设计；7.3 涉及执行循环并发语义；8.1 是 fixture 设计；8.5 需要覆盖率判断 |

派发时**显式指定模型**，不指定会继承会话默认（最贵）。

### 3.3 每 Task 的完成定义（implementer 必须在报告里给出证据）

1. 计划中该 Task 的每个 checkbox 步骤完成（含 commit）。
2. **后端全量校验**（Global Constraints 里那条 ruff+black+isort+mypy+pytest 命令）或**前端全量校验**（lint+typecheck+test:run+build）输出全绿——贴命令与结尾输出，不接受"应该能过"。
3. 删除类 Task 附加证据：`grep -rn "<被删符号>" app/ tests/`（或 frontend src/）输出为空。
4. Phase 收尾 Task（2.2、3.3、4.2、5.3、6.2、7.6、8.7、9.4）额外跑 `pnpm test:e2e` 全绿。

### 3.4 审查参数

- 每个 Task 走技能标准双验收（spec compliance + code quality），reviewer 的 constraints 块从计划 Global Constraints **原文复制**。
- reviewer 常见误报预案（不要预先塞给 reviewer，等它提出后按此裁决）：
  - "删除导致测试覆盖下降" → 若被删测试对应被删功能，或属于计划点名的框架测试/重复测试，plan-mandated，放行。
  - "建议为 X 加抽象/接口/配置" → 撞 D4/ponytail 原则，拒。
  - "建议保留旧 API 兼容" → 撞 D1，拒。
  - 与计划正文真实冲突的发现 → **停下问 owner**，不要自行裁决（技能规则）。
- 最终全分支 review 用最强档模型，输入含 `git merge-base main HEAD` 起的完整 review-package。

### 3.5 进度与恢复

- 技能的 progress ledger（`.superpowers/sdd/progress.md`）每 Task 记一行。上下文压缩后**信 ledger 和 git log，不信记忆**，禁止重派已完成 Task。
- 每完成一个 Phase：push 分支。全部完成后一个 PR（或按你团队习惯拆 PR，phase 边界即天然拆分点）。

## 4. 防偏差硬规则（写给每个 implementer 的 brief 都要带）

1. **删除 = git rm / 删代码块。** 不注释掉、不留空壳函数、不加 `# deprecated`、不搬进 `legacy/` 目录。
2. **mypy/tsc 报错清单 = 接缝清单。** 删文件后跑 `uv run mypy app` / `pnpm typecheck`，逐条处理到零；处理方式是**删掉引用调用链**，不是加 `# type: ignore` 或 try/except 吞掉。
3. **计划行号会漂移，grep 命令不会。** 计划给的行号（如 `run_service.py:1754-1766`）是写计划时的快照；以计划附带的 grep 命令定位为准。文件不存在/符号不同名 → 先 grep 确认是否已在前序 Task 处理，仍疑 → BLOCKED 上报，不要猜。
4. **不新增依赖**，唯一例外：Task 7.1 的 `cryptography`。不新增抽象层、不新建"共享工具"模块（Task 5.1 契约和 8.1 fixture builder 是计划点名的例外）。
5. **测试纪律：** 功能删除 Task 里测试随功能死；测试瘦身 Task（Phase 8）里**行为覆盖不许减**——8.3/8.5 的 brief 里有 collect-only 对比 / e2e 覆盖比对步骤，是硬性前置。TDD 适用于所有新增代码（P1 bootstrap、P5 契约、P7 全部）：先写失败测试。
6. **每个 Task 一个（组）commit**，message 用计划里给定的；不要把多个 Task squash 在一起（review 粒度依赖 commit 边界）。
7. **不碰 D4 清单里的东西。** 见到 `# ponytail:` 注释 = 有意为之的天花板标注，保留。

## 5. 每 Phase 验收清单 + 已知陷阱

| Phase | 验收（全绿之外） | 已知陷阱 |
|---|---|---|
| P0 | 基线记录存在 `/tmp/loc-baseline.txt` | 基线若红，先修后开工，别带病迁移 |
| P1 | 新库两次 `init_db` 幂等；预置包已种入 | `conftest.py` 可能 import upgrades——测试侧接缝也要清；种子 `.sql` 加载逻辑**原样平移**，不要"顺手重构" |
| P2 | `grep -rn "workflow_memory\|workflow_checkpoint" backend/app frontend/src` = 空；`/api/memory/*` 返回 404 | 最高纠缠点：`run_service.py`（~90 个方法的 god object）内 ~400 行 memory 代码。删调用链要删到根，`agent_execution_service` 的 `prepare_invocation` 调用点别漏。fixture YAML（`advisory_research_memory.yaml` 等）整文件删 |
| P3 | fork 端点消失、rerun 正常（`test_run_service_http_operations` 等仍绿）；export 返回原文 manifest | `run_rerun_fork.py` 改名 `run_rerun.py` 后全仓 import 更新；**别删** `run_input_validation.py`（launch 参数校验，名字像但不是 preset 注册表） |
| P4 | portfolio/balances/positions/trading 路由 404；reports/templates 路由正常；dashboard 显示最近 runs | reports 的 `portfolioSlug` 过滤参数删除时同步删 service 分支；`market_quote.py`、`symbol_name_cache.py` 保留（工具依赖） |
| P5 | `test_extension_contract.py` 绿；`/api/tools` 工具清单与迁移前一致（数量可 diff）；`docs/writing-extensions.md` 存在 | **顺序**：先切三个消费方（router/tool_catalog/dependencies）跑绿，再删旧机制。capability profile 校验逻辑一行不动。`extension_disabled` 分支删整支 |
| P6 | gateway 只剩 4 文件；`grep -rn "class.*Protocol" app` 无单实现残留 | 逐文件搬、搬一个跑一次 pytest；`_selected_strategies_for_request` 删前先 grep 确认无调用 |
| P7 | 3 个新测试文件绿（auth/cancel/retention）；不设 token 时 e2e 全绿 | 7.3 是全计划唯一"真开发"任务：协作式取消检查点要先读懂执行循环（brief 里有定位 grep）；cancel queued run 必须释放队列 lease 行 |
| P8 | 后端 tests LOC 约 -1.5 万；前端删 5 个 jsdom 大文件;`pnpm test:e2e` 绿 | 8.1 builder 用 ruamel round-trip，**禁止字符串 replace**；8.5 删除前必须完成 e2e 覆盖比对，缺口先补 e2e 再删 |
| P9 | knip/ruff 清扫零残留；AGENTS.md 只剩根目录一个；README 定位已改；Docker 冒烟通过 | knip 报告要逐条人审再删（动态 import 会误报）；`generated-form`/`launch-input-state` 是 launch 页依赖,别被 knip 误伤 |

## 6. 升级/求助规则

**自行决定：** 行号漂移、符号改名、计划 grep 命令返回多个候选（选语义匹配者并在报告注明）、测试 fixture 构造细节。

**BLOCKED 上报 owner（停止该 Task,不要猜）：**
- 计划正文与仓库现实语义冲突（不是位置漂移，是"这东西和计划描述的不是一回事"）；
- 某删除目标被计划声明保留的功能真实依赖（例：发现 reports 实际有 portfolio 外键）；
- reviewer 发现与计划正文冲突且双方都有道理；
- 任何想新增依赖/抽象/兼容层的冲动——答案大概率是"不"，但由 owner 说。

**预期结果基准：** 全部完成后 `git ls-files '*.py' '*.ts' '*.tsx' | xargs wc -l` 应比基线少 **4.5万~5.5万行**。若少于 3 万，大概率有 Phase 被打折执行；若多删了，检查是否误删保留清单（计划"保留"总表）中的东西。

## 7. 文件索引

- 实施计划（唯一需求来源）：`docs/superpowers/plans/2026-07-08-mini-jenkins-migration.md`
- 本交接文档：`docs/superpowers/plans/2026-07-08-mini-jenkins-migration-handoff.md`
- 审计结论已全部固化进计划，无需另读审计原文；计划中每条 grep/路径均在 2026-07-08 对仓库核实过。
