import type { FrontendExtensionDefinition } from "../types";

export const DIGITAL_ORACLE_EXTENSION_KEY = "signaldeck.digital_oracle";
export const DIGITAL_ORACLE_LABEL = "Digital Oracle Runtime";

const digitalOracleToolAuthoringDiscovery = [
  {
    requiredExtensionKey: DIGITAL_ORACLE_EXTENSION_KEY,
    toolKeyPrefix: "signaldeck.prediction_markets.",
  },
  {
    requiredExtensionKey: DIGITAL_ORACLE_EXTENSION_KEY,
    toolKeyPrefix: "signaldeck.sec_filings.",
  },
  {
    requiredExtensionKey: DIGITAL_ORACLE_EXTENSION_KEY,
    toolKeyPrefix: "signaldeck.market_sentiment.",
  },
] as const;

export const digitalOracleFrontendExtension = {
  key: DIGITAL_ORACLE_EXTENSION_KEY,
  label: DIGITAL_ORACLE_LABEL,
  navContributions: [],
  routeContributions: [],
  toolAuthoringDiscovery: digitalOracleToolAuthoringDiscovery,
} as const satisfies FrontendExtensionDefinition;

export function getDigitalOracleFrontendExtension(): FrontendExtensionDefinition {
  return digitalOracleFrontendExtension;
}
