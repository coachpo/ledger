import type { FrontendExtensionDefinition } from "./types";
import {
  financeWorkspaceFrontendExtension,
  FINANCE_WORKSPACE_EXTENSION_KEY,
} from "./ledger-finance";

export const bundledFrontendExtensions = {
  [FINANCE_WORKSPACE_EXTENSION_KEY]: financeWorkspaceFrontendExtension,
} as const satisfies Record<string, FrontendExtensionDefinition>;

export type BundledFrontendExtensionKey = keyof typeof bundledFrontendExtensions;

export function listBundledFrontendExtensions(): readonly FrontendExtensionDefinition[] {
  return Object.values(bundledFrontendExtensions);
}
export function getBundledFrontendExtension(
  extensionKey: string,
): FrontendExtensionDefinition | undefined {
  return bundledFrontendExtensions[extensionKey as BundledFrontendExtensionKey];
}

export function requireBundledFrontendExtension(extensionKey: string): FrontendExtensionDefinition {
  const extension = getBundledFrontendExtension(extensionKey);
  if (!extension) {
    throw new Error(`Unknown bundled frontend extension: ${extensionKey}`);
  }
  return extension;
}
