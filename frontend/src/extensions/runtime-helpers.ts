import { createElement, type ComponentType } from "react";
import {
  Briefcase,
  ClipboardList,
  Database,
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
import {
  getSidebarRouteMetadataGroups,
  type RouteMetadata,
  type RouteNavIconName,
} from "@/routes.metadata";

import { listBundledFrontendExtensions } from "./registry";
import { FinanceWorkspaceRouteGate } from "./runtime";
import { financeWorkspaceFrontendExtension } from "./signaldeck-finance";
import type { FrontendExtensionGateTag } from "./types";

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

const navIconByName: Record<RouteNavIconName, LucideIcon> = {
  Briefcase,
  ClipboardList,
  Database,
  FileText,
  LayoutDashboard,
  Link2,
  PlayCircle,
  Puzzle,
  Workflow,
};

function navItemFromMetadata(metadata: RouteMetadata): NavItem {
  const icon = navIconByName[metadata.nav.iconName];

  if (!metadata.nav.path) {
    throw new Error(`Sidebar route metadata is missing a nav path: ${metadata.pattern}`);
  }

  return {
    icon,
    label: metadata.nav.label,
    testId: metadata.nav.testId,
    to: metadata.nav.path,
  };
}

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

function isRouteMetadataVisibleForExtensionState(
  metadata: RouteMetadata,
  extensionList: ExtensionListRead | undefined,
): boolean {
  if (metadata.owner.kind !== "extension") {
    return true;
  }

  return isFrontendExtensionEnabled(extensionList, metadata.owner.extensionKey);
}

export function assembleNavGroups(
  extensionList: ExtensionListRead | undefined,
): NavGroup[] {
  return getSidebarRouteMetadataGroups()
    .map((group) => ({
      items: group.items
        .filter((metadata) =>
          isRouteMetadataVisibleForExtensionState(metadata, extensionList),
        )
        .map(navItemFromMetadata),
      label: group.label,
    }))
    .filter((group) => group.items.length > 0);
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

      const GuardedComponent = withFinanceWorkspaceGate(contribution.Component);

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
  const disabledToolPrefixes = listBundledFrontendExtensions()
    .flatMap((extension) => extension.toolAuthoringDiscovery)
    .filter((contribution) => !isGateTagEnabled(extensionList, contribution))
    .map((contribution) => contribution.toolKeyPrefix);

  if (disabledToolPrefixes.length === 0) {
    return [...tools];
  }

  return tools.filter(
    (tool) =>
      !disabledToolPrefixes.some((prefix) => tool.key.startsWith(prefix)),
  );
}
