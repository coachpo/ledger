# Writing Extensions

SignalDeck extensions are static backend code contracts. There is no
marketplace, runtime discovery, install API, enable/disable state, or
`/api/extensions` route.

## Contract Fields

An extension declares an `EXTENSION = Extension(...)` value with these fields:

- `key`: canonical owner key, for example `signaldeck.finance`.
- `api_routers`: FastAPI routers mounted under `/api/v1`.
- `tool_declarations`: server-declared `/api/tools` metadata.
- `runtime_tool_specs`: native runtime executors for declared tools.
- `provider_factories`: named factories consumed by backend composition.
- `runtime_dependency_surfaces`: run dependency surface labels copied into package/run provenance.
- `package_private_mcp_tool_keys`: private MCP tool keys owned by the extension.

Tool keys must stay owner-qualified:
`signaldeck.<owner>.<tool_collection>.<tool>`. OpenAI function names are the
mechanical underscore mapping from those keys.

Bundled extensions today are:

- `signaldeck.finance`: templates/reports routers, finance providers, finance
  runtime tools, and package-private ownership of `web_search_exa`.
- `signaldeck.digital_oracle`: Digital Oracle runtime tools only; no API router
  and no browser route.

## Add An Extension

1. Create a backend package under `backend/app/extensions/<name>/`.
2. Declare `EXTENSION` in that package's `__init__.py`.
3. Add the `Extension` object to `INSTALLED_EXTENSIONS` in
   `backend/app/extensions/registry.py`.

Do not use dynamic `import_module` discovery or registrar side effects.

Bundled Workflow Package preset seeds use `ON CONFLICT DO UPDATE`; shipped
presets are managed/read-only and can overwrite same-key edits on restart.

## Multiple Implementations

Two extensions can expose similar capability through different owner keys:

- `signaldeck.finance.news.lookup`
- `acme.research.news.lookup`

A Workflow Package chooses one or both in its capability profile:

```yaml
capabilityProfiles:
  - key: news_research
    name: News Research
    toolKeys:
      - signaldeck.finance.news.lookup
```

Switching implementation is a manifest choice, not a platform alias:

```yaml
capabilityProfiles:
  - key: news_research
    name: News Research
    toolKeys:
      - acme.research.news.lookup
```
