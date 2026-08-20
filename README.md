# SignalDeck

SignalDeck 是一个面向 LLM agent 的自托管流水线运行器：用 YAML 定义 Workflow Package，手动或按计划启动多 agent 工作流，并在统一的单用户界面中查看运行证据、输出、模板和报告。

## 当前状态

当前项目用于本地开发调试和个人使用，部署边界是本地内网；在不降低既有正确性、数据完整性和密钥处理边界的前提下，开发与使用便利度优先于额外的安全加固。此处只是派生摘要，完整状态以 [`STATUS.md`](STATUS.md) 为准。

## 快速开始

需要 Docker 和 Docker Compose v2，以及一个 LLM 提供商的 API key。

```bash
git clone https://github.com/coachpo/signaldeck.git
cd signaldeck
./start.sh
```

启动脚本构建并运行本地/演示组合栈，默认在 `http://localhost:8080` 提供应用；可用 `APP_PORT` 覆盖端口。按 `Ctrl+C` 停止前台进程；需要停止并删除容器时运行：

```bash
docker compose down
```

首次打开应用后，在 **Model Connections** 中保存模型提供商配置，再到 **Workflow Packages** 选择预置的演示包并启动运行。运行证据可在 **Runs** 中查看。两个演示包的 YAML 源文件位于 [`demo/`](demo/)。

根目录的 `docker-compose.yml`、根 `Dockerfile` 和 `start.sh` 仅用于本地/演示组合栈；拆分的 backend、scheduler、frontend 镜像及生产示例见 [`docker/compose.production.example.yml`](docker/compose.production.example.yml)。

## 主要能力

- Workflow Package：在一个 YAML 包中声明输入、包内 agent、输出 schema、工具能力、私有 MCP、HTTP 操作和工作流图。
- Scheduled Task：按 interval、daily、weekly 或 monthly 规则和 IANA 时区将到期任务物化为普通运行。
- Run evidence：保留不可变包快照、输入、步骤、agent/HTTP 操作证据、队列进度、重试、失败信息和最终输出。
- Model Connections：保存全局模型提供商绑定；API key 只写入、不在读取接口中返回。
- Templates 与 Reports：生成、编辑、下载模板和 markdown 报告快照。

## 文档

- [`docs/README.md`](docs/README.md)：文档索引与权威边界。
- [`docs/产品说明.md`](docs/产品说明.md)：产品范围、流程、需求和验收。
- [`docs/架构说明.md`](docs/架构说明.md)：当前组件、数据流、部署边界和架构例外。
- [`CONTRIBUTING.md`](CONTRIBUTING.md)：开发环境、启动、检查、测试、工作流和完成定义。
- [`docs/开发规范.md`](docs/开发规范.md)：项目特有的技术和实现规则。
- [`docs/源代码规模与职责规则.md`](docs/源代码规模与职责规则.md)：通用的规模与职责规则。
