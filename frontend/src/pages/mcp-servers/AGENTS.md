# FRONTEND MCP SERVERS PAGES GUIDE

> Inherits `/AGENTS.md`, `/frontend/AGENTS.md`, and `/frontend/src/pages/AGENTS.md`.

## OVERVIEW
`src/pages/mcp-servers/` contains the routed MCP server inventory and editor. The page family covers archive, activate, and connection-test flows, with transport-specific command and URL rules handled in the editor.

## WHERE TO LOOK
| Task | Location | Notes |
|---|---|---|
| MCP server inventory | `list.tsx` | list query, edit, archive, and transport summary |
| MCP server editor | `editor.tsx` | create/update, activate, test connection, auth JSON, transport rules |
| MCP server hooks | `../../hooks/use-mcp-servers.ts` | list/detail CRUD, activate, archive, and connection test |
| Shared platform helpers | `../platform-resource-shared.tsx` | badges, JSON helpers, and key sorting |
| MCP server types | `../../lib/types/mcp-server.ts` | transport, auth, command, URL, and activation payloads |

## CONVENTIONS
- `stdio` servers require a command, while `http-sse` servers require a URL.
- Auth is edited as JSON and parsed through the shared JSON helper.
- `key` is normalized to lowercase before submit.
- `list.tsx` only handles inventory actions and summaries, not connection testing.
- Hooks own cache invalidation and connection-test requests, while the page owns toasts and inline feedback.

## ANTI-PATTERNS
- Do not let a `stdio` draft submit without a command.
- Do not let an `http-sse` draft submit without a URL.
- Do not store auth as freeform text outside JSON handling.
- Do not bypass the hook layer for activate, archive, or test-connection calls.

## VALIDATION
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm test:run
```
