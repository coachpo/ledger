import { createBrowserRouter } from "react-router";

import { Layout } from "./components/layout";
import { assembleFinanceWorkspaceRoutes } from "./extensions/runtime";
import { ExtensionsListPage } from "./pages/extensions/list";
import { ModelConnectionsEditorPage } from "./pages/model-connections/editor";
import { ModelConnectionsListPage } from "./pages/model-connections/list";
import { RunsDetailPage } from "./pages/runs/detail";
import { RunsListPage } from "./pages/runs/list";
import { WorkflowPackageEditorPage } from "./pages/workflow-packages/editor";
import { WorkflowPackagesListPage } from "./pages/workflow-packages/list";

const financeWorkspaceRoutes = assembleFinanceWorkspaceRoutes();

export const router = createBrowserRouter([
  {
    path: "/",
    Component: Layout,
    children: [
      ...financeWorkspaceRoutes,
      { path: "extensions", Component: ExtensionsListPage },
      { path: "workflow-packages", Component: WorkflowPackagesListPage },
      { path: "workflow-packages/new", Component: WorkflowPackageEditorPage },
      { path: "workflow-packages/:packageId", Component: WorkflowPackageEditorPage },
      { path: "workflow-packages/:packageId/run", Component: WorkflowPackageEditorPage },
      { path: "model-connections", Component: ModelConnectionsListPage },
      { path: "model-connections/new", Component: ModelConnectionsEditorPage },
      {
        path: "model-connections/:modelConnectionId/edit",
        Component: ModelConnectionsEditorPage,
      },
      { path: "runs", Component: RunsListPage },
      { path: "runs/:runId", Component: RunsDetailPage },
    ],
  },
]);
