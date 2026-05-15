export type FrontendExtensionStateSource = {
  defaultEnabled: boolean;
  endpoint: "/api/extensions";
  extensionKey: string;
  kind: "backend-extension-state";
};

export type FrontendExtensionAvailability = {
  currentBehavior: string;
  stateSource: FrontendExtensionStateSource;
};

export type FrontendRouteContribution = {
  componentModule: string;
  id: string;
  owner: "extension" | "core";
  path: string;
};

export type FrontendNavContribution = {
  iconName: string;
  id: string;
  label: string;
  owner: "extension" | "core";
  testId: string;
  to: string;
};

export type FrontendSettingsPageContribution = {
  id: string;
  label: string;
  path: string;
};

export type FrontendToolAuthoringDiscoveryContribution = {
  catalogEndpoint: "/api/tools";
  host: "core-workflow-package-authoring";
  id: string;
  queryKeyNamespace: string;
  sourceHook: string;
  toolKeyPrefix: string;
};

export type FrontendApiAvailabilityContribution = {
  id: string;
  methodScope: readonly string[];
  pathPrefix: string;
  stateSource: FrontendExtensionStateSource;
};

export type FrontendExtensionDefinition = {
  adminPages: readonly FrontendSettingsPageContribution[];
  apiAvailability: readonly FrontendApiAvailabilityContribution[];
  availability: FrontendExtensionAvailability;
  defaultEnabled: boolean;
  key: string;
  label: string;
  navContributions: readonly FrontendNavContribution[];
  phase: string;
  routeContributions: readonly FrontendRouteContribution[];
  settingsPages: readonly FrontendSettingsPageContribution[];
  toolAuthoringDiscovery: readonly FrontendToolAuthoringDiscoveryContribution[];
};
