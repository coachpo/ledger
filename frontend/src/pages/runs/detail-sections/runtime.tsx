import { Activity } from "lucide-react";

import { ConsoleSection } from "@/components/shared/console-section";
import { EvidenceCluster } from "@/components/shared/evidence-cluster";
import { ResourceStatusStrip } from "@/components/shared/resource-status-strip";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDateTime } from "@/lib/format";
import type {
  RunModelGatewaySelectedStrategiesRead,
  RunModelGatewayUsageRead,
  RunPackageResolvedModelConnectionRead,
  RunRead,
  RunStepStatus,
} from "@/lib/types/run";
import type {
  ModelConnectionCapabilities,
  ModelConnectionCapabilityStatus,
  ModelConnectionOutputStrategyPolicy,
  ModelConnectionParallelToolCallsPolicy,
  ModelConnectionProtocolProfile,
  ModelConnectionReasoningPolicy,
  ModelConnectionStreamingPolicy,
} from "@/lib/types/model-connection";

import { formatQueueReasonTitle, runStatusTone, sortedInvocations } from "../detail-helpers";
import {
  CompactModeEmptyState,
  RunDetailEmptyState,
  RunDetailSectionBlock,
  RunDetailTableFrame,
  statusVariant,
  type DetailItem,
} from "./shared";

const PROTOCOL_PROFILE_LABELS: Record<ModelConnectionProtocolProfile, string> =
  {
    openai_chat_completions: "Chat Completions-compatible",
    openai_responses: "Responses-compatible",
  };

const OUTPUT_STRATEGY_POLICY_LABELS: Record<
  ModelConnectionOutputStrategyPolicy,
  string
> = {
  allow_json_object_validation: "Allow JSON object validation",
  allow_plain_text: "Allow plain text",
  prefer_strict_schema: "Prefer strict schema",
  require_strict_schema: "Require strict schema",
};

const PARALLEL_TOOL_CALLS_POLICY_LABELS: Record<
  ModelConnectionParallelToolCallsPolicy,
  string
> = {
  allow: "Allow parallel calls",
  forbid: "Forbid parallel calls",
  serialize: "Serialize calls",
};

const REASONING_POLICY_LABELS: Record<ModelConnectionReasoningPolicy, string> =
  {
    allow: "Allow reasoning",
    forbid: "Forbid reasoning",
  };

const STREAMING_POLICY_LABELS: Record<ModelConnectionStreamingPolicy, string> =
  {
    allow: "Allow streaming",
    forbid: "Forbid streaming",
  };

export const CAPABILITY_ORDER: (keyof ModelConnectionCapabilities)[] = [
  "textGeneration",
  "chatCompletions",
  "responsesApi",
  "streaming",
  "nativeToolCalls",
  "parallelToolCalls",
  "jsonObjectOutput",
  "strictJsonSchemaOutput",
  "reasoningHints",
  "usageReporting",
  "systemMessages",
];

export const CAPABILITY_LABELS: Record<keyof ModelConnectionCapabilities, string> = {
  textGeneration: "Text generation",
  chatCompletions: "Chat completions",
  responsesApi: "Responses API",
  streaming: "Streaming",
  nativeToolCalls: "Native tool calls",
  parallelToolCalls: "Parallel tool calls",
  jsonObjectOutput: "JSON object output",
  strictJsonSchemaOutput: "Strict JSON schema output",
  reasoningHints: "Reasoning hints",
  usageReporting: "Usage reporting",
  systemMessages: "System messages",
};

function capabilityStatusLabel(
  status: ModelConnectionCapabilityStatus,
): string {
  if (status === "supported") {
    return "Supported";
  }
  if (status === "unsupported") {
    return "Unsupported";
  }
  if (status === "notApplicable") {
    return "Not applicable";
  }
  return "Unknown";
}

function capabilityStatusVariant(
  status: ModelConnectionCapabilityStatus,
): "secondary" | "destructive" | "outline" {
  if (status === "supported") {
    return "secondary";
  }
  if (status === "unsupported") {
    return "destructive";
  }
  return "outline";
}

function runtimeConnectionKindLabel(
  value: RunPackageResolvedModelConnectionRead["connectionKind"],
): string {
  return value === "deterministic_smoke"
    ? "Deterministic smoke"
    : "Provider-backed";
}

type RuntimeStrategySummary = {
  agentLabel: string;
  invocationId: number;
  key: string;
  status: RunStepStatus;
  stepIndex: number;
  strategies: RunModelGatewaySelectedStrategiesRead | null;
  usage: RunModelGatewayUsageRead | null;
};

type RuntimeCapabilityCounts = Record<ModelConnectionCapabilityStatus, number>;

const RUNTIME_AUDIT_STRATEGY_LIMIT = 20;

function formatRuntimeStrategyValue(value: unknown): string {
  if (value === true) {
    return "Enabled";
  }
  if (value === false) {
    return "Disabled";
  }
  if (typeof value === "string" && value.trim()) {
    return value.replaceAll("_", " ");
  }
  if (typeof value === "number") {
    return String(value);
  }
  return "Not recorded";
}

function strategyItems(
  strategies: RunModelGatewaySelectedStrategiesRead | null,
): DetailItem[] {
  return [
    {
      label: "Output strategy",
      value: formatRuntimeStrategyValue(strategies?.outputStrategy),
    },
    {
      label: "Tool call strategy",
      value: formatRuntimeStrategyValue(strategies?.toolCallStrategy),
    },
    {
      label: "Parallel tool calls",
      value: formatRuntimeStrategyValue(strategies?.parallelToolCalls),
    },
    {
      label: "Reasoning strategy",
      value: formatRuntimeStrategyValue(strategies?.reasoningStrategy),
    },
    {
      label: "Reasoning effort",
      value: formatRuntimeStrategyValue(strategies?.reasoningEffort),
    },
    {
      label: "Streaming strategy",
      value: formatRuntimeStrategyValue(strategies?.streamingStrategy),
    },
  ];
}

function usageItems(usage: RunModelGatewayUsageRead | null): DetailItem[] {
  return [
    {
      label: "Input tokens",
      value: formatRuntimeStrategyValue(usage?.inputTokens),
    },
    {
      label: "Output tokens",
      value: formatRuntimeStrategyValue(usage?.outputTokens),
    },
    {
      label: "Total tokens",
      value: formatRuntimeStrategyValue(usage?.totalTokens),
    },
  ];
}

function runtimeStrategySummaries(run: RunRead): RuntimeStrategySummary[] {
  return run.steps.flatMap((step) =>
    sortedInvocations(step.invocations)
      .map((invocation) => {
        const gatewayMetadata = invocation.graphMetadata?.modelGateway;
        const strategies = gatewayMetadata?.selectedStrategies ?? null;
        const usage = gatewayMetadata?.usage ?? null;
        if (!strategies && !usage) {
          return null;
        }
        return {
          agentLabel: `${invocation.agentKey}@${invocation.agentVersion}`,
          invocationId: invocation.id,
          key: `${step.index}-${invocation.id}`,
          status: invocation.status,
          stepIndex: step.index,
          strategies,
          usage,
        } satisfies RuntimeStrategySummary;
      })
      .filter((item): item is RuntimeStrategySummary => item !== null),
  );
}

function runtimeInvocationTokenRows(run: RunRead) {
  return run.steps.flatMap((step) =>
    sortedInvocations(step.invocations)
      .filter((invocation) => invocation.tokens > 0)
      .map((invocation) => ({
        agentLabel: `${invocation.agentKey}@${invocation.agentVersion}`,
        invocationId: invocation.id,
        key: `${step.index}-${invocation.id}`,
        slot: invocation.slot,
        status: invocation.status,
        stepIndex: step.index,
        tokens: invocation.tokens,
      })),
  );
}

function runtimeCapabilityCounts(
  connection: RunPackageResolvedModelConnectionRead,
): RuntimeCapabilityCounts {
  return CAPABILITY_ORDER.reduce<RuntimeCapabilityCounts>(
    (counts, capabilityKey) => {
      const status = connection.capabilities[capabilityKey].status;
      counts[status] += 1;
      return counts;
    },
    { notApplicable: 0, supported: 0, unknown: 0, unsupported: 0 },
  );
}

function formatRuntimeCapabilitySummary(
  connection: RunPackageResolvedModelConnectionRead,
): string {
  const counts = runtimeCapabilityCounts(connection);
  return `${counts.supported} supported · ${counts.unsupported} unsupported · ${counts.unknown} unknown · ${counts.notApplicable} not applicable`;
}

export function RunRuntimeProfileSection({ run }: { run: RunRead }) {
  const provenance = run.packageProvenance;
  if (run.targetKind !== "workflowPackage" || !provenance) {
    return (
      <RunDetailSectionBlock
        blockId="runtime-profile"
        description="Runtime profile data is only recorded for Workflow Package runs."
        icon={Activity}
        title="Runtime profile"
      >
        <RunDetailEmptyState testId="runs-runtime-profile-empty">
          No runtime profile was recorded for this run.
        </RunDetailEmptyState>
      </RunDetailSectionBlock>
    );
  }

  const resolvedModelConnections = provenance.resolvedModelConnections;
  const strategySummaries = runtimeStrategySummaries(run);
  const visibleStrategySummaries = strategySummaries.slice(
    0,
    RUNTIME_AUDIT_STRATEGY_LIMIT,
  );
  const hiddenStrategyCount = Math.max(
    0,
    strategySummaries.length - visibleStrategySummaries.length,
  );

  return (
    <div className="grid min-w-0 gap-3" data-testid="runs-runtime-profile">
      <RunDetailSectionBlock
        blockId="runtime-profile"
        description="Frozen provider, model, policy, and capability rows captured when the run executed."
        icon={Activity}
        title="Runtime profile"
      >
        {resolvedModelConnections.length === 0 ? (
          <RunDetailEmptyState testId="runs-runtime-provider-empty">
            No resolved model connections were recorded for this run.
          </RunDetailEmptyState>
        ) : (
          <RunDetailTableFrame testId="runs-runtime-provider-rows">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Provider/model</TableHead>
                  <TableHead>Protocol</TableHead>
                  <TableHead>Capabilities</TableHead>
                  <TableHead>Policies</TableHead>
                  <TableHead>Execution settings</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {resolvedModelConnections.map((connection) => (
                  <TableRow
                    data-testid={`runs-runtime-profile-connection-${connection.key}`}
                    key={connection.key}
                  >
                    <TableCell className="min-w-56 whitespace-normal align-top">
                      <div className="flex min-w-0 flex-col gap-1">
                        <span className="font-medium text-foreground">
                          {connection.name}
                        </span>
                        <span className="break-all text-xs text-muted-foreground">
                          {connection.key}
                        </span>
                        <span className="break-all text-xs text-muted-foreground">
                          {connection.modelId}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="whitespace-normal align-top">
                      <div className="flex flex-wrap gap-1.5">
                        <Badge variant="outline">
                          {runtimeConnectionKindLabel(
                            connection.connectionKind,
                          )}
                        </Badge>
                        <Badge variant="secondary">
                          {PROTOCOL_PROFILE_LABELS[connection.protocolProfile]}
                        </Badge>
                        <Badge
                          variant={
                            connection.hasApiKey ? "secondary" : "outline"
                          }
                        >
                          {connection.hasApiKey
                            ? "Credential present"
                            : "No credential"}
                        </Badge>
                      </div>
                    </TableCell>
                    <TableCell className="min-w-52 whitespace-normal align-top text-muted-foreground">
                      {formatRuntimeCapabilitySummary(connection)}
                    </TableCell>
                    <TableCell className="min-w-64 whitespace-normal align-top text-muted-foreground">
                      {[
                        OUTPUT_STRATEGY_POLICY_LABELS[
                          connection.outputStrategyPolicy
                        ],
                        PARALLEL_TOOL_CALLS_POLICY_LABELS[
                          connection.parallelToolCallsPolicy
                        ],
                        REASONING_POLICY_LABELS[connection.reasoningPolicy],
                        STREAMING_POLICY_LABELS[connection.streamingPolicy],
                      ].join(" · ")}
                    </TableCell>
                    <TableCell className="min-w-48 whitespace-normal align-top text-muted-foreground">
                      {connection.timeoutSeconds}s timeout · reasoning{" "}
                      {connection.reasoningEffort ?? "omitted"} · probe TTL{" "}
                      {connection.probeCacheTtlSeconds}s
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </RunDetailTableFrame>
        )}
      </RunDetailSectionBlock>

      <RunDetailSectionBlock
        blockId="selected-strategies"
        description="Adapter-selected strategy metadata is repeated invocation evidence, so it stays in rows."
        icon={Activity}
        title="Selected strategies"
      >
        {strategySummaries.length === 0 ? (
          <RunDetailEmptyState testId="runs-runtime-strategy-empty">
            No adapter-selected strategy metadata was recorded for this run.
          </RunDetailEmptyState>
        ) : (
          <div className="grid min-w-0 gap-2">
            {hiddenStrategyCount > 0 ? (
              <p className="text-xs text-muted-foreground">
                Showing the first {visibleStrategySummaries.length} of{" "}
                {strategySummaries.length} invocation records.
              </p>
            ) : null}
            <RunDetailTableFrame>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Invocation</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Strategies</TableHead>
                    <TableHead>Usage</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {visibleStrategySummaries.map((summary) => (
                    <TableRow
                      data-testid={`runs-runtime-strategy-${summary.key}`}
                      key={summary.key}
                    >
                      <TableCell className="min-w-48 whitespace-normal align-top">
                        <div className="flex min-w-0 flex-col gap-1">
                          <span className="font-medium text-foreground">
                            {summary.agentLabel}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            Step {summary.stepIndex} · Invocation #
                            {summary.invocationId}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="align-top">
                        <Badge variant={statusVariant(summary.status)}>
                          {summary.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="min-w-80 whitespace-normal align-top text-muted-foreground">
                        {strategyItems(summary.strategies)
                          .map((item) => `${item.label}: ${item.value}`)
                          .join(" · ")}
                      </TableCell>
                      <TableCell className="min-w-52 whitespace-normal align-top text-muted-foreground">
                        {summary.usage
                          ? usageItems(summary.usage)
                              .map((item) => `${item.label}: ${item.value}`)
                              .join(" · ")
                          : "Usage not recorded"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </RunDetailTableFrame>
          </div>
        )}
      </RunDetailSectionBlock>

      <RunDetailSectionBlock
        blockId="capability-matrix"
        description="Capability probes are row-first so repeated provider evidence stays comparable."
        icon={Activity}
        title="Capability matrix"
      >
        {resolvedModelConnections.length === 0 ? (
          <RunDetailEmptyState testId="runs-runtime-capability-empty">
            No capability probes were recorded.
          </RunDetailEmptyState>
        ) : (
          <RunDetailTableFrame testId="runs-runtime-capability-matrix">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Provider</TableHead>
                  <TableHead>Capability</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Probe detail</TableHead>
                  <TableHead>Last probed</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {resolvedModelConnections.flatMap((connection) =>
                  CAPABILITY_ORDER.map((capabilityKey) => {
                    const state = connection.capabilities[capabilityKey];
                    return (
                      <TableRow
                        data-testid={`runs-runtime-capability-${connection.key}-${capabilityKey}`}
                        key={`${connection.key}-${capabilityKey}`}
                      >
                        <TableCell className="whitespace-normal align-top font-medium">
                          {connection.name}
                        </TableCell>
                        <TableCell className="whitespace-normal align-top">
                          {CAPABILITY_LABELS[capabilityKey]}
                        </TableCell>
                        <TableCell className="align-top">
                          <Badge
                            variant={capabilityStatusVariant(state.status)}
                          >
                            {capabilityStatusLabel(state.status)}
                          </Badge>
                        </TableCell>
                        <TableCell className="min-w-72 whitespace-normal align-top text-muted-foreground">
                          {state.detail || "No probe detail recorded."}
                        </TableCell>
                        <TableCell className="whitespace-normal align-top text-muted-foreground">
                          {state.lastProbedAt
                            ? formatDateTime(state.lastProbedAt)
                            : "Not recorded"}
                        </TableCell>
                      </TableRow>
                    );
                  }),
                )}
              </TableBody>
            </Table>
          </RunDetailTableFrame>
        )}
      </RunDetailSectionBlock>
    </div>
  );
}

export function RunContextStrip({
  allInvocationsCount,
  run,
  runProgress,
  targetKindLabel,
  terminalInvocationsCount,
}: {
  allInvocationsCount: number;
  run: RunRead;
  runProgress: number;
  targetKindLabel: string;
  terminalInvocationsCount: number;
}) {
  const queueValue = run.queue
    ? `${run.queue.state} · ${formatQueueReasonTitle(run.queue.reason)}`
    : run.status === "queued"
      ? "Queued without queue detail"
      : "No queue hold";

  return (
    <section
      className="grid min-w-0 gap-3 text-sm"
      data-testid="runs-workspace-context"
    >
      <ConsoleSection
        description="Backend-owned progress, queue, status, and token truth for this immutable run snapshot."
        title="Summary"
      >
        <div className="flex min-w-0 flex-col gap-3">
          <ResourceStatusStrip
            items={[
              {
                label: "Status",
                value: run.status,
                tone: runStatusTone(run.status),
              },
              { label: "Target", value: targetKindLabel },
              {
                label: "Queue",
                value: queueValue,
                tone: run.queue ? "warning" : "muted",
              },
            ]}
          />
          <div className="min-w-0" data-testid="runs-summary-execution-row">
            <Badge
              data-testid="runs-detail-status"
              variant={statusVariant(run.status)}
            >
              {run.status}
            </Badge>{" "}
            <Badge data-testid="runs-detail-target-kind" variant="outline">
              {targetKindLabel}
            </Badge>{" "}
            <span className="min-w-0 break-words text-muted-foreground">
              {terminalInvocationsCount} of {allInvocationsCount} invocation(s)
              terminal.
            </span>
          </div>
          <div
            className="flex min-w-0 flex-col gap-2"
            data-testid="runs-summary-progress-row"
          >
            <div className="flex items-center justify-between gap-3 text-muted-foreground">
              <span>Run progress</span>
              <span className="font-medium text-foreground">
                {runProgress}%
              </span>
            </div>
            <Progress className="min-w-0" value={runProgress} />
          </div>
        </div>
      </ConsoleSection>

      <RunTokensWorkspace run={run} />
      <RunRuntimeProfileSection run={run} />
    </section>
  );
}

export function RunTokensWorkspace({ run }: { run: RunRead }) {
  const tokenRows = runtimeInvocationTokenRows(run);
  const strategySummaries = runtimeStrategySummaries(run).filter(
    (summary) => summary.usage,
  );
  const hasTokenAccounting = Boolean(
    run.totalTokens ||
    run.inheritedTokens ||
    run.executedTokens ||
    tokenRows.length > 0 ||
    strategySummaries.length > 0,
  );

  if (!hasTokenAccounting) {
    return (
      <section
        className="grid min-w-0 gap-3"
        data-testid="runs-tokens-workspace"
      >
        <RunDetailSectionBlock
          blockId="token-accounting"
          description="Token usage appears here when the backend reports run-level or invocation-level accounting."
          icon={Activity}
          title="Token accounting"
        >
          <CompactModeEmptyState testId="runs-tokens-empty">
            No token accounting was reported for this run.
          </CompactModeEmptyState>
        </RunDetailSectionBlock>
      </section>
    );
  }

  return (
    <section className="grid min-w-0 gap-3" data-testid="runs-tokens-workspace">
      <RunDetailSectionBlock
        blockId="token-accounting"
        description="Run-level accounting stays split across total, inherited, and newly executed usage."
        icon={Activity}
        title="Token accounting"
      >
        <div className="grid min-w-0 gap-3">
          <ResourceStatusStrip
            items={[
              { label: "Total", value: run.totalTokens.toLocaleString() },
              {
                label: "Executed",
                value: run.executedTokens.toLocaleString(),
                tone: run.executedTokens > 0 ? "success" : "muted",
              },
              {
                label: "Inherited",
                value: run.inheritedTokens.toLocaleString(),
                tone: run.inheritedTokens > 0 ? "warning" : "muted",
              },
            ]}
          />
          <EvidenceCluster
            items={[
              {
                label: "Read model total",
                value: run.totalTokens.toLocaleString(),
                description: "All usage counted on the run read model.",
              },
              {
                label: "Fresh execution",
                value: run.executedTokens.toLocaleString(),
                description: "Tokens generated by this run execution.",
              },
              {
                label: "Inherited context",
                value: run.inheritedTokens.toLocaleString(),
                description: run.sourceRunId
                  ? `Copied from upstream source run #${run.sourceRunId}.`
                  : "No upstream source run boundary.",
                tone: run.inheritedTokens > 0 ? "warning" : "neutral",
              },
            ]}
            layout="grid"
          />
          <dl className="sr-only" data-testid="runs-summary-usage-row">
            <div>
              <dt>Total tokens</dt>
              <dd>{run.totalTokens}</dd>
            </div>
            <div>
              <dt>Inherited tokens</dt>
              <dd>{run.inheritedTokens}</dd>
            </div>
            <div>
              <dt>Executed tokens</dt>
              <dd>{run.executedTokens}</dd>
            </div>
          </dl>
        </div>
      </RunDetailSectionBlock>

      <RunDetailSectionBlock
        blockId="invocation-usage-rows"
        description="Per-invocation token fields and provider usage metadata stay row-based for auditability."
        icon={Activity}
        title="Invocation usage rows"
      >
        {tokenRows.length === 0 && strategySummaries.length === 0 ? (
          <CompactModeEmptyState testId="runs-tokens-rows-empty">
            No invocation-level token rows were recorded; only run-level
            accounting is available.
          </CompactModeEmptyState>
        ) : (
          <RunDetailTableFrame>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Invocation</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Run tokens</TableHead>
                  <TableHead>Gateway usage</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {tokenRows.map((row) => {
                  const gatewayUsage = strategySummaries.find(
                    (summary) => summary.key === row.key,
                  )?.usage;
                  return (
                    <TableRow
                      data-testid={`runs-token-row-${row.key}`}
                      key={row.key}
                    >
                      <TableCell className="min-w-52 whitespace-normal align-top">
                        <div className="flex min-w-0 flex-col gap-1">
                          <span className="font-medium text-foreground">
                            {row.agentLabel}
                          </span>
                          <span className="text-xs text-muted-foreground">
                            Step {row.stepIndex} · {row.slot} · Invocation #
                            {row.invocationId}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="align-top">
                        <Badge variant={statusVariant(row.status)}>
                          {row.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="align-top text-muted-foreground">
                        {row.tokens.toLocaleString()}
                      </TableCell>
                      <TableCell className="min-w-64 whitespace-normal align-top text-muted-foreground">
                        {gatewayUsage
                          ? usageItems(gatewayUsage)
                              .map((item) => `${item.label}: ${item.value}`)
                              .join(" · ")
                          : "Gateway usage not recorded"}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </RunDetailTableFrame>
        )}
      </RunDetailSectionBlock>
    </section>
  );
}
