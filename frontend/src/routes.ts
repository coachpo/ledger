import { createBrowserRouter } from "react-router";
import { Layout } from "./components/layout";
import { BacktestConfigPage } from "./pages/backtests/config";
import { BacktestDetailPage } from "./pages/backtests/detail";
import { BacktestListPage } from "./pages/backtests/list";
import { Dashboard } from "./pages/dashboard";
import { OrchestrationIndexPage } from "./pages/orchestration/index";
import { OrchestrationCharacterEditorPage } from "./pages/orchestration/characters/editor";
import { OrchestrationCharactersListPage } from "./pages/orchestration/characters/list";
import { OrchestrationRoleEditorPage } from "./pages/orchestration/roles/editor";
import { OrchestrationRolesListPage } from "./pages/orchestration/roles/list";
import { PortfolioDetailPage } from "./pages/portfolios/detail";
import { PortfolioListPage } from "./pages/portfolios/list";
import { ReportDetailPage } from "./pages/reports/detail";
import { ReportListPage } from "./pages/reports/list";
import { TemplateEditorPage } from "./pages/templates/editor";
import { TemplateListPage } from "./pages/templates/list";

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
      { path: "backtests", Component: BacktestListPage },
      { path: "backtests/new", Component: BacktestConfigPage },
      { path: "backtests/:backtestId", Component: BacktestDetailPage },
      { path: "orchestration", Component: OrchestrationIndexPage },
      { path: "orchestration/roles", Component: OrchestrationRolesListPage },
      { path: "orchestration/roles/new", Component: OrchestrationRoleEditorPage },
      { path: "orchestration/roles/:roleId/edit", Component: OrchestrationRoleEditorPage },
      { path: "orchestration/characters", Component: OrchestrationCharactersListPage },
      { path: "orchestration/characters/new", Component: OrchestrationCharacterEditorPage },
      {
        path: "orchestration/characters/:characterId/edit",
        Component: OrchestrationCharacterEditorPage,
      },
    ],
  },
]);
