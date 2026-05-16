export type FrontendExtensionGateTag = {
  requiredExtensionKey: string;
};

export type FrontendRouteContribution = FrontendExtensionGateTag & {
  componentModule: string;
  path: string;
};

export type FrontendNavContribution = FrontendExtensionGateTag & {
  iconName: string;
  label: string;
  testId: string;
  to: string;
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
