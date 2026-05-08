import { createBrowserRouter } from "react-router";

import { Layout } from "./components/layout";
import { Dashboard } from "./pages/dashboard";
import { ModelConnectionsEditorPage } from "./pages/model-connections/editor";
import { ModelConnectionsListPage } from "./pages/model-connections/list";
import { PortfolioDetailPage } from "./pages/portfolios/detail";
import { PortfolioListPage } from "./pages/portfolios/list";
import { ReportDetailPage } from "./pages/reports/detail";
import { ReportListPage } from "./pages/reports/list";
import { RunsDetailPage } from "./pages/runs/detail";
import { RunsListPage } from "./pages/runs/list";
import { TemplateEditorPage } from "./pages/templates/editor";
import { TemplateListPage } from "./pages/templates/list";
import { WorkflowPackageEditorPage } from "./pages/workflow-packages/editor";
import { WorkflowPackagesListPage } from "./pages/workflow-packages/list";

export const router = createBrowserRouter([
  {
    path: "/",
    Component: Layout,
    children: [
      { index: true, Component: Dashboard },
      { path: "portfolios", Component: PortfolioListPage },
      { path: "portfolios/:portfolioId", Component: PortfolioDetailPage },
      { path: "templates", Component: TemplateListPage },
      { path: "templates/new", Component: TemplateEditorPage },
      { path: "templates/:templateId/edit", Component: TemplateEditorPage },
      { path: "reports", Component: ReportListPage },
      { path: "reports/:slug", Component: ReportDetailPage },
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
