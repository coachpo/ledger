import type { FrontendExtensionDefinition } from "../types";

export const FINANCE_WORKSPACE_EXTENSION_KEY = "signaldeck.finance";
export const FINANCE_WORKSPACE_LABEL = "Finance Workspace";

const financeRouteContributions = [
  {
    componentModule: "@/pages/dashboard#Dashboard",
    path: "/",
    requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
  },
  {
    componentModule: "@/pages/portfolios/list#PortfolioListPage",
    path: "/portfolios",
    requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
  },
  {
    componentModule: "@/pages/portfolios/detail#PortfolioDetailPage",
    path: "/portfolios/:portfolioId",
    requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
  },
  {
    componentModule: "@/pages/templates/list#TemplateListPage",
    path: "/templates",
    requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
  },
  {
    componentModule: "@/pages/templates/editor#TemplateEditorPage",
    path: "/templates/new",
    requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
  },
  {
    componentModule: "@/pages/templates/editor#TemplateEditorPage",
    path: "/templates/:templateId/edit",
    requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
  },
  {
    componentModule: "@/pages/reports/list#ReportListPage",
    path: "/reports",
    requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
  },
  {
    componentModule: "@/pages/reports/detail#ReportDetailPage",
    path: "/reports/:slug",
    requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
  },
] as const;

const financeNavContributions = [
  {
    iconName: "LayoutDashboard",
    label: "Dashboard",
    requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
    testId: "nav-dashboard",
    to: "/",
  },
  {
    iconName: "Briefcase",
    label: "Portfolios",
    requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
    testId: "nav-portfolios",
    to: "/portfolios",
  },
  {
    iconName: "FileText",
    label: "Templates",
    requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
    testId: "nav-templates",
    to: "/templates",
  },
  {
    iconName: "ClipboardList",
    label: "Reports",
    requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
    testId: "nav-reports",
    to: "/reports",
  },
] as const;

export const financeWorkspaceFrontendExtension = {
  key: FINANCE_WORKSPACE_EXTENSION_KEY,
  label: FINANCE_WORKSPACE_LABEL,
  navContributions: financeNavContributions,
  routeContributions: financeRouteContributions,
  toolAuthoringDiscovery: [
    {
      requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
      toolKeyPrefix: "signaldeck.market_data.",
    },
    {
      requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
      toolKeyPrefix: "signaldeck.indicators.",
    },
    {
      requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
      toolKeyPrefix: "signaldeck.fundamentals.",
    },
    {
      requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
      toolKeyPrefix: "signaldeck.news.",
    },
    {
      requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
      toolKeyPrefix: "signaldeck.social_sentiment.",
    },
    {
      requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
      toolKeyPrefix: "signaldeck.insider_data.",
    },
    {
      requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
      toolKeyPrefix: "signaldeck.positions.",
    },
    {
      requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
      toolKeyPrefix: "signaldeck.reports.",
    },
  ],
} as const satisfies FrontendExtensionDefinition;

export function getFinanceWorkspaceFrontendExtension(): FrontendExtensionDefinition {
  return financeWorkspaceFrontendExtension;
}
