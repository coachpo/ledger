import type { ComponentType, ReactNode } from "react";
import { Link } from "react-router";
import {
  AlertCircle,
  Briefcase,
  ClipboardList,
  FileText,
  LayoutDashboard,
  Link2,
  PlayCircle,
  RefreshCw,
  Workflow,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useExtension } from "@/hooks/use-extensions";
import type { ExtensionListRead, ExtensionRead } from "@/lib/types/extension";
import type { ToolCatalogItemRead } from "@/lib/types/tool";
import { Dashboard } from "@/pages/dashboard";
import { PortfolioDetailPage } from "@/pages/portfolios/detail";
import { PortfolioListPage } from "@/pages/portfolios/list";
import { ReportDetailPage } from "@/pages/reports/detail";
import { ReportListPage } from "@/pages/reports/list";
import { TemplateEditorPage } from "@/pages/templates/editor";
import { TemplateListPage } from "@/pages/templates/list";

import {
  financeWorkspaceFrontendExtension,
  FINANCE_WORKSPACE_EXTENSION_KEY,
  FINANCE_WORKSPACE_LABEL,
} from "./ledger-finance";
import type { FrontendNavContribution } from "./types";

export type NavItem = {
  icon: LucideIcon;
  label: string;
  testId: string;
  to: string;
};

type ExtensionRouteDefinition = {
  Component: ComponentType;
  index?: boolean;
  path?: string;
};
const financeRouteComponents: Record<string, ComponentType> = {
  "@/pages/dashboard#Dashboard": Dashboard,
  "@/pages/portfolios/list#PortfolioListPage": PortfolioListPage,
  "@/pages/portfolios/detail#PortfolioDetailPage": PortfolioDetailPage,
  "@/pages/templates/list#TemplateListPage": TemplateListPage,
  "@/pages/templates/editor#TemplateEditorPage": TemplateEditorPage,
  "@/pages/reports/list#ReportListPage": ReportListPage,
  "@/pages/reports/detail#ReportDetailPage": ReportDetailPage,
};

const navIconByName: Record<string, LucideIcon> = {
  Briefcase,
  ClipboardList,
  FileText,
  LayoutDashboard,
  Link2,
  PlayCircle,
  Workflow,
};

export const coreNavItems: readonly NavItem[] = [
  { icon: Link2, label: "Model Connections", testId: "nav-model-connections", to: "/model-connections" },
  { icon: Workflow, label: "Workflow Packages", testId: "nav-workflow-packages", to: "/workflow-packages" },
  { icon: PlayCircle, label: "Runs", testId: "nav-runs", to: "/runs" },
];
function extensionStateFromList(
  extensionList: ExtensionListRead | undefined,
  extensionKey: string,
): ExtensionRead | undefined {
  return extensionList?.items.find((extension) => extension.key === extensionKey);
}

export function isFrontendExtensionEnabled(
  extensionList: ExtensionListRead | undefined,
  extensionKey: string,
): boolean {
  return extensionStateFromList(extensionList, extensionKey)?.enabled === true;
}

function navItemFromContribution(contribution: FrontendNavContribution): NavItem {
  const icon = navIconByName[contribution.iconName];

  if (!icon) {
    throw new Error(`Unknown extension nav icon: ${contribution.iconName}`);
  }

  return {
    icon,
    label: contribution.label,
    testId: contribution.testId,
    to: contribution.to,
  };
}
export function assembleNavItems(extensionList: ExtensionListRead | undefined): NavItem[] {
  const extensionNavItems = isFrontendExtensionEnabled(
    extensionList,
    FINANCE_WORKSPACE_EXTENSION_KEY,
  )
    ? financeWorkspaceFrontendExtension.navContributions.map(navItemFromContribution)
    : [];

  return [...extensionNavItems, ...coreNavItems];
}

export function enabledFinanceRoutePaths(extensionList: ExtensionListRead | undefined): string[] {
  if (!isFrontendExtensionEnabled(extensionList, FINANCE_WORKSPACE_EXTENSION_KEY)) {
    return [];
  }

  return financeWorkspaceFrontendExtension.routeContributions.map(
    (contribution) => contribution.path,
  );
}

function DisabledShell({ children, testId }: { children: ReactNode; testId: string }) {
  return (
    <div className="flex min-h-full items-center justify-center p-4" data-testid={testId}>
      <Card className="w-full max-w-2xl border-border/70 bg-card/90 shadow-sm backdrop-blur">
        {children}
      </Card>
    </div>
  );
}

function ExtensionStateUnavailable({ onRetry }: { onRetry: () => void }) {
  return (
    <DisabledShell testId="extension-state-unavailable">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <AlertCircle className="size-5 text-destructive" />
          Extension state unavailable
        </CardTitle>
        <CardDescription>
          Ledger could not load backend extension state, so extension-owned routes are paused.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Button size="sm" type="button" variant="outline" onClick={onRetry}>
          <RefreshCw data-icon="inline-start" />
          Retry extension state
        </Button>
      </CardContent>
    </DisabledShell>
  );
}
function ExtensionDisabled({ extension }: { extension: ExtensionRead }) {
  return (
    <DisabledShell testId="extension-disabled-state">
      <CardHeader>
        <CardTitle>{extension.label} disabled</CardTitle>
        <CardDescription>
          This route is contributed by {extension.key} and is hidden while the backend marks the extension disabled.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {extension.disabledReason ? (
          <p className="rounded-lg border bg-muted/40 p-3 text-sm text-muted-foreground">
            {extension.disabledReason}
          </p>
        ) : null}
        <Button asChild size="sm" variant="outline">
          <Link to="/workflow-packages">Open core workflow packages</Link>
        </Button>
      </CardContent>
    </DisabledShell>
  );
}

function ExtensionLoading() {
  return (
    <DisabledShell testId="extension-state-loading">
      <CardHeader>
        <CardTitle>Checking {FINANCE_WORKSPACE_LABEL}</CardTitle>
        <CardDescription>
          Loading backend extension state before opening this workspace route.
        </CardDescription>
      </CardHeader>
    </DisabledShell>
  );
}

export function FinanceWorkspaceRouteGate({ children }: { children: ReactNode }) {
  const extensionQuery = useExtension(FINANCE_WORKSPACE_EXTENSION_KEY);

  if (extensionQuery.isPending) {
    return <ExtensionLoading />;
  }

  if (extensionQuery.isError || !extensionQuery.data) {
    return <ExtensionStateUnavailable onRetry={() => void extensionQuery.refetch()} />;
  }

  if (!extensionQuery.data.enabled) {
    return <ExtensionDisabled extension={extensionQuery.data} />;
  }

  return <>{children}</>;
}
function withFinanceWorkspaceGate(Component: ComponentType): ComponentType {
  return function FinanceWorkspaceRoute() {
    return (
      <FinanceWorkspaceRouteGate>
        <Component />
      </FinanceWorkspaceRouteGate>
    );
  };
}

export function assembleFinanceWorkspaceRoutes(): ExtensionRouteDefinition[] {
  return financeWorkspaceFrontendExtension.routeContributions.map((contribution) => {
    const Component = financeRouteComponents[contribution.componentModule];

    if (!Component) {
      throw new Error(`Unknown extension route component: ${contribution.componentModule}`);
    }

    const GuardedComponent = withFinanceWorkspaceGate(Component);

    return contribution.path === "/"
      ? { index: true, Component: GuardedComponent }
      : { path: contribution.path.replace(/^\//, ""), Component: GuardedComponent };
  });
}
export function filterToolsForExtensionState(
  tools: readonly ToolCatalogItemRead[],
  extensionList: ExtensionListRead | undefined,
): ToolCatalogItemRead[] {
  const financeToolContribution = financeWorkspaceFrontendExtension.toolAuthoringDiscovery[0];

  if (
    !financeToolContribution ||
    isFrontendExtensionEnabled(extensionList, FINANCE_WORKSPACE_EXTENSION_KEY)
  ) {
    return [...tools];
  }

  return tools.filter((tool) => !tool.key.startsWith(financeToolContribution.toolKeyPrefix));
}
