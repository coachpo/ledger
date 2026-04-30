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
  AgentManifestApiVersion,
  AgentManifestDiagnostic,
  AgentManifestDiagnosticSeverity,
} from "@/lib/types/agent";

const AGENT_MANIFEST_API_VERSION: AgentManifestApiVersion = "ledger.agent/v1";
const AGENT_MANIFEST_KIND = "Agent";
const AGENT_MANIFEST_SOURCE_MAX_LENGTH = 262_144;

const AGENT_MANIFEST_SECTION_IDS = ["apiVersion", "kind", "metadata", "spec"] as const;
const REQUIRED_SPEC_FIELDS = ["modelConnection", "systemPrompt", "inputSchema", "outputSchema"] as const;

const SECTION_LABELS: Record<AgentManifestSectionId, string> = {
  apiVersion: "API version",
  kind: "Kind",
  metadata: "Metadata",
  spec: "Spec",
};

const SPEC_REF_LABELS: Record<AgentManifestOutlineRefKind, string> = {
  capability: "Capability",
  modelConnection: "Model connection",
  outputSchema: "Output schema",
  mcpServer: "MCP server",
};

const ALLOWED_YAML_TAGS = new Set<unknown>([
  undefined,
  null,
  "tag:yaml.org,2002:bool",
  "tag:yaml.org,2002:float",
  "tag:yaml.org,2002:int",
  "tag:yaml.org,2002:map",
  "tag:yaml.org,2002:null",
  "tag:yaml.org,2002:seq",
  "tag:yaml.org,2002:str",
]);

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

export type AgentManifestSectionId = (typeof AGENT_MANIFEST_SECTION_IDS)[number];
export type AgentManifestDiagnosticOrigin = "backend" | "local";
export type AgentManifestOutlineRefKind = "modelConnection" | "outputSchema" | "capability" | "mcpServer";

export interface AgentManifestSourceLocation {
  column: number | null;
  line: number | null;
}

export interface AgentManifestEditorDiagnostic extends AgentManifestDiagnostic {
  origin: AgentManifestDiagnosticOrigin;
}

export interface AgentManifestDiagnosticPanelItem extends AgentManifestEditorDiagnostic {
  canJump: boolean;
  id: string;
  locationLabel: string;
}

export interface AgentManifestLocalParseResult {
  diagnostics: AgentManifestEditorDiagnostic[];
  isValidYaml: boolean;
  value: unknown | null;
}

export interface AgentManifestOutlineSection extends AgentManifestSourceLocation {
  id: AgentManifestSectionId;
  label: string;
  path: string;
  present: boolean;
}

export interface AgentManifestOutlineRef extends AgentManifestSourceLocation {
  index: number | null;
  kind: AgentManifestOutlineRefKind;
  label: string;
  path: string;
  ref: string;
}

export interface AgentManifestOutline {
  refs: AgentManifestOutlineRef[];
  sections: AgentManifestOutlineSection[];
}

export interface AgentManifestOutlineResult {
  diagnostics: AgentManifestEditorDiagnostic[];
  outline: AgentManifestOutline;
}

export interface AgentManifestFormatResult {
  diagnostics: AgentManifestEditorDiagnostic[];
  formatted: string | null;
}

export interface AgentManifestSourceInput {
  budgetUsd?: string;
  description?: string;
  inputSchema: unknown;
  key: string;
  mcpServers?: readonly string[];
  modelConnection: string;
  name: string;
  outputSchema: string;
  capabilities?: readonly string[];
  systemPrompt: string;
}

export interface AgentManifestScaffoldOptions {
  budgetUsd?: string;
  description?: string;
  key?: string;
  modelConnection?: string;
  name?: string;
  outputSchema?: string;
  systemPrompt?: string;
}

interface ParsedYamlForEditor {
  diagnostics: AgentManifestEditorDiagnostic[];
  document: ParsedYamlDocument | null;
  lineCounter: LineCounter | null;
}

interface AgentManifestPathTarget {
  lineCounter: LineCounter;
  node: unknown;
}

function parseYamlForEditor(source: string): ParsedYamlForEditor {
  if (source.length > AGENT_MANIFEST_SOURCE_MAX_LENGTH) {
    return {
      diagnostics: [createOversizedManifestDiagnostic()],
      document: null,
      lineCounter: null,
    };
  }

  const lineCounter = new LineCounter();
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
  severity: AgentManifestDiagnosticSeverity,
  lineCounter: LineCounter,
): AgentManifestEditorDiagnostic {
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

function locationFromYamlProblem(problem: YAMLError, lineCounter: LineCounter): AgentManifestSourceLocation {
  const linePosition = problem.linePos?.[0];
  if (linePosition) {
    return { column: linePosition.col, line: linePosition.line };
  }
  return locationFromOffset(lineCounter, problem.pos?.[0] ?? null);
}

function collectLocalManifestDiagnostics(
  root: ParsedNode | null,
  lineCounter: LineCounter,
): AgentManifestEditorDiagnostic[] {
  const diagnostics = collectUnsupportedYamlFeatureDiagnostics(root, lineCounter, "$.");

  if (!isMap(root)) {
    diagnostics.push(
      createLocalDiagnostic("Manifest source must be a YAML mapping", "$", locationFromNode(root, lineCounter)),
    );
    return diagnostics;
  }

  const apiVersion = scalarStringValue(getMapValue(root, "apiVersion"));
  if (apiVersion !== AGENT_MANIFEST_API_VERSION) {
    diagnostics.push(
      createLocalDiagnostic(
        `apiVersion must be ${AGENT_MANIFEST_API_VERSION}`,
        "apiVersion",
        locationFromNode(getMapValue(root, "apiVersion") ?? getMapKey(root, "apiVersion") ?? root, lineCounter),
      ),
    );
  }

  const kind = scalarStringValue(getMapValue(root, "kind"));
  if (kind !== AGENT_MANIFEST_KIND) {
    diagnostics.push(
      createLocalDiagnostic(
        `kind must be ${AGENT_MANIFEST_KIND}`,
        "kind",
        locationFromNode(getMapValue(root, "kind") ?? getMapKey(root, "kind") ?? root, lineCounter),
      ),
    );
  }

  for (const sectionId of AGENT_MANIFEST_SECTION_IDS) {
    if (!getMapPair(root, sectionId)) {
      diagnostics.push(createLocalDiagnostic(`${SECTION_LABELS[sectionId]} is required`, sectionId, locationFromNode(root, lineCounter)));
    }
  }

  const specNode = getMapValue(root, "spec");
  if (isMap(specNode)) {
    for (const field of REQUIRED_SPEC_FIELDS) {
      if (!getMapPair(specNode, field)) {
        diagnostics.push(createLocalDiagnostic(`spec.${field} is required`, `spec.${field}`, locationFromNode(specNode, lineCounter)));
      }
    }
    const modelConnectionIdNode = getMapKey(specNode, "modelConnectionId");
    if (modelConnectionIdNode) {
      diagnostics.push(
        createLocalDiagnostic(
          "Use spec.modelConnection with a stable model connection key; raw modelConnectionId is not supported",
          "spec.modelConnectionId",
          locationFromNode(modelConnectionIdNode, lineCounter),
        ),
      );
    }
    const legacySkillsNode = getMapKey(specNode, "skills");
    if (legacySkillsNode) {
      diagnostics.push(
        createLocalDiagnostic(
          "Use spec.capabilities; legacy spec.skills is not supported",
          "spec.skills",
          locationFromNode(legacySkillsNode, lineCounter),
        ),
      );
    }
  }

  return diagnostics;
}

function collectUnsupportedYamlFeatureDiagnostics(
  node: unknown,
  lineCounter: LineCounter,
  path: string,
): AgentManifestEditorDiagnostic[] {
  const diagnostics: AgentManifestEditorDiagnostic[] = [];

  if (!node) {
    return diagnostics;
  }

  if (isAlias(node)) {
    diagnostics.push(createLocalDiagnostic("YAML aliases are not supported in agent manifests", path, locationFromNode(node, lineCounter)));
    return diagnostics;
  }

  if (nodeHasAnchor(node)) {
    diagnostics.push(createLocalDiagnostic("YAML anchors are not supported in agent manifests", path, locationFromNode(node, lineCounter)));
  }

  const unsupportedTag = unsupportedYamlTag(node);
  if (unsupportedTag) {
    diagnostics.push(createLocalDiagnostic(`YAML tag ${unsupportedTag} is not supported in agent manifests`, path, locationFromNode(node, lineCounter)));
  }

  if (isMap(node)) {
    for (const pair of node.items) {
      const key = scalarStringValue(pair.key);
      const childPath = key ? appendPath(path, key) : path;
      if (key === "<<") {
        diagnostics.push(createLocalDiagnostic("YAML merge keys are not supported in agent manifests", childPath, locationFromNode(pair.key, lineCounter)));
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
  location: AgentManifestSourceLocation,
): AgentManifestEditorDiagnostic {
  return {
    column: location.column,
    line: location.line,
    message,
    origin: "local",
    path,
    severity: "error",
  };
}

function createOversizedManifestDiagnostic(): AgentManifestEditorDiagnostic {
  return createLocalDiagnostic(
    `Agent manifest source must be at most ${AGENT_MANIFEST_SOURCE_MAX_LENGTH} characters`,
    "$",
    { column: null, line: null },
  );
}

function hasErrorDiagnostics(diagnostics: readonly AgentManifestDiagnostic[]): boolean {
  return diagnostics.some((diagnostic) => diagnostic.severity === "error");
}

function locationFromOffset(lineCounter: LineCounter, offset: number | null): AgentManifestSourceLocation {
  if (offset === null) {
    return { column: null, line: null };
  }

  const position = lineCounter.linePos(Math.max(0, offset));
  if (position.line <= 0) {
    return { column: null, line: null };
  }
  return { column: position.col, line: position.line };
}

function locationFromNode(node: unknown, lineCounter: LineCounter): AgentManifestSourceLocation {
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

function unsupportedYamlTag(node: unknown): string | null {
  if (!node || typeof node !== "object" || !("tag" in node)) {
    return null;
  }

  const tag = (node as { tag?: unknown }).tag;
  if (ALLOWED_YAML_TAGS.has(tag)) {
    return null;
  }
  return typeof tag === "string" ? tag : String(tag);
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

function emptyOutline(): AgentManifestOutline {
  return {
    refs: [],
    sections: AGENT_MANIFEST_SECTION_IDS.map((id) => ({
      column: null,
      id,
      label: SECTION_LABELS[id],
      line: null,
      path: id,
      present: false,
    })),
  };
}

function extractOutlineFromDocument(document: ParsedYamlDocument, lineCounter: LineCounter): AgentManifestOutline {
  const root = document.contents;
  const outline = emptyOutline();
  if (!isMap(root)) {
    return outline;
  }

  outline.sections = AGENT_MANIFEST_SECTION_IDS.map((id) => {
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

  const specNode = getMapValue(root, "spec");
  if (!isMap(specNode)) {
    return outline;
  }

  outline.refs = [
    ...extractScalarRef(specNode, "modelConnection", "modelConnection", lineCounter),
    ...extractScalarRef(specNode, "outputSchema", "outputSchema", lineCounter),
    ...extractSequenceRefs(specNode, "capabilities", "capability", lineCounter),
    ...extractSequenceRefs(specNode, "mcpServers", "mcpServer", lineCounter),
  ];
  return outline;
}

function extractScalarRef(
  specNode: YAMLMap<unknown, unknown>,
  field: string,
  kind: AgentManifestOutlineRefKind,
  lineCounter: LineCounter,
): AgentManifestOutlineRef[] {
  const pair = getMapPair(specNode, field);
  if (!pair) {
    return [];
  }

  const location = locationFromNode(pair.value ?? pair.key, lineCounter);
  return [
    {
      column: location.column,
      index: null,
      kind,
      label: SPEC_REF_LABELS[kind],
      line: location.line,
      path: `spec.${field}`,
      ref: scalarStringValue(pair.value) ?? "",
    },
  ];
}

function extractSequenceRefs(
  specNode: YAMLMap<unknown, unknown>,
  field: string,
  kind: AgentManifestOutlineRefKind,
  lineCounter: LineCounter,
): AgentManifestOutlineRef[] {
  const refsNode = getMapValue(specNode, field);
  if (!isSeq(refsNode)) {
    return [];
  }

  return refsNode.items.map((item, index) => {
    const location = locationFromNode(item, lineCounter);
    return {
      column: location.column,
      index,
      kind,
      label: SPEC_REF_LABELS[kind],
      line: location.line,
      path: `spec.${field}[${index}]`,
      ref: scalarStringValue(item) ?? "",
    };
  });
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
  const basePath = path.endsWith(".") ? path.slice(0, -1) : path;
  if (typeof token === "number") {
    return basePath === "$" ? `[${token}]` : `${basePath}[${token}]`;
  }
  return basePath === "$" ? token : `${basePath}.${token}`;
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

function locatePathTargetInSource(source: string, path: string): AgentManifestPathTarget | null {
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
    return orderedRecord(value, AGENT_MANIFEST_SECTION_IDS, path);
  }
  if (pathKey === "metadata") {
    return orderedRecord(value, ["key", "name", "description"], path);
  }
  if (pathKey === "spec") {
    return orderedRecord(
      value,
      ["modelConnection", "systemPrompt", "inputSchema", "outputSchema", "capabilities", "mcpServers", "budgetUsd"],
      path,
    );
  }
  if (path.includes("inputSchema")) {
    return orderedRecord(value, ["type", "title", "description", "properties", "required", "items", "additionalProperties", "$ref"], path);
  }
  return orderedRecord(value, [], path);
}

function toPlainYamlValue(document: ParsedYamlDocument): unknown {
  return document.toJS({ maxAliasCount: 0 });
}

function locationLabel(diagnostic: AgentManifestDiagnostic): string {
  if (diagnostic.line !== null) {
    return diagnostic.column !== null ? `Line ${diagnostic.line}, column ${diagnostic.column}` : `Line ${diagnostic.line}`;
  }
  return diagnostic.path && diagnostic.path !== "$" ? diagnostic.path : "Manifest";
}

export function createAgentManifestSource(input: AgentManifestSourceInput): string {
  return stringify(
    normalizeManifestForStringify({
      apiVersion: AGENT_MANIFEST_API_VERSION,
      kind: AGENT_MANIFEST_KIND,
      metadata: {
        key: input.key.trim().toLowerCase(),
        name: input.name.trim(),
        description: input.description?.trim() ?? "",
      },
      spec: {
        modelConnection: input.modelConnection.trim(),
        systemPrompt: input.systemPrompt.trim(),
        inputSchema: input.inputSchema,
        outputSchema: input.outputSchema.trim(),
        capabilities: [...(input.capabilities ?? [])].map((ref) => ref.trim()).filter(Boolean).sort((left, right) => left.localeCompare(right)),
        mcpServers: [...(input.mcpServers ?? [])].map((ref) => ref.trim()).filter(Boolean).sort((left, right) => left.localeCompare(right)),
        budgetUsd: input.budgetUsd?.trim() || "0",
      },
    }),
    YAML_STRINGIFY_OPTIONS,
  );
}

export function createAgentManifestScaffold(options: AgentManifestScaffoldOptions = {}): string {
  return createAgentManifestSource({
    budgetUsd: options.budgetUsd ?? "0",
    description: options.description ?? "Describe what this agent does.",
    inputSchema: {
      type: "object",
      properties: {
        ticker: {
          type: "string",
        },
      },
      required: ["ticker"],
      additionalProperties: false,
    },
    key: options.key?.trim() || "new_agent",
    mcpServers: [],
    modelConnection: options.modelConnection?.trim() || "primary_model_connection",
    name: options.name?.trim() || "New Agent",
    outputSchema: options.outputSchema?.trim() || "summary_schema@1",
    capabilities: [],
    systemPrompt: options.systemPrompt?.trim() || "You are a concise portfolio research assistant.",
  });
}

export function parseAgentManifestLocallyForEditor(source: string): AgentManifestLocalParseResult {
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

export function extractAgentManifestOutline(source: string): AgentManifestOutlineResult {
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

export function locateAgentManifestPath(source: string, path: string): AgentManifestSourceLocation {
  const target = locatePathTargetInSource(source, path);
  if (!target) {
    return { column: null, line: null };
  }
  return locationFromNode(target.node, target.lineCounter);
}

export function mapAgentManifestDiagnosticsForEditor(
  diagnostics: readonly AgentManifestDiagnostic[],
  options: {
    manifestSource?: string;
    origin?: AgentManifestDiagnosticOrigin;
  } = {},
): AgentManifestDiagnosticPanelItem[] {
  const origin = options.origin ?? "backend";

  return diagnostics.map((diagnostic, index) => {
    const sourceLocation =
      options.manifestSource && diagnostic.line === null
        ? locateAgentManifestPath(options.manifestSource, diagnostic.path)
        : { column: diagnostic.column, line: diagnostic.line };
    const mappedDiagnostic: AgentManifestEditorDiagnostic = {
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

export function formatAgentManifestYaml(source: string): AgentManifestFormatResult {
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
          error instanceof Error ? error.message : "Unable to format agent manifest YAML",
          "$",
          { column: null, line: null },
        ),
      ],
      formatted: null,
    };
  }
}

export type AgentManifestYamlNode = Node | YAMLMap | YAMLSeq;
