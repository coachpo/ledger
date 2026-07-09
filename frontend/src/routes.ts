import type { ComponentType } from "react";
import { createBrowserRouter } from "react-router";

import {
  Layout,
  type RootRouteHandle,
  type RouteHandle,
  type RouteNavGroup,
} from "./components/layout";
import { RouteErrorPage } from "./pages/route-error";

const AGENT_PLATFORM_NAV_GROUP = "Agent Platform" as const;
const FINANCE_WORKSPACE_EXTENSION_KEY = "signaldeck.finance" as const;
const FINANCE_WORKSPACE_NAV_GROUP = "Finance Workspace" as const;

type AppRouteDefinition = {
  handle: RouteHandle;
  index?: boolean;
  lazy: () => Promise<{ Component: ComponentType }>;
  path?: string;
};

const sidebarNavGroupOrder = [
  AGENT_PLATFORM_NAV_GROUP,
  FINANCE_WORKSPACE_NAV_GROUP,
  "System",
] as const satisfies readonly RouteNavGroup[];

const financeWorkspaceOwner = {
  extensionKey: FINANCE_WORKSPACE_EXTENSION_KEY,
  extensionLabel: FINANCE_WORKSPACE_NAV_GROUP,
  kind: "extension",
} as const satisfies RouteHandle["owner"];

const appRouteChildren: AppRouteDefinition[] = [
  {
    path: "templates",
    handle: {
      archetype: "inventory",
      breadcrumb: { title: "Templates" },
      nav: {
        group: FINANCE_WORKSPACE_NAV_GROUP,
        iconName: "FileText",
        label: "Templates",
        path: "/templates",
        sidebar: true,
        testId: "nav-templates",
      },
      owner: financeWorkspaceOwner,
      pattern: "/templates",
      shellMode: "scroll",
      stateVariants: ["loading", "ready", "error", "empty", "filteredEmpty"],
      testId: "route-templates-list",
      widthMode: "wide",
    },
    lazy: async () => ({
      Component: (await import("@/pages/templates/list")).TemplateListPage,
    }),
  },
  {
    path: "templates/new",
    handle: {
      archetype: "editor",
      breadcrumb: {
        parent: { href: "/templates", title: "Templates" },
        title: "New Template",
      },
      nav: {
        group: FINANCE_WORKSPACE_NAV_GROUP,
        iconName: "FileText",
        label: "Templates",
        path: "/templates",
        sidebar: false,
        testId: "nav-templates",
      },
      owner: financeWorkspaceOwner,
      pattern: "/templates/new",
      shellMode: "fullHeight",
      stateVariants: ["creating", "saving", "error"],
      testId: "route-template-new",
      widthMode: "full",
    },
    lazy: async () => ({
      Component: (await import("@/pages/templates/editor")).TemplateEditorPage,
    }),
  },
  {
    path: "templates/:templateId/edit",
    handle: {
      archetype: "editor",
      breadcrumb: {
        parent: { href: "/templates", title: "Templates" },
        title: "Edit Template",
      },
      nav: {
        group: FINANCE_WORKSPACE_NAV_GROUP,
        iconName: "FileText",
        label: "Templates",
        path: "/templates",
        sidebar: false,
        testId: "nav-templates",
      },
      owner: financeWorkspaceOwner,
      pattern: "/templates/:templateId/edit",
      shellMode: "fullHeight",
      stateVariants: ["loading", "editing", "saving", "error", "notFound"],
      testId: "route-template-edit",
      widthMode: "full",
    },
    lazy: async () => ({
      Component: (await import("@/pages/templates/editor")).TemplateEditorPage,
    }),
  },
  {
    path: "reports",
    handle: {
      archetype: "inventory",
      breadcrumb: { title: "Reports" },
      nav: {
        group: FINANCE_WORKSPACE_NAV_GROUP,
        iconName: "ClipboardList",
        label: "Reports",
        path: "/reports",
        sidebar: true,
        testId: "nav-reports",
      },
      owner: financeWorkspaceOwner,
      pattern: "/reports",
      shellMode: "scroll",
      stateVariants: ["loading", "ready", "error", "empty", "filteredEmpty"],
      testId: "route-reports-list",
      widthMode: "wide",
    },
    lazy: async () => ({
      Component: (await import("@/pages/reports/list")).ReportListPage,
    }),
  },
  {
    path: "reports/:slug",
    handle: {
      archetype: "detail",
      breadcrumb: {
        parent: { href: "/reports", title: "Reports" },
        title: "Report Detail",
      },
      nav: {
        group: FINANCE_WORKSPACE_NAV_GROUP,
        iconName: "ClipboardList",
        label: "Reports",
        path: "/reports",
        sidebar: false,
        testId: "nav-reports",
      },
      owner: financeWorkspaceOwner,
      pattern: "/reports/:slug",
      shellMode: "scroll",
      stateVariants: ["loading", "editing", "saving", "error", "notFound"],
      testId: "route-report-detail",
      widthMode: "wide",
    },
    lazy: async () => ({
      Component: (await import("@/pages/reports/detail")).ReportDetailPage,
    }),
  },
  {
    index: true,
    handle: {
      archetype: "dashboard",
      breadcrumb: { title: "Dashboard" },
      nav: {
        group: AGENT_PLATFORM_NAV_GROUP,
        iconName: "LayoutDashboard",
        label: "Dashboard",
        path: "/",
        sidebar: true,
        testId: "nav-dashboard",
      },
      owner: { kind: "platform" },
      pattern: "/",
      shellMode: "scroll",
      stateVariants: ["loading", "ready", "error"],
      testId: "route-dashboard",
      widthMode: "wide",
    },
    lazy: async () => ({
      Component: (await import("./pages/dashboard")).Dashboard,
    }),
  },
  {
    path: "workflow-packages",
    handle: {
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
      widthMode: "wide",
    },
    lazy: async () => ({
      Component: (await import("./pages/workflow-packages/list"))
        .WorkflowPackagesListPage,
    }),
  },
  {
    path: "workflow-packages/import",
    handle: {
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
      widthMode: "full",
    },
    lazy: async () => ({
      Component: (await import("./pages/workflow-packages/import-page"))
        .WorkflowPackageImportPage,
    }),
  },
  {
    path: "workflow-packages/new",
    handle: {
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
      widthMode: "full",
    },
    lazy: async () => ({
      Component: (await import("./pages/workflow-packages/editor"))
        .WorkflowPackageEditorPage,
    }),
  },
  {
    path: "workflow-packages/:packageId",
    handle: {
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
      widthMode: "full",
    },
    lazy: async () => ({
      Component: (await import("./pages/workflow-packages/editor"))
        .WorkflowPackageEditorPage,
    }),
  },
  {
    path: "workflow-packages/:packageId/run",
    handle: {
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
      widthMode: "full",
    },
    lazy: async () => ({
      Component: (await import("./pages/workflow-packages/launch"))
        .WorkflowPackageLaunchPage,
    }),
  },
  {
    path: "model-connections",
    handle: {
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
      widthMode: "wide",
    },
    lazy: async () => ({
      Component: (await import("./pages/model-connections/list"))
        .ModelConnectionsListPage,
    }),
  },
  {
    path: "model-connections/new",
    handle: {
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
      widthMode: "full",
    },
    lazy: async () => ({
      Component: (await import("./pages/model-connections/editor"))
        .ModelConnectionsEditorPage,
    }),
  },
  {
    path: "model-connections/:modelConnectionId/edit",
    handle: {
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
      widthMode: "full",
    },
    lazy: async () => ({
      Component: (await import("./pages/model-connections/editor"))
        .ModelConnectionsEditorPage,
    }),
  },
  {
    path: "scheduled-tasks",
    handle: {
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
      stateVariants: ["loading", "ready", "error", "empty", "filteredEmpty"],
      testId: "route-scheduled-tasks-list",
      widthMode: "wide",
    },
    lazy: async () => ({
      Component: (await import("./pages/scheduled-tasks/list"))
        .ScheduledTasksListPage,
    }),
  },
  {
    path: "scheduled-tasks/new",
    handle: {
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
      stateVariants: ["creating", "saving", "validating", "error"],
      testId: "route-scheduled-task-new",
      widthMode: "full",
    },
    lazy: async () => ({
      Component: (await import("./pages/scheduled-tasks/editor"))
        .ScheduledTaskEditorPage,
    }),
  },
  {
    path: "scheduled-tasks/:scheduleId",
    handle: {
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
      widthMode: "full",
    },
    lazy: async () => ({
      Component: (await import("./pages/scheduled-tasks/detail"))
        .ScheduledTaskDetailPage,
    }),
  },
  {
    path: "runs",
    handle: {
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
      widthMode: "wide",
    },
    lazy: async () => ({
      Component: (await import("./pages/runs/list")).RunsListPage,
    }),
  },
  {
    path: "runs/:runId",
    handle: {
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
      widthMode: "full",
    },
    lazy: async () => ({
      Component: (await import("./pages/runs/detail")).RunsDetailPage,
    }),
  },
  {
    path: "*",
    handle: {
      archetype: "unknown",
      breadcrumb: { title: "Page not found" },
      nav: {
        group: "System",
        iconName: "Puzzle",
        label: "Unknown Route",
        sidebar: false,
        testId: "route-unknown",
      },
      owner: { kind: "unknown" },
      pattern: "*",
      shellMode: "scroll",
      stateVariants: ["notFound"],
      testId: "route-unknown",
      widthMode: "wide",
    },
    lazy: async () => ({
      Component: (await import("./pages/not-found")).NotFoundPage,
    }),
  },
];

function buildSidebarGroups(routes: readonly AppRouteDefinition[]) {
  return sidebarNavGroupOrder
    .map((label) => ({
      items: routes
        .map((route) => route.handle)
        .filter(
          (handle) => handle.nav.sidebar && handle.nav.group === label,
        ),
      label,
    }))
    .filter((group) => group.items.length > 0);
}

const rootRouteHandle: RootRouteHandle = {
  sidebarGroups: buildSidebarGroups(appRouteChildren),
};

export const router = createBrowserRouter([
  {
    path: "/",
    Component: Layout,
    ErrorBoundary: RouteErrorPage,
    handle: rootRouteHandle,
    children: appRouteChildren,
  },
]);
