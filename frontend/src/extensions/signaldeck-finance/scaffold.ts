import { Dashboard } from "@/pages/dashboard";
import { PortfolioDetailPage } from "@/pages/portfolios/detail";
import { PortfolioListPage } from "@/pages/portfolios/list";
import { ReportDetailPage } from "@/pages/reports/detail";
import { ReportListPage } from "@/pages/reports/list";
import { TemplateEditorPage } from "@/pages/templates/editor";
import { TemplateListPage } from "@/pages/templates/list";

import type {
  FrontendExtensionDefinition,
  FrontendNavContribution,
  FrontendRouteContribution,
} from "../types";

export const FINANCE_WORKSPACE_EXTENSION_KEY = "signaldeck.finance";
export const FINANCE_WORKSPACE_LABEL = "Finance Workspace";

function financeRouteOwnerNav(
  nav: FrontendRouteContribution["routeMetadata"]["nav"],
  requiredExtensionKey: string,
): FrontendNavContribution | undefined {
  if (!nav.sidebar) {
    return undefined;
  }

  if (!nav.path) {
    throw new Error(`Finance sidebar nav is missing a path for ${nav.label}`);
  }

  return {
    iconName: nav.iconName,
    label: nav.label,
    requiredExtensionKey,
    testId: nav.testId,
    to: nav.path,
  };
}

const financeRouteContributions = [
  {
    Component: Dashboard,
    path: "/",
    requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
    routeMetadata: {
      archetype: "dashboard",
      breadcrumb: { title: "Dashboard" },
      nav: {
        group: FINANCE_WORKSPACE_LABEL,
        iconName: "LayoutDashboard",
        label: "Dashboard",
        path: "/",
        sidebar: true,
        testId: "nav-dashboard",
      },
      shellMode: "scroll",
      widthMode: "wide",
      stateVariants: ["loading", "ready", "error", "disabledExtension"],
      testId: "route-dashboard",
    },
  },
  {
    Component: PortfolioListPage,
    path: "/portfolios",
    requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
    routeMetadata: {
      archetype: "inventory",
      breadcrumb: { title: "Portfolios" },
      nav: {
        group: FINANCE_WORKSPACE_LABEL,
        iconName: "Briefcase",
        label: "Portfolios",
        path: "/portfolios",
        sidebar: true,
        testId: "nav-portfolios",
      },
      shellMode: "scroll",
      widthMode: "wide",
      stateVariants: ["loading", "ready", "error", "empty", "disabledExtension"],
      testId: "route-portfolios-list",
    },
  },
  {
    Component: PortfolioDetailPage,
    path: "/portfolios/:portfolioId",
    requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
    routeMetadata: {
      archetype: "detail",
      breadcrumb: {
        parent: { href: "/portfolios", title: "Portfolios" },
        title: "Portfolio Detail",
      },
      nav: {
        group: FINANCE_WORKSPACE_LABEL,
        iconName: "Briefcase",
        label: "Portfolios",
        path: "/portfolios",
        sidebar: false,
        testId: "nav-portfolios",
      },
      shellMode: "scroll",
      widthMode: "wide",
      stateVariants: [
        "loading",
        "ready",
        "error",
        "notFound",
        "disabledExtension",
      ],
      testId: "route-portfolio-detail",
    },
  },
  {
    Component: TemplateListPage,
    path: "/templates",
    requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
    routeMetadata: {
      archetype: "inventory",
      breadcrumb: { title: "Templates" },
      nav: {
        group: FINANCE_WORKSPACE_LABEL,
        iconName: "FileText",
        label: "Templates",
        path: "/templates",
        sidebar: true,
        testId: "nav-templates",
      },
      shellMode: "scroll",
      widthMode: "wide",
      stateVariants: [
        "loading",
        "ready",
        "error",
        "empty",
        "filteredEmpty",
        "disabledExtension",
      ],
      testId: "route-templates-list",
    },
  },
  {
    Component: TemplateEditorPage,
    path: "/templates/new",
    requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
    routeMetadata: {
      archetype: "editor",
      breadcrumb: {
        parent: { href: "/templates", title: "Templates" },
        title: "New Template",
      },
      nav: {
        group: FINANCE_WORKSPACE_LABEL,
        iconName: "FileText",
        label: "Templates",
        path: "/templates",
        sidebar: false,
        testId: "nav-templates",
      },
      shellMode: "fullHeight",
      widthMode: "full",
      stateVariants: ["creating", "saving", "error", "disabledExtension"],
      testId: "route-template-new",
    },
  },
  {
    Component: TemplateEditorPage,
    path: "/templates/:templateId/edit",
    requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
    routeMetadata: {
      archetype: "editor",
      breadcrumb: {
        parent: { href: "/templates", title: "Templates" },
        title: "Edit Template",
      },
      nav: {
        group: FINANCE_WORKSPACE_LABEL,
        iconName: "FileText",
        label: "Templates",
        path: "/templates",
        sidebar: false,
        testId: "nav-templates",
      },
      shellMode: "fullHeight",
      widthMode: "full",
      stateVariants: [
        "loading",
        "editing",
        "saving",
        "error",
        "notFound",
        "disabledExtension",
      ],
      testId: "route-template-edit",
    },
  },
  {
    Component: ReportListPage,
    path: "/reports",
    requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
    routeMetadata: {
      archetype: "inventory",
      breadcrumb: { title: "Reports" },
      nav: {
        group: FINANCE_WORKSPACE_LABEL,
        iconName: "ClipboardList",
        label: "Reports",
        path: "/reports",
        sidebar: true,
        testId: "nav-reports",
      },
      shellMode: "scroll",
      widthMode: "wide",
      stateVariants: [
        "loading",
        "ready",
        "error",
        "empty",
        "filteredEmpty",
        "disabledExtension",
      ],
      testId: "route-reports-list",
    },
  },
  {
    Component: ReportDetailPage,
    path: "/reports/:slug",
    requiredExtensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
    routeMetadata: {
      archetype: "detail",
      breadcrumb: {
        parent: { href: "/reports", title: "Reports" },
        title: "Report Detail",
      },
      nav: {
        group: FINANCE_WORKSPACE_LABEL,
        iconName: "ClipboardList",
        label: "Reports",
        path: "/reports",
        sidebar: false,
        testId: "nav-reports",
      },
      shellMode: "scroll",
      widthMode: "readable",
      stateVariants: [
        "loading",
        "editing",
        "saving",
        "error",
        "notFound",
        "disabledExtension",
      ],
      testId: "route-report-detail",
    },
  },
] as const satisfies readonly FrontendRouteContribution[];

const financeNavContributions = financeRouteContributions
  .map((contribution) =>
    financeRouteOwnerNav(
      contribution.routeMetadata.nav,
      contribution.requiredExtensionKey,
    ),
  )
  .filter(
    (contribution): contribution is FrontendNavContribution =>
      contribution !== undefined,
  );

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
