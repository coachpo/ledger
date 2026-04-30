import { createBrowserRouter } from "react-router";

import { Layout } from "./components/layout";
import { Dashboard } from "./pages/dashboard";
import { AgentsEditorPage } from "./pages/agents/editor";
import { AgentsListPage } from "./pages/agents/list";
import { CapabilitiesEditorPage } from "./pages/capabilities/editor";
import {
  LegacySkillsEditRedirect,
  LegacySkillsListRedirect,
  LegacySkillsNewRedirect,
} from "./pages/capabilities/legacy-redirect";
import { CapabilitiesListPage } from "./pages/capabilities/list";
import { McpServersEditorPage } from "./pages/mcp-servers/editor";
import { McpServersListPage } from "./pages/mcp-servers/list";
import { ModelConnectionsEditorPage } from "./pages/model-connections/editor";
import { ModelConnectionsListPage } from "./pages/model-connections/list";
import { OutputSchemasEditorPage } from "./pages/output-schemas/editor";
import { OutputSchemasListPage } from "./pages/output-schemas/list";
import { PortfolioDetailPage } from "./pages/portfolios/detail";
import { PortfolioListPage } from "./pages/portfolios/list";
import { ReportDetailPage } from "./pages/reports/detail";
import { ReportListPage } from "./pages/reports/list";
import { RunsDetailPage } from "./pages/runs/detail";
import { RunsListPage } from "./pages/runs/list";
import { TemplateEditorPage } from "./pages/templates/editor";
import { TemplateListPage } from "./pages/templates/list";
import { WorkflowsEditorPage } from "./pages/workflows/editor";
import { WorkflowsListPage } from "./pages/workflows/list";

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
      { path: "agents", Component: AgentsListPage },
      { path: "agents/new", Component: AgentsEditorPage },
      { path: "agents/:agentId/edit", Component: AgentsEditorPage },
      { path: "capabilities", Component: CapabilitiesListPage },
      { path: "capabilities/new", Component: CapabilitiesEditorPage },
      { path: "capabilities/:capabilityId/edit", Component: CapabilitiesEditorPage },
      { path: "skills", Component: LegacySkillsListRedirect },
      { path: "skills/new", Component: LegacySkillsNewRedirect },
      { path: "skills/:skillId/edit", Component: LegacySkillsEditRedirect },
      { path: "mcp-servers", Component: McpServersListPage },
      { path: "mcp-servers/new", Component: McpServersEditorPage },
      { path: "mcp-servers/:serverId/edit", Component: McpServersEditorPage },
      { path: "model-connections", Component: ModelConnectionsListPage },
      { path: "model-connections/new", Component: ModelConnectionsEditorPage },
      {
        path: "model-connections/:modelConnectionId/edit",
        Component: ModelConnectionsEditorPage,
      },
      { path: "output-schemas", Component: OutputSchemasListPage },
      { path: "output-schemas/new", Component: OutputSchemasEditorPage },
      { path: "output-schemas/:schemaId/edit", Component: OutputSchemasEditorPage },
      { path: "workflows", Component: WorkflowsListPage },
      { path: "workflows/new", Component: WorkflowsEditorPage },
      { path: "workflows/:workflowId/edit", Component: WorkflowsEditorPage },
      { path: "runs", Component: RunsListPage },
      { path: "runs/:runId", Component: RunsDetailPage },
    ],
  },
]);
