"""Canonical phase-1 ownership inventory for ``ledger.finance``.

This module is declarative only. It does not register routers, enable/disable
state, runtime tools, or provider factories; later extension-registry work can
consume the constants here without changing today's public behavior.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OwnershipSurfaceGroup:
    category: str
    summary: str
    surfaces: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "summary": self.summary,
            "surfaces": list(self.surfaces),
        }


@dataclass(frozen=True, slots=True)
class ExtensionOwnershipArtifact:
    extension_key: str
    label: str
    default_enabled: bool
    phase: str
    versioning_rule: str
    contribution_categories: tuple[str, ...]
    extension_owned_public_surfaces: tuple[OwnershipSurfaceGroup, ...]
    core_retained_surfaces: tuple[OwnershipSurfaceGroup, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "extensionKey": self.extension_key,
            "label": self.label,
            "defaultEnabled": self.default_enabled,
            "phase": self.phase,
            "versioningRule": self.versioning_rule,
            "contributionCategories": list(self.contribution_categories),
            "extensionOwnedPublicSurfaces": [
                group.as_dict() for group in self.extension_owned_public_surfaces
            ],
            "coreRetainedSurfaces": [group.as_dict() for group in self.core_retained_surfaces],
        }


def _join_text(*parts: str) -> str:
    return "".join(parts)


FINANCE_WORKSPACE_EXTENSION_KEY = "ledger.finance"
FINANCE_WORKSPACE_LABEL = "Finance Workspace"
FINANCE_WORKSPACE_DEFAULT_ENABLED = True
FINANCE_WORKSPACE_PHASE = "phase_1_bundled_first_party"
FINANCE_WORKSPACE_VERSIONING_RULE = (
    "Bundled with the Ledger backend package version in phase 1; no independent "
    "extension semver exists until a registry/state contract introduces one. "
    "Routes, runtime tool keys, OpenAI function names, placeholder roots, report "
    "metadata semantics, and workflow manifest contracts stay stable while enabled."
)

FINANCE_WORKSPACE_CONTRIBUTION_CATEGORIES = (
    "backend_api_routes",
    "backend_domain_services",
    "native_runtime_tools",
    "provider_integrations",
    "report_backed_memory_automation",
    "frontend_finance_routes",
    "frontend_finance_navigation",
    "frontend_api_hooks_query_keys",
    "frontend_tool_discovery_contributions",
    "docs_contract_references",
    "test_fixtures_and_regressions",
)

FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS = (
    "ledger.market_data.quote_lookup",
    "ledger.market_data.history_lookup",
    "ledger.market_data.ohlcv_lookup",
    "ledger.indicators.lookup",
    "ledger.fundamentals.lookup",
    "ledger.news.lookup",
    "ledger.social_sentiment.lookup",
    "ledger.insider_data.lookup",
    "ledger.positions.lookup",
    "ledger.reports.lookup",
    "ledger.reports.write",
)

FINANCE_WORKSPACE_OPENAI_FUNCTION_NAMES = (
    "ledger_market_data_quote_lookup",
    "ledger_market_data_history_lookup",
    "ledger_market_data_ohlcv_lookup",
    "ledger_indicators_lookup",
    "ledger_fundamentals_lookup",
    "ledger_news_lookup",
    "ledger_social_sentiment_lookup",
    "ledger_insider_data_lookup",
    "ledger_positions_lookup",
    "ledger_reports_lookup",
    "ledger_reports_write",
)

_EXTENSION_OWNED_SURFACES = (
    OwnershipSurfaceGroup(
        category="backend_api_routes",
        summary="Preserved `/api/v1` finance workspace route families move behind the extension.",
        surfaces=(
            _join_text(
                "GET/POST /api/v1/portfolios -> backend/app/api/portfolios.py ",
                '(APIRouter(prefix="/portfolios"))',
            ),
            _join_text(
                "GET/POST /api/v1/portfolios/{portfolioId}/balances -> ",
                "backend/app/api/balances.py ",
                '(APIRouter(prefix="/portfolios/{portfolio_id}/balances"))',
            ),
            _join_text(
                "GET/POST/PATCH/DELETE /api/v1/portfolios/{portfolioId}/positions plus ",
                "lookup/imports -> backend/app/api/positions.py",
            ),
            _join_text(
                "GET/POST /api/v1/portfolios/{portfolioId}/trading-operations -> ",
                "backend/app/api/trading_operations.py",
            ),
            _join_text(
                "GET /api/v1/portfolios/{portfolioId}/market-data/{quotes,history} -> ",
                "backend/app/api/market_data.py",
            ),
            _join_text(
                "GET/POST/PATCH/DELETE /api/v1/templates plus compile/placeholders -> ",
                'backend/app/api/templates.py (APIRouter(prefix="/templates"))',
            ),
            _join_text(
                "GET/POST/PATCH/DELETE /api/v1/reports plus compile/upload/download -> ",
                'backend/app/api/reports.py (APIRouter(prefix="/reports"))',
            ),
        ),
    ),
    OwnershipSurfaceGroup(
        category="backend_domain_services",
        summary="Business-rule and request dependencies behind the `/api/v1` finance workspace.",
        surfaces=(
            "backend/app/services/portfolio_service.py",
            "backend/app/services/balance_service.py",
            "backend/app/services/position_service.py",
            "backend/app/services/csv_import_service.py",
            "backend/app/services/trading_operation_service.py",
            "backend/app/services/market_data_service.py",
            "backend/app/services/template_compiler_service.py",
            "backend/app/services/text_template_service.py",
            "backend/app/services/report_service.py",
            "backend/app/api/dependencies.py finance service factories and quote-provider binding",
            "Template placeholder roots remain `inputs`, `portfolios`, and `reports`.",
            "Report sources remain `compiled`, `uploaded`, `external`, and `agent`.",
        ),
    ),
    OwnershipSurfaceGroup(
        category="native_runtime_tools",
        summary=_join_text(
            "Finance-native server tools and OpenAI function names ",
            "are extension contributions.",
        ),
        surfaces=FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS + FINANCE_WORKSPACE_OPENAI_FUNCTION_NAMES,
    ),
    OwnershipSurfaceGroup(
        category="provider_integrations",
        summary="External finance/provider adapters and warning semantics move with the extension.",
        surfaces=(
            "backend/app/services/quote_provider.py: YahooFinanceQuoteProvider (`yahoo_finance`)",
            "backend/app/services/quote_provider.py: DeterministicQuoteProvider test/dev fallback",
            "backend/app/services/market_data_service.py quote/history cache and degraded warnings",
            "backend/app/services/social_sentiment_provider.py: RedditSocialSentimentAdapter",
            "backend/app/services/social_sentiment_provider.py: StockTwitsSocialSentimentAdapter",
            "backend/app/services/social_sentiment_service.py source normalization/warnings",
            _join_text(
                "backend/app/agents/runtime_tools/market_data.py provider-backed ",
                "quote/history/OHLCV, indicators, fundamentals, news, social sentiment, ",
                "and insider-data executors",
            ),
        ),
    ),
    OwnershipSurfaceGroup(
        category="report_backed_memory_automation",
        summary="Phase-1 memory is report-backed and follows the finance reporting boundary.",
        surfaces=(
            "backend/app/agents/runtime_tools/reports.py: ledger_reports_lookup",
            "backend/app/agents/runtime_tools/reports.py: ledger_reports_write",
            "backend/app/services/memory_service.py",
            "backend/app/services/memory_report_service.py",
            "backend/app/services/memory_context_service.py",
            "backend/app/services/memory_follow_up_service.py",
            "backend/app/services/report_backed_memory_store.py",
            "backend/app/schemas/memory_report.py",
            'metadata.analysis.reviewType="agent_memory"',
            'metadata.analysis.versionGroup="agent_memory/v1"',
            'metadata.createdBy.type="agent"',
            "memoryId values remain opaque outside ReportBackedMemoryStore.",
        ),
    ),
    OwnershipSurfaceGroup(
        category="frontend_finance_routes",
        summary="Browser routes with finance data dependencies are finance extension surfaces.",
        surfaces=(
            "frontend/src/pages/dashboard.tsx -> `/` dashboard backed by usePortfolios()",
            "frontend/src/pages/portfolios/list.tsx -> `/portfolios`",
            "frontend/src/pages/portfolios/detail.tsx -> `/portfolios/:portfolioId`",
            "frontend/src/pages/templates/list.tsx -> `/templates`",
            _join_text(
                "frontend/src/pages/templates/editor.tsx -> `/templates/new` and ",
                "`/templates/:templateId/edit`",
            ),
            "frontend/src/pages/reports/list.tsx -> `/reports`",
            "frontend/src/pages/reports/detail.tsx -> `/reports/:slug`",
            "frontend/src/components/forms/generate-report-dialog.tsx",
            "frontend/src/components/forms/portfolio-form-dialog.tsx",
            "frontend/src/components/portfolios/*.tsx",
            "frontend/src/components/templates/*.tsx",
        ),
    ),
    OwnershipSurfaceGroup(
        category="frontend_finance_navigation",
        summary="Finance nav contributions currently live in the static layout shell.",
        surfaces=(
            "frontend/src/components/layout.tsx nav-dashboard -> `/`",
            "frontend/src/components/layout.tsx nav-portfolios -> `/portfolios`",
            "frontend/src/components/layout.tsx nav-templates -> `/templates`",
            "frontend/src/components/layout.tsx nav-reports -> `/reports`",
            "frontend/src/components/layout.tsx finance route page metadata",
        ),
    ),
    OwnershipSurfaceGroup(
        category="frontend_api_hooks_query_keys",
        summary=_join_text(
            "Frontend request/cache surfaces for finance product flows ",
            "move with the extension.",
        ),
        surfaces=(
            "frontend/src/lib/api/portfolios.ts",
            "frontend/src/lib/api/balances.ts",
            "frontend/src/lib/api/positions.ts",
            "frontend/src/lib/api/trading-operations.ts",
            "frontend/src/lib/api/market-data.ts",
            "frontend/src/lib/api/templates.ts",
            "frontend/src/lib/api/reports.ts",
            "frontend/src/hooks/use-portfolios.ts",
            "frontend/src/hooks/use-balances.ts",
            "frontend/src/hooks/use-positions.ts",
            "frontend/src/hooks/use-trading-operations.ts",
            "frontend/src/hooks/use-market-data.ts",
            "frontend/src/hooks/use-templates.ts",
            "frontend/src/hooks/use-reports.ts",
            _join_text(
                "frontend/src/lib/query-keys.ts finance namespaces: portfolios, balances, ",
                "positions, trades, marketData, marketHistory, templates, reports",
            ),
            "frontend/src/lib/portfolio-analytics.ts",
            "frontend/src/lib/runtime-inputs.ts",
            "frontend/src/lib/report-grouping.ts",
            "frontend/src/lib/markdown-format.ts",
        ),
    ),
    OwnershipSurfaceGroup(
        category="frontend_tool_discovery_contributions",
        summary="Tool discovery host remains core, but finance tool entries are extension-owned.",
        surfaces=(
            "frontend/src/lib/api/tools.ts exposes finance-owned tool keys through `/api/tools`.",
            "frontend/src/hooks/use-workflow-packages.ts: useTools() discovery hook",
            "frontend/src/pages/workflow-packages/editor.tsx Capability Profiles tool picker",
            "frontend/src/lib/platform-authoring/workflow-packages/manifest.ts toolKeys fields",
            "frontend/src/components/platform-authoring/**/*.tsx capability/tool form widgets",
        ),
    ),
    OwnershipSurfaceGroup(
        category="docs_contract_references",
        summary="Live docs sections that describe finance-owned routes/tools/providers/memory.",
        surfaces=(
            "docs/api-design.md preserved product API table and runtime tool contract notes",
            "docs/ledger-agent-platform.md tools, UI contract, and memory artifact notes",
            "docs/ledger-memory-layer-design.md report-backed memory tool and metadata contract",
            "docs/data-model.md portfolio/report/cache/memory-related persistence descriptions",
            "docs/test-plan.md finance route, tool, and memory validation targets",
            "docs/requirements.md finance workspace and report/memory requirements",
        ),
    ),
    OwnershipSurfaceGroup(
        category="test_fixtures_and_regressions",
        summary="Tests/fixtures that pin finance-owned public contracts and provider seams.",
        surfaces=(
            "backend/tests/test_api.py",
            "backend/tests/test_tool_catalog_api.py",
            "backend/tests/test_runtime_tools.py",
            "backend/tests/test_runtime_tools_social_sentiment.py",
            "backend/tests/test_market_data_service.py",
            "backend/tests/test_memory_reports.py",
            "backend/tests/test_memory_service.py",
            "backend/tests/test_report_backed_memory_store.py",
            "backend/tests/test_memory_follow_up_service.py",
            "backend/tests/test_workflow_package_smoke_fixture.py",
            "backend/tests/fixtures/workflow_packages/*.yaml demo package fixtures",
            "frontend/src/pages/templates/editor.test.tsx",
            "frontend/src/pages/reports/source-label.test.tsx",
            "frontend/src/pages/workflow-packages/resource-editors.test.tsx tool-key assertions",
        ),
    ),
)

_CORE_RETAINED_SURFACES = (
    OwnershipSurfaceGroup(
        category="backend_core_bootstrap_and_shared_infrastructure",
        summary=_join_text(
            "Core keeps app bootstrap, shared contracts, persistence plumbing, ",
            "and error envelopes.",
        ),
        surfaces=(
            "backend/app/main.py mounts routers and owns health/error/CORS behavior",
            "backend/app/api/router.py composition host for `/api/v1` remains stable",
            "backend/app/core/* shared config, errors, formatting, telemetry",
            "backend/app/db/* session lifecycle and PostgreSQL schema repair",
            "backend/app/schemas/* shared API serialization and manifest contracts",
            "backend/app/models/* shared ORM tables and constraints",
            "backend/app/repositories/* shared persistence query helpers",
        ),
    ),
    OwnershipSurfaceGroup(
        category="backend_platform_workflow_infrastructure",
        summary="Generic package-first workflow infrastructure stays core-retained.",
        surfaces=(
            "backend/app/api/platform_router.py `/api` composition",
            "GET/POST /api/workflow-packages plus version/preflight/launch/import/export",
            "GET/POST/PATCH/DELETE /api/model-connections and connection-test routes",
            "GET/DELETE /api/runs plus rerun and step-replay routes",
            "backend/app/services/workflow_package_*.py manifest and preflight services",
            "backend/app/services/model_connection_service.py",
            "backend/app/services/run_service.py generic run lifecycle and provenance host",
            "backend/app/services/http_operation_execution_service.py",
            "ledger.workflowPackage/v1 manifest shape and package-private resources",
        ),
    ),
    OwnershipSurfaceGroup(
        category="backend_tool_and_runtime_hosts",
        summary=_join_text(
            "Core keeps discovery/dispatch hosts; finance tool specs and executors ",
            "are owned above.",
        ),
        surfaces=(
            "backend/app/api/tools.py `GET /api/tools` read-only route host",
            "backend/app/agents/tool_catalog/__init__.py ToolCatalog validation framework",
            "backend/app/agents/runtime_tools/registry.py RuntimeToolRegistry dispatch host",
            "backend/app/agents/mcp/* saved MCP security/runtime boundaries",
            "backend/app/services/agent_execution_service.py invocation and SDK host",
            "Package capability profiles remain package-local core workflow infrastructure.",
        ),
    ),
    OwnershipSurfaceGroup(
        category="frontend_core_shell_and_primitives",
        summary="Core keeps application bootstrap, shell host, theme, and reusable UI primitives.",
        surfaces=(
            "frontend/src/App.tsx",
            "frontend/src/main.tsx",
            "frontend/src/components/layout.tsx shell host and breadcrumb renderer",
            "frontend/src/components/theme-provider.tsx",
            "frontend/src/components/theme-toggle.tsx",
            "frontend/src/components/ui/*.tsx",
            "frontend/src/components/shared/*.tsx when generic and finance-agnostic",
            "frontend/src/pages/platform-resource-shared.tsx",
        ),
    ),
    OwnershipSurfaceGroup(
        category="frontend_platform_workflow_surfaces",
        summary=_join_text(
            "Generic workflow UI routes remain core; only finance tool entries ",
            "are extension-owned.",
        ),
        surfaces=(
            "frontend/src/routes.ts platform routes: workflow-packages/model-connections/runs",
            "frontend/src/components/layout.tsx platform nav ids",
            "frontend/src/pages/workflow-packages/*.tsx package authoring host",
            "frontend/src/pages/model-connections/*.tsx saved provider binding host",
            "frontend/src/pages/runs/*.tsx run list/detail inspection host",
            "frontend/src/lib/api/workflow-packages.ts",
            "frontend/src/lib/api/model-connections.ts",
            "frontend/src/lib/api/runs.ts",
            "frontend/src/hooks/use-workflow-packages.ts package lifecycle hooks",
            "frontend/src/hooks/use-model-connections.ts",
            "frontend/src/hooks/use-runs.ts",
            "frontend/src/lib/query-keys.ts platform namespaces except finance-owned tool entries",
        ),
    ),
    OwnershipSurfaceGroup(
        category="docs_and_tests_infrastructure",
        summary="Docs/test harnesses stay core while finance-specific cases are owned above.",
        surfaces=(
            "docs/AGENTS.md governance for live docs set",
            "docs/ledger-agent-platform.md package-first platform reference sections",
            "backend/tests/conftest.py isolated PostgreSQL app fixture",
            "backend/tests/test_workflow_package_*.py generic package/runtime behavior",
            "backend/tests/test_legacy_backend_cutover.py removed legacy route guardrails",
            "frontend/src/routes.test.tsx retired route guardrails and platform route mounting",
            "frontend/src/components/layout.test.tsx shell host regression",
        ),
    ),
    OwnershipSurfaceGroup(
        category="retired_or_unmounted_surfaces",
        summary=_join_text(
            "Removed legacy authoring surfaces are neither core product ",
            "nor extension-owned features.",
        ),
        surfaces=(
            "/api/agents",
            "/api/capabilities",
            "/api/mcp-servers",
            "/api/output-schemas",
            "/api/workflows",
            "/api/v2/*",
            "retired global authoring frontend routes and docs",
        ),
    ),
)
FINANCE_WORKSPACE_OWNERSHIP = ExtensionOwnershipArtifact(
    extension_key=FINANCE_WORKSPACE_EXTENSION_KEY,
    label=FINANCE_WORKSPACE_LABEL,
    default_enabled=FINANCE_WORKSPACE_DEFAULT_ENABLED,
    phase=FINANCE_WORKSPACE_PHASE,
    versioning_rule=FINANCE_WORKSPACE_VERSIONING_RULE,
    contribution_categories=FINANCE_WORKSPACE_CONTRIBUTION_CATEGORIES,
    extension_owned_public_surfaces=_EXTENSION_OWNED_SURFACES,
    core_retained_surfaces=_CORE_RETAINED_SURFACES,
)

__all__ = [
    "ExtensionOwnershipArtifact",
    "FINANCE_WORKSPACE_CONTRIBUTION_CATEGORIES",
    "FINANCE_WORKSPACE_DEFAULT_ENABLED",
    "FINANCE_WORKSPACE_EXTENSION_KEY",
    "FINANCE_WORKSPACE_LABEL",
    "FINANCE_WORKSPACE_OPENAI_FUNCTION_NAMES",
    "FINANCE_WORKSPACE_OWNERSHIP",
    "FINANCE_WORKSPACE_PHASE",
    "FINANCE_WORKSPACE_RUNTIME_TOOL_KEYS",
    "FINANCE_WORKSPACE_VERSIONING_RULE",
    "OwnershipSurfaceGroup",
]
