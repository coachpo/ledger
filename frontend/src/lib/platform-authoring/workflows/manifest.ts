import {
  LineCounter,
  isAlias,
  isMap,
  isScalar,
  isSeq,
  parseDocument,
  stringify,
  type Document,
  type Node,
  type Pair,
  type ParsedNode,
  type YAMLError,
  type YAMLMap,
  type YAMLSeq,
} from "yaml";

import type {
  WorkflowManifestApiVersion,
  WorkflowManifestDiagnostic,
  WorkflowManifestDiagnosticSeverity,
} from "@/lib/types/workflow";

const WORKFLOW_MANIFEST_V1_API_VERSION: WorkflowManifestApiVersion = "signaldeck.workflow/v1";
const WORKFLOW_MANIFEST_V2_API_VERSION: WorkflowManifestApiVersion = "signaldeck.workflow/v2";
const WORKFLOW_MANIFEST_API_VERSIONS = [WORKFLOW_MANIFEST_V1_API_VERSION, WORKFLOW_MANIFEST_V2_API_VERSION] as const;
const WORKFLOW_MANIFEST_KIND = "Workflow";
const WORKFLOW_MANIFEST_SOURCE_MAX_LENGTH = 262_144; // Matches backend WORKFLOW_MANIFEST_SOURCE_MAX_LENGTH.

const WORKFLOW_MANIFEST_SECTION_IDS = [
  "apiVersion",
  "kind",
  "metadata",
  "inputSchema",
  "steps",
  "flow",
  "output",
  "postRunMemory",
] as const;

const WORKFLOW_MANIFEST_V1_REQUIRED_SECTION_IDS = ["apiVersion", "kind", "metadata", "inputSchema", "steps", "output"] as const;
const WORKFLOW_MANIFEST_V2_REQUIRED_SECTION_IDS = ["apiVersion", "kind", "metadata", "inputSchema", "flow", "output"] as const;

const SECTION_LABELS: Record<WorkflowManifestSectionId, string> = {
  apiVersion: "API version",
  kind: "Kind",
  metadata: "Metadata",
  inputSchema: "Input schema",
  steps: "Steps",
  flow: "Flow",
  output: "Output",
  postRunMemory: "Post-run memory",
};

const YAML_STRINGIFY_OPTIONS = {
  aliasDuplicateObjects: false,
  collectionStyle: "block" as const,
  directives: false,
  indent: 2,
  indentSeq: true,
  lineWidth: 0,
  schema: "core",
  simpleKeys: true,
  version: "1.2" as const,
};

type PathToken = string | number;
type ParsedYamlDocument = Document<ParsedNode, true>;

export type WorkflowManifestSectionId = (typeof WORKFLOW_MANIFEST_SECTION_IDS)[number];
export type WorkflowManifestDiagnosticOrigin = "backend" | "local";

export interface WorkflowManifestSourceLocation {
  column: number | null;
  line: number | null;
}

export interface WorkflowManifestEditorDiagnostic extends WorkflowManifestDiagnostic {
  origin: WorkflowManifestDiagnosticOrigin;
}

export interface WorkflowManifestDiagnosticPanelItem extends WorkflowManifestEditorDiagnostic {
  canJump: boolean;
  id: string;
  locationLabel: string;
}

export interface WorkflowManifestLocalParseResult {
  diagnostics: WorkflowManifestEditorDiagnostic[];
  isValidYaml: boolean;
  value: unknown | null;
}

export interface WorkflowManifestOutlineSection extends WorkflowManifestSourceLocation {
  id: WorkflowManifestSectionId;
  label: string;
  path: string;
  present: boolean;
}

export interface WorkflowManifestOutlineAgentSlot extends WorkflowManifestSourceLocation {
  index: number;
  optional: boolean;
  path: string;
  slot: string;
  uses: string | null;
}

export interface WorkflowManifestOutlineStep extends WorkflowManifestSourceLocation {
  agentSlots: WorkflowManifestOutlineAgentSlot[];
  id: string;
  index: number;
  path: string;
}

export interface WorkflowManifestOutline {
  sections: WorkflowManifestOutlineSection[];
  steps: WorkflowManifestOutlineStep[];
}

export interface WorkflowManifestOutlineResult {
  diagnostics: WorkflowManifestEditorDiagnostic[];
  outline: WorkflowManifestOutline;
}

export interface WorkflowManifestFormatResult {
  diagnostics: WorkflowManifestEditorDiagnostic[];
  formatted: string | null;
}

export interface WorkflowManifestScaffoldOptions {
  agentSlot?: string;
  agentUse?: string;
  description?: string;
  key?: string;
  name?: string;
  stepId?: string;
}

interface ParsedYamlForEditor {
  diagnostics: WorkflowManifestEditorDiagnostic[];
  document: ParsedYamlDocument | null;
  lineCounter: LineCounter | null;
}

interface WorkflowManifestPathTarget {
  lineCounter: LineCounter;
  node: unknown;
}

function createLineCounter(): LineCounter {
  return new LineCounter();
}

function parseYamlForEditor(source: string): ParsedYamlForEditor | { diagnostics: [WorkflowManifestEditorDiagnostic]; document: null; lineCounter: null } {
  if (source.length > WORKFLOW_MANIFEST_SOURCE_MAX_LENGTH) {
    return {
      diagnostics: [createOversizedManifestDiagnostic()],
      document: null,
      lineCounter: null,
    };
  }

  const lineCounter = createLineCounter();
  const document = parseDocument(source, {
    keepSourceTokens: true,
    lineCounter,
    logLevel: "silent",
    merge: false,
    prettyErrors: false,
    schema: "core",
    stringKeys: true,
    uniqueKeys: true,
    version: "1.2",
  });

  const diagnostics = [
    ...document.errors.map((error) => yamlProblemToDiagnostic(error, "error", lineCounter)),
    ...document.warnings.map((warning) => yamlProblemToDiagnostic(warning, "warning", lineCounter)),
  ];

  if (diagnostics.some((diagnostic) => diagnostic.severity === "error")) {
    return { diagnostics, document, lineCounter };
  }

  return {
    diagnostics: [...diagnostics, ...collectLocalManifestDiagnostics(document.contents, lineCounter)],
    document,
    lineCounter,
  };
}

function yamlProblemToDiagnostic(
  problem: YAMLError,
  severity: WorkflowManifestDiagnosticSeverity,
  lineCounter: LineCounter,
): WorkflowManifestEditorDiagnostic {
  const location = locationFromYamlProblem(problem, lineCounter);
  const message = problem.code === "DUPLICATE_KEY" ? "Duplicate mapping key is not allowed" : problem.message;

  return {
    column: location.column,
    line: location.line,
    message: message.startsWith("Malformed YAML") ? message : `Malformed YAML: ${message}`,
    origin: "local",
    path: "$",
    severity,
  };
}

function locationFromYamlProblem(problem: YAMLError, lineCounter: LineCounter): WorkflowManifestSourceLocation {
  const linePosition = problem.linePos?.[0];
  if (linePosition) {
    return { column: linePosition.col, line: linePosition.line };
  }
  return locationFromOffset(lineCounter, problem.pos?.[0] ?? null);
}

function collectLocalManifestDiagnostics(
  root: ParsedNode | null,
  lineCounter: LineCounter,
): WorkflowManifestEditorDiagnostic[] {
  const diagnostics = collectUnsupportedYamlFeatureDiagnostics(root, lineCounter, "$");

  if (!isMap(root)) {
    diagnostics.push(
      createLocalDiagnostic("Manifest source must be a YAML mapping", "$", locationFromNode(root, lineCounter)),
    );
    return diagnostics;
  }

  const apiVersion = scalarStringValue(getMapValue(root, "apiVersion"));
  if (!isSupportedWorkflowManifestApiVersion(apiVersion)) {
    diagnostics.push(
      createLocalDiagnostic(
        `apiVersion must be ${WORKFLOW_MANIFEST_API_VERSIONS.join(" or ")}`,
        "apiVersion",
        locationFromNode(getMapValue(root, "apiVersion") ?? getMapKey(root, "apiVersion") ?? root, lineCounter),
      ),
    );
  }

  const kind = scalarStringValue(getMapValue(root, "kind"));
  if (kind !== WORKFLOW_MANIFEST_KIND) {
    diagnostics.push(
      createLocalDiagnostic(
        `kind must be ${WORKFLOW_MANIFEST_KIND}`,
        "kind",
        locationFromNode(getMapValue(root, "kind") ?? getMapKey(root, "kind") ?? root, lineCounter),
      ),
    );
  }

  const requiredSectionIds = apiVersion === WORKFLOW_MANIFEST_V2_API_VERSION
    ? WORKFLOW_MANIFEST_V2_REQUIRED_SECTION_IDS
    : WORKFLOW_MANIFEST_V1_REQUIRED_SECTION_IDS;
  for (const sectionId of requiredSectionIds) {
    if (!getMapPair(root, sectionId)) {
      diagnostics.push(createLocalDiagnostic(`${SECTION_LABELS[sectionId]} is required`, sectionId, locationFromNode(root, lineCounter)));
    }
  }

  if (apiVersion === WORKFLOW_MANIFEST_V2_API_VERSION) {
    diagnostics.push(...collectV2LoopDiagnostics(getMapValue(root, "flow"), lineCounter, "flow"));
  }

  return diagnostics;
}

function isSupportedWorkflowManifestApiVersion(value: string | null): value is WorkflowManifestApiVersion {
  return WORKFLOW_MANIFEST_API_VERSIONS.some((apiVersion) => apiVersion === value);
}

function collectV2LoopDiagnostics(
  node: unknown,
  lineCounter: LineCounter,
  path: string,
): WorkflowManifestEditorDiagnostic[] {
  const diagnostics: WorkflowManifestEditorDiagnostic[] = [];
  if (!node || !isMap(node)) {
    return diagnostics;
  }

  const kind = scalarStringValue(getMapValue(node, "kind"));
  if (kind === "loop" && !getMapPair(node, "maxIterations")) {
    diagnostics.push(
      createLocalDiagnostic(
        "Loop nodes should set maxIterations so browser preview and backend validation agree on iteration bounds",
        `${path}.maxIterations`,
        locationFromNode(getMapValue(node, "kind") ?? node, lineCounter),
        "warning",
      ),
    );
  }

  if (kind === "sequence") {
    const nodes = getMapValue(node, "nodes");
    if (isSeq(nodes)) {
      nodes.items.forEach((child, index) => {
        diagnostics.push(...collectV2LoopDiagnostics(child, lineCounter, `${path}.nodes[${index}]`));
      });
    }
  }

  if (kind === "fanout") {
    const branches = getMapValue(node, "branches");
    if (isSeq(branches)) {
      branches.items.forEach((branch, index) => {
        const childNode = isMap(branch) ? getMapValue(branch, "node") : null;
        diagnostics.push(...collectV2LoopDiagnostics(childNode, lineCounter, `${path}.branches[${index}].node`));
      });
    }
  }

  if (kind === "loop") {
    diagnostics.push(...collectV2LoopDiagnostics(getMapValue(node, "sequence"), lineCounter, `${path}.sequence`));
  }

  return diagnostics;
}

function collectUnsupportedYamlFeatureDiagnostics(
  node: unknown,
  lineCounter: LineCounter,
  path: string,
): WorkflowManifestEditorDiagnostic[] {
  const diagnostics: WorkflowManifestEditorDiagnostic[] = [];

  if (!node) {
    return diagnostics;
  }

  if (isAlias(node)) {
    diagnostics.push(createLocalDiagnostic("YAML aliases are not supported in workflow manifests", path, locationFromNode(node, lineCounter)));
    return diagnostics;
  }

  if (nodeHasAnchor(node)) {
    diagnostics.push(createLocalDiagnostic("YAML anchors are not supported in workflow manifests", path, locationFromNode(node, lineCounter)));
  }

  if (isMap(node)) {
    for (const pair of node.items) {
      const key = scalarStringValue(pair.key);
      const childPath = key ? appendPath(path, key) : path;
      if (key === "<<") {
        diagnostics.push(createLocalDiagnostic("YAML merge keys are not supported in workflow manifests", childPath, locationFromNode(pair.key, lineCounter)));
      }
      diagnostics.push(...collectUnsupportedYamlFeatureDiagnostics(pair.key, lineCounter, childPath));
      diagnostics.push(...collectUnsupportedYamlFeatureDiagnostics(pair.value, lineCounter, childPath));
    }
    return diagnostics;
  }

  if (isSeq(node)) {
    node.items.forEach((item, index) => {
      diagnostics.push(...collectUnsupportedYamlFeatureDiagnostics(item, lineCounter, appendPath(path, index)));
    });
  }

  return diagnostics;
}

function createLocalDiagnostic(
  message: string,
  path: string,
  location: WorkflowManifestSourceLocation,
  severity: WorkflowManifestDiagnosticSeverity = "error",
): WorkflowManifestEditorDiagnostic {
  return {
    column: location.column,
    line: location.line,
    message,
    origin: "local",
    path,
    severity,
  };
}

function createOversizedManifestDiagnostic(): WorkflowManifestEditorDiagnostic {
  return createLocalDiagnostic(
    `Workflow manifest source must be at most ${WORKFLOW_MANIFEST_SOURCE_MAX_LENGTH} characters`,
    "$",
    { column: null, line: null },
  );
}

function hasErrorDiagnostics(diagnostics: readonly WorkflowManifestDiagnostic[]): boolean {
  return diagnostics.some((diagnostic) => diagnostic.severity === "error");
}

function locationFromOffset(lineCounter: LineCounter, offset: number | null): WorkflowManifestSourceLocation {
  if (offset === null) {
    return { column: null, line: null };
  }

  const position = lineCounter.linePos(Math.max(0, offset));
  if (position.line <= 0) {
    return { column: null, line: null };
  }
  return { column: position.col, line: position.line };
}

function locationFromNode(node: unknown, lineCounter: LineCounter): WorkflowManifestSourceLocation {
  const range = nodeRange(node);
  return locationFromOffset(lineCounter, range?.[0] ?? null);
}

function nodeRange(node: unknown): [number, number, number] | null {
  if (!node || typeof node !== "object" || !("range" in node)) {
    return null;
  }

  const range = (node as { range?: unknown }).range;
  if (
    Array.isArray(range) &&
    range.length >= 3 &&
    typeof range[0] === "number" &&
    typeof range[1] === "number" &&
    typeof range[2] === "number"
  ) {
    return [range[0], range[1], range[2]];
  }
  return null;
}

function nodeHasAnchor(node: unknown): boolean {
  return Boolean(
    node &&
      typeof node === "object" &&
      "anchor" in node &&
      typeof (node as { anchor?: unknown }).anchor === "string" &&
      (node as { anchor?: string }).anchor,
  );
}

function getMapPair(map: YAMLMap<unknown, unknown>, key: string): Pair<unknown, unknown> | undefined {
  return map.items.find((item) => scalarStringValue(item.key) === key);
}

function getMapValue(map: YAMLMap<unknown, unknown>, key: string): unknown {
  return getMapPair(map, key)?.value ?? null;
}

function getMapKey(map: YAMLMap<unknown, unknown>, key: string): unknown {
  return getMapPair(map, key)?.key ?? null;
}

function scalarStringValue(node: unknown): string | null {
  if (!isScalar(node)) {
    return null;
  }
  if (node.value === null || node.value === undefined) {
    return null;
  }
  return String(node.value);
}

function scalarBooleanValue(node: unknown): boolean {
  return isScalar(node) && node.value === true;
}

function emptyOutline(): WorkflowManifestOutline {
  return {
    sections: WORKFLOW_MANIFEST_SECTION_IDS.map((id) => ({
      column: null,
      id,
      label: SECTION_LABELS[id],
      line: null,
      path: id,
      present: false,
    })),
    steps: [],
  };
}

function extractOutlineFromDocument(
  document: ParsedYamlDocument,
  lineCounter: LineCounter,
): WorkflowManifestOutline {
  const root = document.contents;
  const outline = emptyOutline();
  if (!isMap(root)) {
    return outline;
  }

  outline.sections = WORKFLOW_MANIFEST_SECTION_IDS.map((id) => {
    const pair = getMapPair(root, id);
    const location = locationFromNode(pair?.key ?? pair?.value ?? null, lineCounter);
    return {
      column: location.column,
      id,
      label: SECTION_LABELS[id],
      line: location.line,
      path: id,
      present: Boolean(pair),
    };
  });

  const stepsNode = getMapValue(root, "steps");
  if (isSeq(stepsNode)) {
    outline.steps = stepsNode.items.map((stepNode, stepIndex) => extractOutlineStep(stepNode, stepIndex, lineCounter));
    return outline;
  }

  const flowNode = getMapValue(root, "flow");
  outline.steps = extractV2OutlineSteps(flowNode, lineCounter);
  return outline;
}

function extractV2OutlineSteps(
  flowNode: unknown,
  lineCounter: LineCounter,
): WorkflowManifestOutlineStep[] {
  const steps: WorkflowManifestOutlineStep[] = [];
  const visit = (node: unknown, path: string) => {
    if (!isMap(node)) {
      return;
    }
    const kind = scalarStringValue(getMapValue(node, "kind"));
    if (kind === "step") {
      const location = locationFromNode(node, lineCounter);
      const stepId = scalarStringValue(getMapValue(node, "id")) ?? "";
      steps.push({
        agentSlots: [
          {
            column: location.column,
            index: 0,
            line: location.line,
            optional: scalarBooleanValue(getMapValue(node, "optional")),
            path,
            slot: scalarStringValue(getMapValue(node, "slot")) ?? "",
            uses: scalarStringValue(getMapValue(node, "uses")),
          },
        ],
        column: location.column,
        id: stepId,
        index: steps.length,
        line: location.line,
        path,
      });
      return;
    }

    if (kind === "sequence") {
      const children = getMapValue(node, "nodes");
      if (isSeq(children)) {
        children.items.forEach((child, index) => visit(child, `${path}.nodes[${index}]`));
      }
      return;
    }

    if (kind === "fanout") {
      const branches = getMapValue(node, "branches");
      if (isSeq(branches)) {
        branches.items.forEach((branch, index) => {
          const childNode = isMap(branch) ? getMapValue(branch, "node") : null;
          visit(childNode, `${path}.branches[${index}].node`);
        });
      }
      return;
    }

    if (kind === "loop") {
      visit(getMapValue(node, "sequence"), `${path}.sequence`);
    }
  };

  visit(flowNode, "flow");
  return steps;
}

function extractOutlineStep(
  stepNode: unknown,
  stepIndex: number,
  lineCounter: LineCounter,
): WorkflowManifestOutlineStep {
  const path = `steps[${stepIndex}]`;
  const location = locationFromNode(stepNode, lineCounter);
  const stepId = isMap(stepNode) ? scalarStringValue(getMapValue(stepNode, "id")) : null;
  const agentsNode = isMap(stepNode) ? getMapValue(stepNode, "agents") : null;

  return {
    agentSlots: isSeq(agentsNode)
      ? agentsNode.items.map((agentNode, agentIndex) => extractOutlineAgentSlot(agentNode, stepIndex, agentIndex, lineCounter))
      : [],
    column: location.column,
    id: stepId ?? "",
    index: stepIndex,
    line: location.line,
    path,
  };
}

function extractOutlineAgentSlot(
  agentNode: unknown,
  stepIndex: number,
  agentIndex: number,
  lineCounter: LineCounter,
): WorkflowManifestOutlineAgentSlot {
  const path = `steps[${stepIndex}].agents[${agentIndex}]`;
  const slotNode = isMap(agentNode) ? getMapValue(agentNode, "slot") : null;
  const location = locationFromNode(slotNode ?? agentNode, lineCounter);

  return {
    column: location.column,
    index: agentIndex,
    line: location.line,
    optional: isMap(agentNode) ? scalarBooleanValue(getMapValue(agentNode, "optional")) : false,
    path,
    slot: scalarStringValue(slotNode) ?? "",
    uses: isMap(agentNode) ? scalarStringValue(getMapValue(agentNode, "uses")) : null,
  };
}

function pathToTokens(path: string): PathToken[] {
  if (!path || path === "$") {
    return [];
  }

  const tokens: PathToken[] = [];
  for (const rawSegment of path.split(".")) {
    let segment = rawSegment;
    while (segment) {
      const bracketIndex = segment.indexOf("[");
      if (bracketIndex > 0) {
        tokens.push(segment.slice(0, bracketIndex));
        segment = segment.slice(bracketIndex);
        continue;
      }
      if (bracketIndex === -1) {
        tokens.push(segment);
        segment = "";
        continue;
      }

      const indexMatch = /^\[(\d+)]/.exec(segment);
      if (!indexMatch) {
        return [];
      }
      tokens.push(Number(indexMatch[1]));
      segment = segment.slice(indexMatch[0].length);
    }
  }
  return tokens;
}

function appendPath(path: string, token: PathToken): string {
  if (typeof token === "number") {
    return path === "$" ? `[${token}]` : `${path}[${token}]`;
  }
  return path === "$" ? token : `${path}.${token}`;
}

function locatePathTarget(root: ParsedNode | null, tokens: readonly PathToken[]): unknown {
  let current: unknown = root;
  let lastTarget: unknown = root;

  for (const token of tokens) {
    if (typeof token === "string" && isMap(current)) {
      const pair = getMapPair(current, token);
      if (!pair) {
        return lastTarget;
      }
      lastTarget = pair.value ?? pair.key;
      current = pair.value;
      continue;
    }

    if (typeof token === "number" && isSeq(current)) {
      const item = current.items[token];
      if (!item) {
        return lastTarget;
      }
      lastTarget = item;
      current = item;
      continue;
    }

    return lastTarget;
  }

  return lastTarget;
}

function locatePathTargetInSource(source: string, path: string): WorkflowManifestPathTarget | null {
  const parsed = parseYamlForEditor(source);
  if (hasErrorDiagnostics(parsed.diagnostics) || !parsed.document || !parsed.lineCounter) {
    return null;
  }
  return {
    lineCounter: parsed.lineCounter,
    node: locatePathTarget(parsed.document.contents, pathToTokens(path)),
  };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function orderedRecord(
  record: Record<string, unknown>,
  preferredKeys: readonly string[],
  path: readonly PathToken[],
): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  for (const key of preferredKeys) {
    if (Object.prototype.hasOwnProperty.call(record, key)) {
      result[key] = normalizeManifestForStringify(record[key], [...path, key]);
    }
  }

  for (const key of Object.keys(record).filter((key) => !preferredKeys.includes(key)).sort((left, right) => left.localeCompare(right))) {
    result[key] = normalizeManifestForStringify(record[key], [...path, key]);
  }
  return result;
}

function normalizeManifestForStringify(value: unknown, path: readonly PathToken[] = []): unknown {
  if (Array.isArray(value)) {
    return value.map((item, index) => normalizeManifestForStringify(item, [...path, index]));
  }

  if (!isRecord(value)) {
    return value;
  }

  const pathKey = path.join(".");
  if (path.length === 0) {
    return orderedRecord(value, WORKFLOW_MANIFEST_SECTION_IDS, path);
  }
  if (pathKey === "metadata") {
    return orderedRecord(value, ["key", "name", "description"], path);
  }
  if (path.includes("inputSchema")) {
    return orderedRecord(value, ["type", "title", "description", "properties", "required", "items", "additionalProperties", "$ref"], path);
  }
  if (path[path.length - 2] === "steps" && typeof path[path.length - 1] === "number") {
    return orderedRecord(value, ["id", "agents"], path);
  }
  if (path[path.length - 2] === "agents" && typeof path[path.length - 1] === "number") {
    return orderedRecord(value, ["slot", "uses", "optional", "with"], path);
  }
  if (pathKey === "output") {
    return orderedRecord(value, ["from"], path);
  }
  return orderedRecord(value, [], path);
}

function toPlainYamlValue(document: ParsedYamlDocument): unknown {
  return document.toJS({ maxAliasCount: 0 });
}

function locationLabel(diagnostic: WorkflowManifestDiagnostic): string {
  if (diagnostic.line !== null) {
    return diagnostic.column !== null ? `Line ${diagnostic.line}, column ${diagnostic.column}` : `Line ${diagnostic.line}`;
  }
  return diagnostic.path && diagnostic.path !== "$" ? diagnostic.path : "Manifest";
}

export function createWorkflowManifestScaffold(options: WorkflowManifestScaffoldOptions = {}): string {
  const agentSlot = options.agentSlot?.trim() || "analysis";
  const stepId = options.stepId?.trim() || "research";

  return stringify(
    normalizeManifestForStringify({
      apiVersion: WORKFLOW_MANIFEST_V1_API_VERSION,
      kind: WORKFLOW_MANIFEST_KIND,
      metadata: {
        key: options.key?.trim() || "new_workflow",
        name: options.name?.trim() || "New Workflow",
        description: options.description?.trim() || "Describe what this workflow does.",
      },
      inputSchema: {
        type: "object",
        properties: {
          ticker: {
            type: "string",
            title: "Ticker",
            description: "Ticker symbol to research, such as AAPL.",
          },
        },
        required: ["ticker"],
      },
      steps: [
        {
          id: stepId,
          agents: [
            {
              slot: agentSlot,
              uses: options.agentUse?.trim() || "research_agent@1",
              with: {
                ticker: "${{ inputs.ticker }}",
              },
            },
          ],
        },
      ],
      output: {
        from: `\${{ steps.${stepId}.outputs.${agentSlot} }}`,
      },
    }),
    YAML_STRINGIFY_OPTIONS,
  );
}

export function parseWorkflowManifestLocallyForEditor(source: string): WorkflowManifestLocalParseResult {
  const parsed = parseYamlForEditor(source);
  if (hasErrorDiagnostics(parsed.diagnostics) || !parsed.document) {
    return {
      diagnostics: parsed.diagnostics,
      isValidYaml: false,
      value: null,
    };
  }

  return {
    diagnostics: parsed.diagnostics,
    isValidYaml: true,
    value: toPlainYamlValue(parsed.document),
  };
}

export function extractWorkflowManifestOutline(source: string): WorkflowManifestOutlineResult {
  const parsed = parseYamlForEditor(source);
  if (hasErrorDiagnostics(parsed.diagnostics) || !parsed.document || !parsed.lineCounter) {
    return {
      diagnostics: parsed.diagnostics,
      outline: emptyOutline(),
    };
  }

  return {
    diagnostics: parsed.diagnostics,
    outline: extractOutlineFromDocument(parsed.document, parsed.lineCounter),
  };
}

export function locateWorkflowManifestPath(source: string, path: string): WorkflowManifestSourceLocation {
  const target = locatePathTargetInSource(source, path);
  if (!target) {
    return { column: null, line: null };
  }
  return locationFromNode(target.node, target.lineCounter);
}

export function mapWorkflowManifestDiagnosticsForEditor(
  diagnostics: readonly WorkflowManifestDiagnostic[],
  options: {
    manifestSource?: string;
    origin?: WorkflowManifestDiagnosticOrigin;
  } = {},
): WorkflowManifestDiagnosticPanelItem[] {
  const origin = options.origin ?? "backend";

  return diagnostics.map((diagnostic, index) => {
    const sourceLocation =
      options.manifestSource && diagnostic.line === null
        ? locateWorkflowManifestPath(options.manifestSource, diagnostic.path)
        : { column: diagnostic.column, line: diagnostic.line };
    const mappedDiagnostic: WorkflowManifestEditorDiagnostic = {
      ...diagnostic,
      column: diagnostic.column ?? sourceLocation.column,
      line: diagnostic.line ?? sourceLocation.line,
      origin,
    };

    return {
      ...mappedDiagnostic,
      canJump: mappedDiagnostic.line !== null,
      id: `${origin}:${mappedDiagnostic.path}:${mappedDiagnostic.line ?? ""}:${mappedDiagnostic.column ?? ""}:${index}`,
      locationLabel: locationLabel(mappedDiagnostic),
    };
  });
}

export function formatWorkflowManifestYaml(source: string): WorkflowManifestFormatResult {
  const parsed = parseYamlForEditor(source);
  if (hasErrorDiagnostics(parsed.diagnostics) || !parsed.document) {
    return {
      diagnostics: parsed.diagnostics,
      formatted: null,
    };
  }

  try {
    return {
      diagnostics: parsed.diagnostics,
      formatted: stringify(normalizeManifestForStringify(toPlainYamlValue(parsed.document)), YAML_STRINGIFY_OPTIONS),
    };
  } catch (error) {
    return {
      diagnostics: [
        createLocalDiagnostic(
          error instanceof Error ? error.message : "Unable to format workflow manifest YAML",
          "$",
          { column: null, line: null },
        ),
      ],
      formatted: null,
    };
  }
}

export type WorkflowManifestYamlNode = Node | YAMLMap | YAMLSeq;
