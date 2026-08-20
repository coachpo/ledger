# SignalDeck

SignalDeck 是一个面向 LLM agent 的自托管流水线运行器：用 YAML 定义 Workflow Package，手动或按计划启动多 agent 工作流，并在统一的单用户界面中查看运行证据、输出、模板和报告。

当前项目用于本地开发调试和个人使用，部署边界是本地内网；在不降低既有正确性、数据完整性和密钥处理边界的前提下，开发与使用便利度优先于额外的安全加固。完整状态以 [`STATUS.md`](STATUS.md) 为准。

## 快速开始

需要 Docker 和 Docker Compose v2，以及一个 LLM 提供商的 API key：

```bash
git clone https://github.com/coachpo/signaldeck.git
cd signaldeck
./start.sh
```

默认应用地址为 `http://localhost:8080`，可用 `APP_PORT` 覆盖端口。首次打开后，在 **Model Connections** 中配置模型，再到 **Workflow Packages** 启动演示包；运行证据可在 **Runs** 查看。演示 YAML 位于 [`demo/`](demo/)。

## 文档

- [`docs/README.md`](docs/README.md)：文档索引；
- [`docs/产品说明.md`](docs/产品说明.md)：产品范围、流程和验收；
- [`docs/架构说明.md`](docs/架构说明.md)：架构边界和数据流；
- [`CONTRIBUTING.md`](CONTRIBUTING.md)：开发、验证和完成定义；
- [`STATUS.md`](STATUS.md)：当前项目状态。

根目录组合栈仅用于本地/演示；生产拆分镜像示例见 [`docker/compose.production.example.yml`](docker/compose.production.example.yml)。
