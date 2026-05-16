export interface ExtensionToggleRequest {
  enabled: boolean;
}

export interface ExtensionRead {
  key: string;
  label: string;
  enabled: boolean;
}

export interface ExtensionListRead {
  items: ExtensionRead[];
}
