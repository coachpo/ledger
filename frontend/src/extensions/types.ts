import type { ComponentType } from "react";

import type { AbsoluteRoutePath, RouteMetadata } from "@/routes.metadata";

export type FrontendExtensionGateTag = {
  requiredExtensionKey: string;
};

export type FrontendRouteMetadataContribution = Omit<
  RouteMetadata,
  "owner" | "pattern"
>;

export type FrontendRouteContribution = FrontendExtensionGateTag & {
  lazy: () => Promise<{ Component: ComponentType }>;
  path: AbsoluteRoutePath;
  routeMetadata: FrontendRouteMetadataContribution;
};

export type FrontendNavContribution = FrontendExtensionGateTag & {
  iconName: string;
  label: string;
  testId: string;
  to: AbsoluteRoutePath;
};

export type FrontendToolAuthoringDiscoveryContribution =
  FrontendExtensionGateTag & {
    toolKeyPrefix: string;
  };

export type FrontendExtensionDefinition = {
  key: string;
  label: string;
  navContributions: readonly FrontendNavContribution[];
  routeContributions: readonly FrontendRouteContribution[];
  toolAuthoringDiscovery: readonly FrontendToolAuthoringDiscoveryContribution[];
};
