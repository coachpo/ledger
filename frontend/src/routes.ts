import { createBrowserRouter } from "react-router";
import { Layout } from "./components/layout";
import { BacktestConfigPage } from "./pages/backtests/config";
import { BacktestDetailPage } from "./pages/backtests/detail";
import { BacktestListPage } from "./pages/backtests/list";
import { Dashboard } from "./pages/dashboard";
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
    ],
  },
]);
