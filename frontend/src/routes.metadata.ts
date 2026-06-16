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
export type RouteWidthMode = "wide" | "full" | "compact" | "readable";

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
  widthMode: RouteWidthMode;
  stateVariants: readonly RouteStateVariant[];
  testId: string;
};

export type RouteNavGroupMetadata = {
  items: readonly RouteMetadata[];
  label: RouteNavGroup;
};

const financeRouteMetadata: RouteMetadata[] =
  financeWorkspaceFrontendExtension.routeContributions.map((contribution) => ({
    ...contribution.routeMetadata,
    owner: {
      extensionKey: contribution.requiredExtensionKey,
      extensionLabel: FINANCE_WORKSPACE_LABEL,
      kind: "extension",
    },
    pattern: contribution.path,
  }));

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
    widthMode: "wide",
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
    widthMode: "wide",
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
    widthMode: "full",
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
    widthMode: "full",
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
    widthMode: "full",
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
    widthMode: "full",
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
    widthMode: "wide",
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
    widthMode: "full",
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
    widthMode: "full",
    stateVariants: ["loading", "editing", "saving", "error", "notFound"],
    testId: "route-model-connection-edit",
  },
  {
    archetype: "inventory",
    breadcrumb: { title: "Workflow Memory Review" },
    nav: {
      group: AGENT_PLATFORM_NAV_GROUP,
      iconName: "Database",
      label: "Memory Review",
      path: "/memory",
      sidebar: true,
      testId: "nav-memory",
    },
    owner: { kind: "platform" },
    pattern: "/memory",
    shellMode: "scroll",
    widthMode: "wide",
    stateVariants: ["loading", "ready", "error", "empty", "saving"],
    testId: "route-memory-list",
  },
  {
    archetype: "inventory",
    breadcrumb: { title: "Scheduled Tasks" },
    nav: {
      group: AGENT_PLATFORM_NAV_GROUP,
      iconName: "ClipboardList",
      label: "Scheduled Tasks",
      path: "/scheduled-tasks",
      sidebar: true,
      testId: "nav-scheduled-tasks",
    },
    owner: { kind: "platform" },
    pattern: "/scheduled-tasks",
    shellMode: "scroll",
    widthMode: "wide",
    stateVariants: ["loading", "ready", "error", "empty", "filteredEmpty"],
    testId: "route-scheduled-tasks-list",
  },
  {
    archetype: "editor",
    breadcrumb: {
      parent: { href: "/scheduled-tasks", title: "Scheduled Tasks" },
      title: "New Scheduled Task",
    },
    nav: {
      group: AGENT_PLATFORM_NAV_GROUP,
      iconName: "ClipboardList",
      label: "Scheduled Tasks",
      path: "/scheduled-tasks",
      sidebar: false,
      testId: "nav-scheduled-tasks",
    },
    owner: { kind: "platform" },
    pattern: "/scheduled-tasks/new",
    shellMode: "fullHeight",
    widthMode: "full",
    stateVariants: ["creating", "saving", "validating", "error"],
    testId: "route-scheduled-task-new",
  },
  {
    archetype: "console",
    breadcrumb: {
      parent: { href: "/scheduled-tasks", title: "Scheduled Tasks" },
      title: "Scheduled Task Detail",
    },
    nav: {
      group: AGENT_PLATFORM_NAV_GROUP,
      iconName: "ClipboardList",
      label: "Scheduled Tasks",
      path: "/scheduled-tasks",
      sidebar: false,
      testId: "nav-scheduled-tasks",
    },
    owner: { kind: "platform" },
    pattern: "/scheduled-tasks/:scheduleId",
    shellMode: "fullHeight",
    widthMode: "full",
    stateVariants: [
      "loading",
      "ready",
      "editing",
      "saving",
      "validating",
      "error",
      "notFound",
      "polling",
    ],
    testId: "route-scheduled-task-detail",
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
    widthMode: "wide",
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
    widthMode: "full",
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
  widthMode: "wide",
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

export function requireRouteMetadataByPattern(
  pattern: RoutePattern,
): RouteMetadata {
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
  return getSidebarRouteMetadata().find(
    (metadata) => metadata.nav.path === path,
  );
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
