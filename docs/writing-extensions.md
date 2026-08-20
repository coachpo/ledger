# 编写静态扩展

SignalDeck extension 是静态 backend code contract，不是 marketplace。当前没有 marketplace、runtime discovery、安装 API、enable/disable 状态或 `/api/extensions` 路由。

## Contract 字段

扩展在自己的包中声明 `EXTENSION = Extension(...)`，字段包括：

- `key`：canonical owner key，例如 `signaldeck.finance`；
- `api_routers`：挂载在 `/api/v1` 下的 FastAPI router；
- `tool_declarations`：`/api/tools` 返回的 server-declared metadata；
- `runtime_tool_specs`：声明工具的 native runtime executor；
- `provider_factories`：由 backend composition 消费的命名 factory；
- `runtime_dependency_surfaces`：复制到 package/run provenance 的运行依赖面标签；
- `package_private_mcp_tool_keys`：由扩展拥有的 package-private MCP tool key。

tool key 必须保持 owner-qualified，例如 `signaldeck.<owner>.<tool_collection>.<tool>`。OpenAI function name 使用这些 key 的机械 underscore mapping。

当前内置扩展：

- `signaldeck.finance`：Templates/Reports router、finance provider、finance runtime tools，以及 `web_search_exa` 的 package-private ownership；
- `signaldeck.digital_oracle`：Digital Oracle runtime tools，不提供 API router 或浏览器导航面。

## 添加扩展

1. 在 `backend/app/extensions/<name>/` 创建 backend package。
2. 在该 package 的 `__init__.py` 声明 `EXTENSION`。
3. 在 `backend/app/extensions/registry.py` 将 `Extension` 对象加入 `INSTALLED_EXTENSIONS`。
4. 为 API、tool declaration、provider 和 runtime executor 添加对应测试，并验证 owner-qualified key 唯一。

不要使用动态 `import_module` discovery 或 registrar side effect。Bundled Workflow Package preset seed 使用 `ON CONFLICT DO UPDATE`；已发布 preset 属于 managed/read-only 内容，重启时可能覆盖同 key 的修改。

## 多种实现

不同扩展可以用不同 owner key 提供相似能力：

- `signaldeck.finance.news.lookup`
- `acme.research.news.lookup`

Workflow Package 在 capability profile 中选择一个或多个：

```yaml
capabilityProfiles:
  - key: news_research
    name: News Research
    toolKeys:
      - signaldeck.finance.news.lookup
```

切换实现是 manifest 选择，而不是平台 alias：

```yaml
capabilityProfiles:
  - key: news_research
    name: News Research
    toolKeys:
      - acme.research.news.lookup
```
