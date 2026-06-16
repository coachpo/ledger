import type { ComponentType } from "react";
import { createBrowserRouter } from "react-router";

import { Layout } from "./components/layout";
import { assembleFinanceWorkspaceRoutes } from "./extensions/runtime-helpers";
import { ExtensionsListPage } from "./pages/extensions/list";
import { MemoryListPage } from "./pages/memory/list";
import { ModelConnectionsEditorPage } from "./pages/model-connections/editor";
import { ModelConnectionsListPage } from "./pages/model-connections/list";
import { NotFoundPage } from "./pages/not-found";
import { RouteErrorPage } from "./pages/route-error";
import { RunsDetailPage } from "./pages/runs/detail";
import { RunsListPage } from "./pages/runs/list";
import { ScheduledTaskDetailPage } from "./pages/scheduled-tasks/detail";
import { ScheduledTaskEditorPage } from "./pages/scheduled-tasks/editor";
import { ScheduledTasksListPage } from "./pages/scheduled-tasks/list";
import { WorkflowPackageEditorPage } from "./pages/workflow-packages/editor";
import { WorkflowPackageImportPage } from "./pages/workflow-packages/import-page";
import { WorkflowPackageLaunchPage } from "./pages/workflow-packages/launch";
import { WorkflowPackagesListPage } from "./pages/workflow-packages/list";
import { assertRouteMetadataCoverage } from "./routes.metadata";

type AppRouteDefinition = {
  Component: ComponentType;
  index?: boolean;
  path?: string;
};

const financeWorkspaceRoutes: AppRouteDefinition[] =
  assembleFinanceWorkspaceRoutes();
const platformRoutes: AppRouteDefinition[] = [
  { path: "extensions", Component: ExtensionsListPage },
  { path: "workflow-packages", Component: WorkflowPackagesListPage },
  { path: "workflow-packages/import", Component: WorkflowPackageImportPage },
  { path: "workflow-packages/new", Component: WorkflowPackageEditorPage },
  {
    path: "workflow-packages/:packageId",
    Component: WorkflowPackageEditorPage,
  },
  {
    path: "workflow-packages/:packageId/run",
    Component: WorkflowPackageLaunchPage,
  },
  { path: "model-connections", Component: ModelConnectionsListPage },
  { path: "model-connections/new", Component: ModelConnectionsEditorPage },
  {
    path: "model-connections/:modelConnectionId/edit",
    Component: ModelConnectionsEditorPage,
  },
  { path: "memory", Component: MemoryListPage },
  { path: "scheduled-tasks", Component: ScheduledTasksListPage },
  { path: "scheduled-tasks/new", Component: ScheduledTaskEditorPage },
  { path: "scheduled-tasks/:scheduleId", Component: ScheduledTaskDetailPage },
  { path: "runs", Component: RunsListPage },
  { path: "runs/:runId", Component: RunsDetailPage },
];

const appRouteChildren: AppRouteDefinition[] = [
  ...financeWorkspaceRoutes,
  ...platformRoutes,
  { path: "*", Component: NotFoundPage },
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
