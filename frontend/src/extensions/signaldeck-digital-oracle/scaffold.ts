import type { FrontendExtensionDefinition } from "../types";

export const DIGITAL_ORACLE_EXTENSION_KEY = "signaldeck.digital_oracle";
export const DIGITAL_ORACLE_LABEL = "Digital Oracle Runtime";

const digitalOracleToolAuthoringDiscovery = [
  {
    requiredExtensionKey: DIGITAL_ORACLE_EXTENSION_KEY,
    toolKeyPrefix: "signaldeck.digital_oracle.prediction_markets.",
  },
  {
    requiredExtensionKey: DIGITAL_ORACLE_EXTENSION_KEY,
    toolKeyPrefix: "signaldeck.digital_oracle.sec_filings.",
  },
  {
    requiredExtensionKey: DIGITAL_ORACLE_EXTENSION_KEY,
    toolKeyPrefix: "signaldeck.digital_oracle.market_sentiment.",
  },
  {
    requiredExtensionKey: DIGITAL_ORACLE_EXTENSION_KEY,
    toolKeyPrefix: "signaldeck.digital_oracle.macro_rates.",
  },
  {
    requiredExtensionKey: DIGITAL_ORACLE_EXTENSION_KEY,
    toolKeyPrefix: "signaldeck.digital_oracle.crypto_derivatives.",
  },
  {
    requiredExtensionKey: DIGITAL_ORACLE_EXTENSION_KEY,
    toolKeyPrefix: "signaldeck.digital_oracle.cftc_positioning.",
  },
  {
    requiredExtensionKey: DIGITAL_ORACLE_EXTENSION_KEY,
    toolKeyPrefix: "signaldeck.digital_oracle.options.",
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
