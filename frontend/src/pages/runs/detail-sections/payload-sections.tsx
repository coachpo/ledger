import { StructuredValueInspector } from "@/components/platform-authoring/inspectors/structured-value-inspector";
import { ResourceStatusStrip } from "@/components/shared/resource-status-strip";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { RunRead } from "@/lib/types/run";

import { formatQueueReasonTitle, type TraceSpanEntry } from "../detail-helpers";
import {
  DetailGrid,
  RunDetailContentSection,
  RunDetailEmptyState,
} from "./shared";

function formatRawPayload(value: unknown): string {
  return JSON.stringify(value, null, 2) ?? "";
}

function RawPayloadBlock({
  testId,
  value,
}: {
  testId?: string;
  value: unknown;
}) {
  return (
    <pre
      className="max-w-full overflow-x-auto whitespace-pre rounded-lg border border-border/70 bg-ui-surface-inset p-3 text-xs shadow-inner shadow-black/[0.02] dark:shadow-black/20"
      data-testid={testId}
      data-wide-payload="scroll"
    >
      {formatRawPayload(value)}
    </pre>
  );
}

function PayloadViewTabs({
  label,
  testId,
  value,
}: {
  label: string;
  testId?: string;
  value: unknown;
}) {
  return (
    <Tabs
      defaultValue="rendered"
      className="min-w-0 gap-3"
      data-testid={testId}
    >
      <div
        className="max-w-full overflow-x-auto pb-1"
        data-testid={testId ? `${testId}-tab-scroll` : undefined}
      >
        <TabsList
          aria-label={`${label} payload view modes`}
          className="h-8 rounded-lg"
        >
          <TabsTrigger className="rounded-md px-2 text-xs" value="rendered">
            Rendered
          </TabsTrigger>
          <TabsTrigger className="rounded-md px-2 text-xs" value="raw">
            Raw
          </TabsTrigger>
        </TabsList>
      </div>
      <TabsContent className="min-w-0" value="rendered">
        <StructuredValueInspector
          className="min-w-0 rounded-lg border border-border/70 bg-ui-surface-inset p-3 text-sm shadow-inner shadow-black/[0.02] dark:shadow-black/20"
          data-testid={testId ? `${testId}-rendered` : undefined}
          enableMarkdownStringPreview
          label={null}
          preserveObjectKeyOrder
          presentation="tree"
          value={value}
        />
      </TabsContent>
      <TabsContent className="min-w-0" value="raw">
        <RawPayloadBlock
          testId={testId ? `${testId}-raw` : undefined}
          value={value}
        />
      </TabsContent>
    </Tabs>
  );
}

export function JsonBlock({
  label,
  testId,
  value,
}: {
  label?: string;
  testId?: string;
  value: unknown;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-2">
      {label ? <p className="text-sm font-medium">{label}</p> : null}
      <PayloadViewTabs
        label={label ?? "Payload"}
        testId={testId}
        value={value}
      />
    </div>
  );
}

export function RunPayloadPane({
  label,
  testId,
  value,
}: {
  label: string;
  testId: string;
  value: unknown;
}) {
  return (
    <section aria-label={label} className="flex min-w-0 flex-col gap-3">
      <PayloadViewTabs label={label} testId={testId} value={value} />
    </section>
  );
}

function CompactDetailValue({
  description,
  value,
}: {
  description?: string;
  value: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="break-words">{value}</div>
      {description ? (
        <p className="text-xs leading-5 text-muted-foreground">
          {description}
        </p>
      ) : null}
    </div>
  );
}

export function RunFinalOutputPane({ run }: { run: RunRead }) {
  return (
    <RunDetailContentSection
      contentClassName="flex flex-col gap-5"
      description="Rendered payload view for the immutable run result."
      sectionId="final-output"
      testId="runs-detail-final-output-card"
      title="Final output"
    >
      {run.finalOutput !== null ? (
        <RunPayloadPane
          label="Final output"
          testId="runs-detail-final-output"
          value={run.finalOutput}
        />
      ) : (
        <section aria-label="Final output" className="flex flex-col gap-3">
          <RunDetailEmptyState testId="runs-detail-final-output">
            No final output payload was recorded for this run.
          </RunDetailEmptyState>
        </section>
      )}
    </RunDetailContentSection>
  );
}

export function RunOutputWorkspace({ run }: { run: RunRead }) {
  const provenance = run.packageProvenance;

  return (
    <div className="grid min-w-0 gap-3" data-testid="runs-output-workspace">
      <RunDetailContentSection
        description="Output provenance stays beside the rendered payload without duplicating final output detail."
        sectionId="output-provenance"
        testId="runs-detail-section-output-provenance"
        title="Output provenance"
      >
        <DetailGrid
          items={[
            {
              label: "Workflow",
              value: (
                <CompactDetailValue
                  description={
                    provenance?.workflowKey ?? run.targetKey ?? "Not recorded"
                  }
                  value={provenance?.workflowName ?? "Snapshot workflow"}
                />
              ),
            },
          ]}
        />
      </RunDetailContentSection>
    </div>
  );
}

export function RunInputWorkspace({ run }: { run: RunRead }) {
  const provenance = run.packageProvenance;

  return (
    <div className="grid min-w-0 gap-3" data-testid="runs-input-workspace">
      <RunDetailContentSection
        contentClassName="flex flex-col gap-5"
        description="Launch payload captured with the immutable run snapshot."
        sectionId="run-input"
        testId="runs-detail-input-card"
        title="Run input"
      >
        <RunPayloadPane
          label="Run input"
          testId="runs-detail-input"
          value={run.input}
        />
      </RunDetailContentSection>
      <RunDetailContentSection
        description="Input provenance stays beside the launch payload without duplicating run input detail."
        sectionId="input-provenance"
        testId="runs-detail-section-input-provenance"
        title="Input provenance"
      >
        <DetailGrid
          items={[
            {
              label: "Workflow",
              value: (
                <CompactDetailValue
                  description={
                    provenance?.workflowKey ?? run.targetKey ?? "Not recorded"
                  }
                  value={provenance?.workflowName ?? "Snapshot workflow"}
                />
              ),
            },
            {
              label: "Target",
              value: (
                <CompactDetailValue
                  description={`Run #${run.id} launch snapshot`}
                  value={run.targetKey}
                />
              ),
            },
          ]}
        />
      </RunDetailContentSection>
    </div>
  );
}

export function RunOverviewWorkspace({
  allInvocationsCount,
  run,
  runProgress,
  targetKindLabel,
  terminalInvocationsCount,
  traceSpanEntries,
}: {
  allInvocationsCount: number;
  run: RunRead;
  runProgress: number;
  targetKindLabel: string;
  terminalInvocationsCount: number;
  traceSpanEntries: TraceSpanEntry[];
}) {
  const queueValue = run.queue
    ? `${run.queue.state} · ${formatQueueReasonTitle(run.queue.reason)}`
    : run.status === "queued"
      ? "Queued without queue detail"
      : "No queue hold";

  return (
    <section
      className="grid min-w-0 gap-3"
      data-testid="runs-overview-workspace"
    >
      <RunDetailContentSection
        description="Operational availability and progress cues for this immutable run snapshot."
        sectionId="operational-overview"
        testId="runs-detail-section-operational-overview"
        title="Operational overview"
      >
        <div className="flex min-w-0 flex-col gap-3">
          <div className="sr-only" data-testid="runs-summary-execution-row">
            <span data-testid="runs-detail-status">{run.status}</span>
            <span data-testid="runs-detail-target-kind">{targetKindLabel}</span>
            <span>
              {terminalInvocationsCount} of {allInvocationsCount} invocation(s)
              terminal.
            </span>
          </div>
          <ResourceStatusStrip
            items={[
              {
                label: "Queue",
                value: queueValue,
                tone: run.queue ? "warning" : "muted",
              },
              {
                label: "Invocations",
                value: `${terminalInvocationsCount} of ${allInvocationsCount} invocation(s) terminal`,
              },
              {
                label: "Trace",
                value: run.traceId ?? `${traceSpanEntries.length} span(s)`,
                tone:
                  run.traceId || traceSpanEntries.length > 0
                    ? "success"
                    : "warning",
              },
            ]}
          />
          <div
            className="flex min-w-0 flex-col gap-2"
            data-testid="runs-summary-progress-row"
          >
            <div className="flex items-center justify-between gap-3 text-sm text-muted-foreground">
              <span>Run progress</span>
              <span className="font-medium text-foreground">
                {runProgress}%
              </span>
            </div>
            <Progress className="min-w-0" value={runProgress} />
          </div>
        </div>
      </RunDetailContentSection>
    </section>
  );
}

export function RunEvidenceAvailabilitySection({ run }: { run: RunRead }) {
  const providerCount =
    run.packageProvenance?.resolvedModelConnections.length ?? 0;

  return (
    <RunDetailContentSection
      description="Evidence availability without opening the secondary evidence modes."
      sectionId="evidence-availability"
      testId="runs-detail-section-evidence-availability"
      title="Evidence availability"
    >
      <DetailGrid
        items={[
          {
            label: "Runtime",
            value: (
              <CompactDetailValue
                description="Open Runtime for provider and capability rows."
                value={`${providerCount} provider/model row${providerCount === 1 ? "" : "s"}`}
              />
            ),
          },
          {
            label: "Usage",
            value: (
              <CompactDetailValue
                description={`${run.inheritedTokens.toLocaleString()} inherited tokens copied into this snapshot.`}
                value={`${run.executedTokens.toLocaleString()} executed tokens`}
              />
            ),
          },
        ]}
      />
    </RunDetailContentSection>
  );
}
