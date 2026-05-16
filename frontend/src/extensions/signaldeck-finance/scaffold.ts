import type { FrontendExtensionDefinition, FrontendExtensionStateSource } from "../types";

export const FINANCE_WORKSPACE_EXTENSION_KEY = "signaldeck.finance";
export const FINANCE_WORKSPACE_LABEL = "Finance Workspace";
export const FINANCE_WORKSPACE_DEFAULT_ENABLED = true;
export const FINANCE_WORKSPACE_PHASE = "phase_1_bundled_first_party";

const backendStateSource = {
  defaultEnabled: FINANCE_WORKSPACE_DEFAULT_ENABLED,
  endpoint: "/api/extensions",
  extensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
  kind: "backend-extension-state",
} as const satisfies FrontendExtensionStateSource;

const financeRouteContributions = [
  {
    componentModule: "@/pages/dashboard#Dashboard",
    id: "finance.dashboard.route",
    owner: "extension",
    path: "/",
  },
  {
    componentModule: "@/pages/portfolios/list#PortfolioListPage",
    id: "finance.portfolios.list.route",
    owner: "extension",
    path: "/portfolios",
  },
  {
    componentModule: "@/pages/portfolios/detail#PortfolioDetailPage",
    id: "finance.portfolios.detail.route",
    owner: "extension",
    path: "/portfolios/:portfolioId",
  },
  {
    componentModule: "@/pages/templates/list#TemplateListPage",
    id: "finance.templates.list.route",
    owner: "extension",
    path: "/templates",
  },
  {
    componentModule: "@/pages/templates/editor#TemplateEditorPage",
    id: "finance.templates.new.route",
    owner: "extension",
    path: "/templates/new",
  },
  {
    componentModule: "@/pages/templates/editor#TemplateEditorPage",
    id: "finance.templates.edit.route",
    owner: "extension",
    path: "/templates/:templateId/edit",
  },
  {
    componentModule: "@/pages/reports/list#ReportListPage",
    id: "finance.reports.list.route",
    owner: "extension",
    path: "/reports",
  },
  {
    componentModule: "@/pages/reports/detail#ReportDetailPage",
    id: "finance.reports.detail.route",
    owner: "extension",
    path: "/reports/:slug",
  },
] as const;

const financeNavContributions = [
  {
    iconName: "LayoutDashboard",
    id: "finance.dashboard.nav",
    label: "Dashboard",
    owner: "extension",
    testId: "nav-dashboard",
    to: "/",
  },
  {
    iconName: "Briefcase",
    id: "finance.portfolios.nav",
    label: "Portfolios",
    owner: "extension",
    testId: "nav-portfolios",
    to: "/portfolios",
  },
  {
    iconName: "FileText",
    id: "finance.templates.nav",
    label: "Templates",
    owner: "extension",
    testId: "nav-templates",
    to: "/templates",
  },
  {
    iconName: "ClipboardList",
    id: "finance.reports.nav",
    label: "Reports",
    owner: "extension",
    testId: "nav-reports",
    to: "/reports",
  },
] as const;

const financeApiAvailability = [
  {
    id: "finance.portfolios.api",
    methodScope: ["GET", "POST", "PATCH", "DELETE"],
    pathPrefix: "/api/v1/portfolios",
    stateSource: backendStateSource,
  },
  {
    id: "finance.market-data.api",
    methodScope: ["GET"],
    pathPrefix: "/api/v1/portfolios/:portfolioId/market-data",
    stateSource: backendStateSource,
  },
  {
    id: "finance.templates.api",
    methodScope: ["GET", "POST", "PATCH", "DELETE"],
    pathPrefix: "/api/v1/templates",
    stateSource: backendStateSource,
  },
  {
    id: "finance.reports.api",
    methodScope: ["GET", "POST", "PATCH", "DELETE"],
    pathPrefix: "/api/v1/reports",
    stateSource: backendStateSource,
  },
] as const;

export const financeWorkspaceFrontendExtension = {
  adminPages: [],
  apiAvailability: financeApiAvailability,
  availability: {
    currentBehavior: "Routes, nav, and tool authoring discovery read backend extension state before exposing finance workspace contributions.",
    stateSource: backendStateSource,
  },
  defaultEnabled: FINANCE_WORKSPACE_DEFAULT_ENABLED,
  key: FINANCE_WORKSPACE_EXTENSION_KEY,
  label: FINANCE_WORKSPACE_LABEL,
  navContributions: financeNavContributions,
  phase: FINANCE_WORKSPACE_PHASE,
  routeContributions: financeRouteContributions,
  settingsPages: [],
  toolAuthoringDiscovery: [
    {
      catalogEndpoint: "/api/tools",
      host: "core-workflow-package-authoring",
      id: "finance.workflow-packages.tool-discovery",
      queryKeyNamespace: "platform.tools",
      sourceHook: "@/hooks/use-workflow-packages#useTools",
      toolKeyPrefix: "signaldeck.",
    },
  ],
} as const satisfies FrontendExtensionDefinition;

export function getFinanceWorkspaceFrontendExtension(): FrontendExtensionDefinition {
  return financeWorkspaceFrontendExtension;
}
