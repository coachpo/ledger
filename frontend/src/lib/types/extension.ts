export interface ExtensionContributionRead {
  extensionKey: string;
  category: string;
  summary: string;
  surface: string;
  ownerExtensionKey: string;
  dependencies: string[];
}

export interface ExtensionToggleRequest {
  enabled: boolean;
  disabledReason?: string | null;
}

export interface ExtensionRead {
  key: string;
  label: string;
  enabled: boolean;
  defaultEnabled: boolean;
  phase: string;
  versioningRule: string;
  contributionCategories: string[];
  dependencies: string[];
  contributions: ExtensionContributionRead[];
  stateVersion: number;
  enabledAt: string | null;
  disabledAt: string | null;
  disabledReason: string | null;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface ExtensionListRead {
  items: ExtensionRead[];
}
