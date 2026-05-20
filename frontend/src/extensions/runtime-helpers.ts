import { createElement, type ComponentType } from "react";
import {
  Briefcase,
  ClipboardList,
  FileText,
  LayoutDashboard,
  Link2,
  PlayCircle,
  Puzzle,
  Workflow,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { ExtensionListRead, ExtensionRead } from "@/lib/types/extension";
import type { ToolCatalogItemRead } from "@/lib/types/tool";
import { Dashboard } from "@/pages/dashboard";
import { PortfolioDetailPage } from "@/pages/portfolios/detail";
import { PortfolioListPage } from "@/pages/portfolios/list";
import { ReportDetailPage } from "@/pages/reports/detail";
import { ReportListPage } from "@/pages/reports/list";
import { TemplateEditorPage } from "@/pages/templates/editor";
import { TemplateListPage } from "@/pages/templates/list";

import { FinanceWorkspaceRouteGate } from "./runtime";
import {
  financeWorkspaceFrontendExtension,
  FINANCE_WORKSPACE_LABEL,
} from "./signaldeck-finance";
import type {
  FrontendExtensionGateTag,
  FrontendNavContribution,
} from "./types";

export type NavItem = {
  icon: LucideIcon;
  label: string;
  testId: string;
  to: string;
};

export type NavGroup = {
  items: readonly NavItem[];
  label: string;
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
  Puzzle,
  Workflow,
};

export const agentPlatformNavItems: readonly NavItem[] = [
  {
    icon: Workflow,
    label: "Workflow Packages",
    testId: "nav-workflow-packages",
    to: "/workflow-packages",
  },
  {
    icon: Link2,
    label: "Model Connections",
    testId: "nav-model-connections",
    to: "/model-connections",
  },
  { icon: PlayCircle, label: "Runs", testId: "nav-runs", to: "/runs" },
];

export const systemNavItems: readonly NavItem[] = [
  {
    icon: Puzzle,
    label: "Extensions",
    testId: "nav-extensions",
    to: "/extensions",
  },
];

export const coreNavItems: readonly NavItem[] = [
  ...agentPlatformNavItems,
  ...systemNavItems,
];

function extensionStateFromList(
  extensionList: ExtensionListRead | undefined,
  extensionKey: string,
): ExtensionRead | undefined {
  return extensionList?.items.find(
    (extension) => extension.key === extensionKey,
  );
}

export function isFrontendExtensionEnabled(
  extensionList: ExtensionListRead | undefined,
  extensionKey: string,
): boolean {
  return extensionStateFromList(extensionList, extensionKey)?.enabled === true;
}

function isGateTagEnabled(
  extensionList: ExtensionListRead | undefined,
  gateTag: FrontendExtensionGateTag,
): boolean {
  return isFrontendExtensionEnabled(
    extensionList,
    gateTag.requiredExtensionKey,
  );
}

function navItemFromContribution(
  contribution: FrontendNavContribution,
): NavItem {
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

function financeNavItems(
  extensionList: ExtensionListRead | undefined,
): NavItem[] {
  return financeWorkspaceFrontendExtension.navContributions
    .filter((contribution) => isGateTagEnabled(extensionList, contribution))
    .map(navItemFromContribution);
}

export function assembleNavGroups(
  extensionList: ExtensionListRead | undefined,
): NavGroup[] {
  const enabledFinanceNavItems = financeNavItems(extensionList);
  const navGroups: NavGroup[] = [];

  navGroups.push({ label: "Agent Platform", items: agentPlatformNavItems });

  if (enabledFinanceNavItems.length > 0) {
    navGroups.push({
      label: FINANCE_WORKSPACE_LABEL,
      items: enabledFinanceNavItems,
    });
  }

  navGroups.push({ label: "System", items: systemNavItems });

  return navGroups;
}

export function assembleNavItems(
  extensionList: ExtensionListRead | undefined,
): NavItem[] {
  return assembleNavGroups(extensionList).flatMap((group) => group.items);
}

export function enabledFinanceRoutePaths(
  extensionList: ExtensionListRead | undefined,
): string[] {
  return financeWorkspaceFrontendExtension.routeContributions
    .filter((contribution) => isGateTagEnabled(extensionList, contribution))
    .map((contribution) => contribution.path);
}

function withFinanceWorkspaceGate(Component: ComponentType): ComponentType {
  return function FinanceWorkspaceRoute() {
    return createElement(
      FinanceWorkspaceRouteGate,
      null,
      createElement(Component),
    );
  };
}

export function assembleFinanceWorkspaceRoutes(): ExtensionRouteDefinition[] {
  return financeWorkspaceFrontendExtension.routeContributions.map(
    (contribution) => {
      if (
        contribution.requiredExtensionKey !==
        financeWorkspaceFrontendExtension.key
      ) {
        throw new Error(
          `Finance route gate ${contribution.requiredExtensionKey} does not match ${financeWorkspaceFrontendExtension.key}`,
        );
      }

      const Component = financeRouteComponents[contribution.componentModule];

      if (!Component) {
        throw new Error(
          `Unknown extension route component: ${contribution.componentModule}`,
        );
      }

      const GuardedComponent = withFinanceWorkspaceGate(Component);

      return contribution.path === "/"
        ? { index: true, Component: GuardedComponent }
        : {
            path: contribution.path.replace(/^\//, ""),
            Component: GuardedComponent,
          };
    },
  );
}

export function filterToolsForExtensionState(
  tools: readonly ToolCatalogItemRead[],
  extensionList: ExtensionListRead | undefined,
): ToolCatalogItemRead[] {
  const financeToolContribution =
    financeWorkspaceFrontendExtension.toolAuthoringDiscovery[0];

  if (
    !financeToolContribution ||
    isGateTagEnabled(extensionList, financeToolContribution)
  ) {
    return [...tools];
  }

  return tools.filter(
    (tool) => !tool.key.startsWith(financeToolContribution.toolKeyPrefix),
  );
}
