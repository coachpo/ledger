export type RunDetailTabKey =
  | "output"
  | "execution"
  | "overview"
  | "input"
  | "runtime"
  | "usage"
  | "memory"
  | "lineage";

export const RUN_DETAIL_TAB_ORDER = [
  "output",
  "execution",
  "overview",
  "input",
  "runtime",
  "usage",
  "memory",
  "lineage",
] as const satisfies readonly RunDetailTabKey[];

export const RUN_DETAIL_TAB_LABELS: Record<RunDetailTabKey, string> = {
  output: "Output",
  execution: "Execution",
  overview: "Overview",
  input: "Input",
  runtime: "Runtime",
  usage: "Usage",
  memory: "Memory",
  lineage: "Lineage",
};

const RUN_DETAIL_TAB_KEYS: readonly RunDetailTabKey[] = [
  "output",
  "execution",
  "overview",
  "input",
  "runtime",
  "usage",
  "memory",
  "lineage",
];

const RUN_DETAIL_TAB_INFERENCE_ALIASES: Record<string, RunDetailTabKey> = {
  audit: "overview",
  diagnostics: "execution",
  input: "input",
  inputs: "input",
  lineage: "lineage",
  memory: "memory",
  metadata: "overview",
  output: "output",
  outputs: "output",
  overview: "overview",
  runtime: "runtime",
  summary: "overview",
  tokens: "usage",
  usage: "usage",
  execution: "execution",
};

function normalizeRawValue(raw: string | null | undefined): string | null {
  if (raw === null || raw === undefined) {
    return null;
  }

  const trimmed = raw.trim();
  return trimmed === "" ? null : trimmed;
}

export function parseRunDetailTab(raw: string | null | undefined): RunDetailTabKey | null {
  const normalized = normalizeRawValue(raw);
  if (!normalized) {
    return null;
  }

  return RUN_DETAIL_TAB_KEYS.includes(normalized as RunDetailTabKey)
    ? (normalized as RunDetailTabKey)
    : null;
}

function parseRawHashTab(rawHash: string | null | undefined): RunDetailTabKey | null {
  const normalizedHash = normalizeRawValue(rawHash);
  if (!normalizedHash) {
    return null;
  }

  if (normalizedHash === "#run-context" || normalizedHash === "run-context") {
    return null;
  }

  const hash = normalizedHash.startsWith("#") ? normalizedHash.slice(1) : normalizedHash;
  if (/^step-\d+$/.test(hash) || /^invocation-\d+$/.test(hash) || /^operation-invocation-\d+$/.test(hash)) {
    return "execution";
  }

  return null;
}

function parseRawPaneTab(
  rawPane: string | null | undefined,
  rawInspect: string | null | undefined,
): RunDetailTabKey | null {
  const pane = normalizeRawValue(rawPane);
  const inspect = normalizeRawValue(rawInspect);

  if (
    inspect &&
    (inspect.startsWith("step:") ||
      inspect.startsWith("invocation:") ||
      inspect.startsWith("operation:"))
  ) {
    return "execution";
  }
  if (inspect && inspect.startsWith("memory:")) {
    return "memory";
  }
  if (pane === "error") {
    return "execution";
  }
  if (pane === "finalOutput" || pane === "output") {
    return "output";
  }
  if (pane === "input") {
    return "input";
  }
  if (pane === "memory") {
    return "memory";
  }
  if (pane === "lineage") {
    return "lineage";
  }
  if (pane === "details" || pane === "provenance") {
    return inspect?.startsWith("memory:") ? "memory" : null;
  }

  return null;
}

export function inferRunDetailTabFromUrlHints({
  rawMode,
  rawPane,
  rawInspect,
  rawHash,
}: {
  rawMode: string | null | undefined;
  rawPane: string | null | undefined;
  rawInspect: string | null | undefined;
  rawHash: string | null | undefined;
}): RunDetailTabKey | null {
  const normalizedMode = normalizeRawValue(rawMode);
  if (normalizedMode && Object.hasOwn(RUN_DETAIL_TAB_INFERENCE_ALIASES, normalizedMode)) {
    return RUN_DETAIL_TAB_INFERENCE_ALIASES[normalizedMode];
  }

  const fromPane = parseRawPaneTab(rawPane, rawInspect);
  if (fromPane) {
    return fromPane;
  }

  const fromHash = parseRawHashTab(rawHash);
  if (fromHash) {
    return fromHash;
  }

  return null;
}

export function resolveRunDetailTab({
  rawTab,
  rawMode,
  rawPane,
  rawInspect,
  rawHash,
}: {
  rawTab: string | null | undefined;
  rawMode: string | null | undefined;
  rawPane: string | null | undefined;
  rawInspect: string | null | undefined;
  rawHash: string | null | undefined;
}): RunDetailTabKey {
  const parsedTab = parseRunDetailTab(rawTab);
  if (parsedTab) {
    return parsedTab;
  }

  return inferRunDetailTabFromUrlHints({ rawMode, rawPane, rawInspect, rawHash }) ?? "output";
}

export function withRunDetailTab(
  searchParams: URLSearchParams,
  tab: RunDetailTabKey,
): URLSearchParams {
  const next = new URLSearchParams(searchParams);
  next.set("tab", tab);
  return next;
}
