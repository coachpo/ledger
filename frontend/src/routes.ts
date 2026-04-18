import { createBrowserRouter } from "react-router";
import { Layout } from "./components/layout";
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
import { StudioAgentEditorPage } from "./pages/studio/agents/editor";
import { StudioAgentsListPage } from "./pages/studio/agents/list";
import { StudioCapabilityEditorPage } from "./pages/studio/capabilities/editor";
import { StudioCapabilitiesListPage } from "./pages/studio/capabilities/list";
import { StudioIndexPage } from "./pages/studio/index";
import { StudioPersonaEditorPage } from "./pages/studio/personas/editor";
import { StudioPersonasListPage } from "./pages/studio/personas/list";
import { StudioRunDetailPage } from "./pages/studio/runs/detail";
import { StudioWorkflowEditorPage } from "./pages/studio/workflows/editor";
import { StudioWorkflowsListPage } from "./pages/studio/workflows/list";
import { TryoutPage } from "./pages/tryout/index";
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
      { path: "tryout", Component: TryoutPage },
      { path: "studio", Component: StudioIndexPage },
      { path: "studio/agents", Component: StudioAgentsListPage },
      { path: "studio/agents/new", Component: StudioAgentEditorPage },
      { path: "studio/agents/:agentKey/edit", Component: StudioAgentEditorPage },
      { path: "studio/workflows", Component: StudioWorkflowsListPage },
      { path: "studio/workflows/new", Component: StudioWorkflowEditorPage },
      { path: "studio/workflows/:workflowKey/edit", Component: StudioWorkflowEditorPage },
      { path: "studio/personas", Component: StudioPersonasListPage },
      { path: "studio/personas/new", Component: StudioPersonaEditorPage },
      { path: "studio/personas/:personaKey/edit", Component: StudioPersonaEditorPage },
      { path: "studio/capabilities", Component: StudioCapabilitiesListPage },
      { path: "studio/capabilities/new", Component: StudioCapabilityEditorPage },
      { path: "studio/capabilities/:capabilityKey/edit", Component: StudioCapabilityEditorPage },
      { path: "studio/runs/:runId", Component: StudioRunDetailPage },
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
