import type { ComponentType } from "react";
import { createBrowserRouter } from "react-router";

import { Layout } from "./components/layout";
import { assembleFinanceWorkspaceRoutes } from "./extensions/runtime-helpers";
import { RouteErrorPage } from "./pages/route-error";
import { assertRouteMetadataCoverage } from "./routes.metadata";

type AppRouteDefinition = {
  index?: boolean;
  lazy: () => Promise<{ Component: ComponentType }>;
  path?: string;
};

const financeWorkspaceRoutes: AppRouteDefinition[] =
  assembleFinanceWorkspaceRoutes();
const platformRoutes: AppRouteDefinition[] = [
  {
    index: true,
    lazy: async () => ({
      Component: (await import("./pages/dashboard")).Dashboard,
    }),
  },
  {
    path: "extensions",
    lazy: async () => ({
      Component: (await import("./pages/extensions/list")).ExtensionsListPage,
    }),
  },
  {
    path: "workflow-packages",
    lazy: async () => ({
      Component: (await import("./pages/workflow-packages/list"))
        .WorkflowPackagesListPage,
    }),
  },
  {
    path: "workflow-packages/import",
    lazy: async () => ({
      Component: (await import("./pages/workflow-packages/import-page"))
        .WorkflowPackageImportPage,
    }),
  },
  {
    path: "workflow-packages/new",
    lazy: async () => ({
      Component: (await import("./pages/workflow-packages/editor"))
        .WorkflowPackageEditorPage,
    }),
  },
  {
    path: "workflow-packages/:packageId",
    lazy: async () => ({
      Component: (await import("./pages/workflow-packages/editor"))
        .WorkflowPackageEditorPage,
    }),
  },
  {
    path: "workflow-packages/:packageId/run",
    lazy: async () => ({
      Component: (await import("./pages/workflow-packages/launch"))
        .WorkflowPackageLaunchPage,
    }),
  },
  {
    path: "model-connections",
    lazy: async () => ({
      Component: (await import("./pages/model-connections/list"))
        .ModelConnectionsListPage,
    }),
  },
  {
    path: "model-connections/new",
    lazy: async () => ({
      Component: (await import("./pages/model-connections/editor"))
        .ModelConnectionsEditorPage,
    }),
  },
  {
    path: "model-connections/:modelConnectionId/edit",
    lazy: async () => ({
      Component: (await import("./pages/model-connections/editor"))
        .ModelConnectionsEditorPage,
    }),
  },
  {
    path: "scheduled-tasks",
    lazy: async () => ({
      Component: (await import("./pages/scheduled-tasks/list"))
        .ScheduledTasksListPage,
    }),
  },
  {
    path: "scheduled-tasks/new",
    lazy: async () => ({
      Component: (await import("./pages/scheduled-tasks/editor"))
        .ScheduledTaskEditorPage,
    }),
  },
  {
    path: "scheduled-tasks/:scheduleId",
    lazy: async () => ({
      Component: (await import("./pages/scheduled-tasks/detail"))
        .ScheduledTaskDetailPage,
    }),
  },
  {
    path: "runs",
    lazy: async () => ({
      Component: (await import("./pages/runs/list")).RunsListPage,
    }),
  },
  {
    path: "runs/:runId",
    lazy: async () => ({
      Component: (await import("./pages/runs/detail")).RunsDetailPage,
    }),
  },
  {
    path: "*",
    lazy: async () => ({
      Component: (await import("./pages/not-found")).NotFoundPage,
    }),
  },
];

const appRouteChildren: AppRouteDefinition[] = [
  ...financeWorkspaceRoutes,
  ...platformRoutes,
];

assertRouteMetadataCoverage(appRouteChildren);

export const router = createBrowserRouter([
  {
    path: "/",
    Component: Layout,
    ErrorBoundary: RouteErrorPage,
    children: appRouteChildren,
  },
]);
