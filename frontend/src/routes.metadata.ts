import { matchPath } from "react-router";

import {
  financeWorkspaceFrontendExtension,
  FINANCE_WORKSPACE_LABEL,
} from "@/extensions/signaldeck-finance";

export const UNKNOWN_ROUTE_PATTERN = "*" as const;
export const AGENT_PLATFORM_NAV_GROUP = "Agent Platform" as const;
export const FINANCE_WORKSPACE_NAV_GROUP = FINANCE_WORKSPACE_LABEL;
export const SYSTEM_NAV_GROUP = "System" as const;

export type AbsoluteRoutePath = `/${string}`;
export type RoutePattern = AbsoluteRoutePath | typeof UNKNOWN_ROUTE_PATTERN;
export type RouteArchetype =
  | "dashboard"
  | "inventory"
  | "detail"
  | "editor"
  | "console"
  | "systemState"
  | "unknown";
export type RouteShellMode = "scroll" | "fullHeight";

export type RouteNavGroup =
  | typeof AGENT_PLATFORM_NAV_GROUP
  | typeof FINANCE_WORKSPACE_NAV_GROUP
  | typeof SYSTEM_NAV_GROUP;

export const SIDEBAR_NAV_GROUP_ORDER = [
  AGENT_PLATFORM_NAV_GROUP,
  FINANCE_WORKSPACE_NAV_GROUP,
  SYSTEM_NAV_GROUP,
] as const satisfies readonly RouteNavGroup[];

export type RouteNavIconName =
  | "Briefcase"
  | "ClipboardList"
  | "Database"
  | "FileText"
  | "LayoutDashboard"
  | "Link2"
  | "PlayCircle"
  | "Puzzle"
  | "Workflow";

export type RouteStateVariant =
  | "ready"
  | "loading"
  | "error"
  | "empty"
  | "filteredEmpty"
  | "disabledExtension"
  | "unauthorized"
  | "notFound"
  | "creating"
  | "editing"
  | "saving"
  | "importing"
  | "validating"
  | "launching"
  | "polling";

export type RouteOwnership =
  | { kind: "platform" }
  | { kind: "system" }
  | {
      extensionKey: string;
      extensionLabel: string;
      kind: "extension";
    }
  | { kind: "unknown" };

export type RouteBreadcrumbMetadata = {
  parent?: {
    href: AbsoluteRoutePath;
    title: string;
  };
  title: string;
};

export type RouteNavMetadata = {
  group: RouteNavGroup;
  iconName: RouteNavIconName;
  label: string;
  path?: AbsoluteRoutePath;
  sidebar: boolean;
  testId: string;
};

export type RouteMetadata = {
  archetype: RouteArchetype;
  breadcrumb: RouteBreadcrumbMetadata;
  nav: RouteNavMetadata;
  owner: RouteOwnership;
  pattern: RoutePattern;
  shellMode: RouteShellMode;
  stateVariants: readonly RouteStateVariant[];
  testId: string;
};

export type RouteNavGroupMetadata = {
  items: readonly RouteMetadata[];
  label: RouteNavGroup;
};

type FinanceRouteContribution =
  (typeof financeWorkspaceFrontendExtension.routeContributions)[number];
type FinanceRoutePath = FinanceRouteContribution["path"];
type FinanceNavContribution =
  (typeof financeWorkspaceFrontendExtension.navContributions)[number];
type FinanceNavPath = FinanceNavContribution["to"];

type FinanceRouteMetadataOverride = Omit<
  RouteMetadata,
  "nav" | "owner" | "pattern"
> & {
  navPath: FinanceNavPath;
};

const financeRouteMetadataByPath = {
  "/": {
    archetype: "dashboard",
    breadcrumb: { title: "Dashboard" },
    navPath: "/",
    shellMode: "scroll",
    stateVariants: ["loading", "ready", "error", "disabledExtension"],
    testId: "route-dashboard",
  },
  "/portfolios": {
    archetype: "inventory",
    breadcrumb: { title: "Portfolios" },
    navPath: "/portfolios",
    shellMode: "scroll",
    stateVariants: [
      "loading",
      "ready",
      "error",
      "empty",
      "disabledExtension",
    ],
    testId: "route-portfolios-list",
  },
  "/portfolios/:portfolioId": {
    archetype: "detail",
    breadcrumb: {
      parent: { href: "/portfolios", title: "Portfolios" },
      title: "Portfolio Detail",
    },
    navPath: "/portfolios",
    shellMode: "scroll",
    stateVariants: [
      "loading",
      "ready",
      "error",
      "notFound",
      "disabledExtension",
    ],
    testId: "route-portfolio-detail",
  },
  "/templates": {
    archetype: "inventory",
    breadcrumb: { title: "Templates" },
    navPath: "/templates",
    shellMode: "scroll",
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
  "/templates/new": {
    archetype: "editor",
    breadcrumb: {
      parent: { href: "/templates", title: "Templates" },
      title: "New Template",
    },
    navPath: "/templates",
    shellMode: "fullHeight",
    stateVariants: ["creating", "saving", "error", "disabledExtension"],
    testId: "route-template-new",
  },
  "/templates/:templateId/edit": {
    archetype: "editor",
    breadcrumb: {
      parent: { href: "/templates", title: "Templates" },
      title: "Edit Template",
    },
    navPath: "/templates",
    shellMode: "fullHeight",
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
  "/reports": {
    archetype: "inventory",
    breadcrumb: { title: "Reports" },
    navPath: "/reports",
    shellMode: "scroll",
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
  "/reports/:slug": {
    archetype: "detail",
    breadcrumb: {
      parent: { href: "/reports", title: "Reports" },
      title: "Report Detail",
    },
    navPath: "/reports",
    shellMode: "scroll",
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
} as const satisfies Record<FinanceRoutePath, FinanceRouteMetadataOverride>;

const financeNavContributionByPath = new Map<FinanceNavPath, FinanceNavContribution>(
  financeWorkspaceFrontendExtension.navContributions.map((contribution) => [
    contribution.to,
    contribution,
  ]),
);

function financeNavMetadata(
  navPath: FinanceNavPath,
  sidebar: boolean,
): RouteNavMetadata {
  const contribution = financeNavContributionByPath.get(navPath);

  if (!contribution) {
    throw new Error(`Missing finance nav metadata for ${navPath}`);
  }

  return {
    group: FINANCE_WORKSPACE_NAV_GROUP,
    iconName: contribution.iconName,
    label: contribution.label,
    path: contribution.to,
    sidebar,
    testId: contribution.testId,
  };
}

const financeRouteMetadata: RouteMetadata[] =
  financeWorkspaceFrontendExtension.routeContributions.map((contribution) => {
    const { navPath, ...metadata } = financeRouteMetadataByPath[contribution.path];

    return {
      ...metadata,
      nav: financeNavMetadata(navPath, contribution.path === navPath),
      owner: {
        extensionKey: contribution.requiredExtensionKey,
        extensionLabel: FINANCE_WORKSPACE_LABEL,
        kind: "extension",
      },
      pattern: contribution.path,
    };
  });

const platformAndSystemRouteMetadata = [
  {
    archetype: "systemState",
    breadcrumb: { title: "Extensions" },
    nav: {
      group: SYSTEM_NAV_GROUP,
      iconName: "Puzzle",
      label: "Extensions",
      path: "/extensions",
      sidebar: true,
      testId: "nav-extensions",
    },
    owner: { kind: "system" },
    pattern: "/extensions",
    shellMode: "scroll",
    stateVariants: ["loading", "ready", "error", "empty"],
    testId: "route-extensions",
  },
  {
    archetype: "inventory",
    breadcrumb: { title: "Workflow Packages" },
    nav: {
      group: AGENT_PLATFORM_NAV_GROUP,
      iconName: "Workflow",
      label: "Workflow Packages",
      path: "/workflow-packages",
      sidebar: true,
      testId: "nav-workflow-packages",
    },
    owner: { kind: "platform" },
    pattern: "/workflow-packages",
    shellMode: "scroll",
    stateVariants: ["loading", "ready", "error", "empty", "filteredEmpty"],
    testId: "route-workflow-packages-list",
  },
  {
    archetype: "editor",
    breadcrumb: {
      parent: { href: "/workflow-packages", title: "Workflow Packages" },
      title: "Import Workflow Package",
    },
    nav: {
      group: AGENT_PLATFORM_NAV_GROUP,
      iconName: "Workflow",
      label: "Workflow Packages",
      path: "/workflow-packages",
      sidebar: false,
      testId: "nav-workflow-packages",
    },
    owner: { kind: "platform" },
    pattern: "/workflow-packages/import",
    shellMode: "fullHeight",
    stateVariants: ["importing", "validating", "error"],
    testId: "route-workflow-package-import",
  },
  {
    archetype: "editor",
    breadcrumb: {
      parent: { href: "/workflow-packages", title: "Workflow Packages" },
      title: "New Workflow Package",
    },
    nav: {
      group: AGENT_PLATFORM_NAV_GROUP,
      iconName: "Workflow",
      label: "Workflow Packages",
      path: "/workflow-packages",
      sidebar: false,
      testId: "nav-workflow-packages",
    },
    owner: { kind: "platform" },
    pattern: "/workflow-packages/new",
    shellMode: "fullHeight",
    stateVariants: ["creating", "saving", "validating", "error"],
    testId: "route-workflow-package-new",
  },
  {
    archetype: "editor",
    breadcrumb: {
      parent: { href: "/workflow-packages", title: "Workflow Packages" },
      title: "Workflow Package Detail",
    },
    nav: {
      group: AGENT_PLATFORM_NAV_GROUP,
      iconName: "Workflow",
      label: "Workflow Packages",
      path: "/workflow-packages",
      sidebar: false,
      testId: "nav-workflow-packages",
    },
    owner: { kind: "platform" },
    pattern: "/workflow-packages/:packageId",
    shellMode: "fullHeight",
    stateVariants: [
      "loading",
      "editing",
      "saving",
      "validating",
      "error",
      "notFound",
    ],
    testId: "route-workflow-package-detail",
  },
  {
    archetype: "console",
    breadcrumb: {
      parent: { href: "/workflow-packages", title: "Workflow Packages" },
      title: "Launch Workflow Package",
    },
    nav: {
      group: AGENT_PLATFORM_NAV_GROUP,
      iconName: "Workflow",
      label: "Workflow Packages",
      path: "/workflow-packages",
      sidebar: false,
      testId: "nav-workflow-packages",
    },
    owner: { kind: "platform" },
    pattern: "/workflow-packages/:packageId/run",
    shellMode: "fullHeight",
    stateVariants: ["loading", "ready", "error", "launching", "notFound"],
    testId: "route-workflow-package-launch",
  },
  {
    archetype: "inventory",
    breadcrumb: { title: "Model Connections" },
    nav: {
      group: AGENT_PLATFORM_NAV_GROUP,
      iconName: "Link2",
      label: "Model Connections",
      path: "/model-connections",
      sidebar: true,
      testId: "nav-model-connections",
    },
    owner: { kind: "platform" },
    pattern: "/model-connections",
    shellMode: "scroll",
    stateVariants: ["loading", "ready", "error", "empty", "filteredEmpty"],
    testId: "route-model-connections-list",
  },
  {
    archetype: "editor",
    breadcrumb: {
      parent: { href: "/model-connections", title: "Model Connections" },
      title: "New Model Connection",
    },
    nav: {
      group: AGENT_PLATFORM_NAV_GROUP,
      iconName: "Link2",
      label: "Model Connections",
      path: "/model-connections",
      sidebar: false,
      testId: "nav-model-connections",
    },
    owner: { kind: "platform" },
    pattern: "/model-connections/new",
    shellMode: "fullHeight",
    stateVariants: ["creating", "saving", "error"],
    testId: "route-model-connection-new",
  },
  {
    archetype: "editor",
    breadcrumb: {
      parent: { href: "/model-connections", title: "Model Connections" },
      title: "Edit Model Connection",
    },
    nav: {
      group: AGENT_PLATFORM_NAV_GROUP,
      iconName: "Link2",
      label: "Model Connections",
      path: "/model-connections",
      sidebar: false,
      testId: "nav-model-connections",
    },
    owner: { kind: "platform" },
    pattern: "/model-connections/:modelConnectionId/edit",
    shellMode: "fullHeight",
    stateVariants: ["loading", "editing", "saving", "error", "notFound"],
    testId: "route-model-connection-edit",
  },
  {
    archetype: "inventory",
    breadcrumb: { title: "Memory" },
    nav: {
      group: AGENT_PLATFORM_NAV_GROUP,
      iconName: "Database",
      label: "Memory",
      path: "/memory",
      sidebar: true,
      testId: "nav-memory",
    },
    owner: { kind: "platform" },
    pattern: "/memory",
    shellMode: "scroll",
    stateVariants: ["loading", "ready", "error", "empty", "unauthorized"],
    testId: "route-memory-list",
  },
  {
    archetype: "inventory",
    breadcrumb: { title: "Runs" },
    nav: {
      group: AGENT_PLATFORM_NAV_GROUP,
      iconName: "PlayCircle",
      label: "Runs",
      path: "/runs",
      sidebar: true,
      testId: "nav-runs",
    },
    owner: { kind: "platform" },
    pattern: "/runs",
    shellMode: "scroll",
    stateVariants: [
      "loading",
      "ready",
      "error",
      "empty",
      "filteredEmpty",
      "polling",
    ],
    testId: "route-runs-list",
  },
  {
    archetype: "console",
    breadcrumb: {
      parent: { href: "/runs", title: "Runs" },
      title: "Run Detail",
    },
    nav: {
      group: AGENT_PLATFORM_NAV_GROUP,
      iconName: "PlayCircle",
      label: "Runs",
      path: "/runs",
      sidebar: false,
      testId: "nav-runs",
    },
    owner: { kind: "platform" },
    pattern: "/runs/:runId",
    shellMode: "fullHeight",
    stateVariants: ["loading", "ready", "error", "notFound", "polling"],
    testId: "route-run-detail",
  },
] as const satisfies readonly RouteMetadata[];

export const liveRouteMetadata: readonly RouteMetadata[] = [
  ...financeRouteMetadata,
  ...platformAndSystemRouteMetadata,
];

export const unknownRouteMetadata: RouteMetadata = {
  archetype: "unknown",
  breadcrumb: { title: "Page not found" },
  nav: {
    group: SYSTEM_NAV_GROUP,
    iconName: "Puzzle",
    label: "Unknown Route",
    sidebar: false,
    testId: "route-unknown",
  },
  owner: { kind: "unknown" },
  pattern: UNKNOWN_ROUTE_PATTERN,
  shellMode: "scroll",
  stateVariants: ["notFound"],
  testId: "route-unknown",
};

export const allRouteMetadata: readonly RouteMetadata[] = [
  ...liveRouteMetadata,
  unknownRouteMetadata,
];

const routeMetadataByPattern = new Map<RoutePattern, RouteMetadata>(
  allRouteMetadata.map((metadata) => [metadata.pattern, metadata]),
);

function normalizePathname(pathname: string): AbsoluteRoutePath {
  const pathWithoutQuery = pathname.split(/[?#]/, 1)[0] || "/";
  const absolutePath = pathWithoutQuery.startsWith("/")
    ? pathWithoutQuery
    : `/${pathWithoutQuery}`;

  return absolutePath.length > 1 && absolutePath.endsWith("/")
    ? (absolutePath.slice(0, -1) as AbsoluteRoutePath)
    : (absolutePath as AbsoluteRoutePath);
}

export function getRouteMetadataByPattern(
  pattern: RoutePattern,
): RouteMetadata | undefined {
  return routeMetadataByPattern.get(pattern);
}

export function requireRouteMetadataByPattern(pattern: RoutePattern): RouteMetadata {
  const metadata = getRouteMetadataByPattern(pattern);

  if (!metadata) {
    throw new Error(`Missing route metadata for ${pattern}`);
  }

  return metadata;
}

export function getRouteMetadataForPathname(pathname: string): RouteMetadata {
  const normalizedPathname = normalizePathname(pathname);

  return (
    liveRouteMetadata.find((metadata) =>
      matchPath({ end: true, path: metadata.pattern }, normalizedPathname),
    ) ?? unknownRouteMetadata
  );
}

export function getSidebarRouteMetadata(): RouteMetadata[] {
  return liveRouteMetadata.filter((metadata) => metadata.nav.sidebar);
}

export function getSidebarRouteMetadataByGroup(
  group: RouteNavGroup,
): RouteMetadata[] {
  return getSidebarRouteMetadata().filter(
    (metadata) => metadata.nav.group === group,
  );
}

export function getSidebarRouteMetadataGroups(): RouteNavGroupMetadata[] {
  return SIDEBAR_NAV_GROUP_ORDER.map((group) => ({
    items: getSidebarRouteMetadataByGroup(group),
    label: group,
  })).filter((group) => group.items.length > 0);
}

export function getSidebarRouteMetadataByPath(
  path: AbsoluteRoutePath,
): RouteMetadata | undefined {
  return getSidebarRouteMetadata().find((metadata) => metadata.nav.path === path);
}

export type RouteCoverageDefinition = {
  index?: boolean;
  path?: string;
};

export function routePatternFromDefinition(
  route: RouteCoverageDefinition,
): RoutePattern {
  if (route.index) {
    return "/";
  }

  if (route.path === UNKNOWN_ROUTE_PATTERN) {
    return UNKNOWN_ROUTE_PATTERN;
  }

  if (route.path) {
    return route.path.startsWith("/")
      ? (route.path as RoutePattern)
      : (`/${route.path}` as RoutePattern);
  }

  throw new Error("Cannot derive route metadata pattern for a pathless route.");
}

export function routePatternsFromDefinitions(
  routes: readonly RouteCoverageDefinition[],
): RoutePattern[] {
  return routes.map(routePatternFromDefinition);
}

export function assertRouteMetadataCoverage(
  routes: readonly RouteCoverageDefinition[],
): void {
  const missingPatterns = routePatternsFromDefinitions(routes).filter(
    (pattern) => !routeMetadataByPattern.has(pattern),
  );

  if (missingPatterns.length > 0) {
    throw new Error(
      `Missing route metadata for registered routes: ${missingPatterns.join(", ")}`,
    );
  }
}
