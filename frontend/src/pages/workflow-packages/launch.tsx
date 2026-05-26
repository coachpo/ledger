import {
  AlertCircle,
  FileCheck2,
  Loader2,
  PlayCircle,
  Save,
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { ConsoleSection } from "@/components/shared/console-section";
import { ConstraintInspector } from "@/components/shared/constraint-inspector";
import { EvidenceCluster } from "@/components/shared/evidence-cluster";
import { PageContextBar } from "@/components/shared/page-context-bar";
import { ResourceStatusStrip } from "@/components/shared/resource-status-strip";
import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  useCreateWorkflowPackageLaunch,
  useCreateWorkflowPackageRuntimeInputPersonalEntry,
  useDeleteWorkflowPackageRuntimeInputPersonalEntry,
  usePreflightWorkflowPackage,
  useUpdateWorkflowPackageRuntimeInputPersonalEntry,
  useWorkflowPackage,
  useWorkflowPackageLaunch,
  useWorkflowPackageRuntimeInputRegistry,
} from "@/hooks/use-workflow-packages";
import { ApiRequestError } from "@/lib/api-client";
import { formatDateTime } from "@/lib/format";
import { stringifyJson } from "@/lib/platform-authoring/common/serialization";
import {
  createLaunchParametersTemplate,
  parseLaunchParametersJson,
  resetLaunchParametersTemplate,
} from "@/lib/platform-authoring/schema/schema-template";
import type { ApiErrorDetail, UnknownRecord } from "@/lib/types/common";
import type { ModelConnectionKind } from "@/lib/types/model-connection";
import type {
  WorkflowPackageLaunchRead,
  WorkflowPackageRead,
  WorkflowPackageRuntimeInputEntryRead,
} from "@/lib/types/workflow-package";

type PackageDiagnostic = {
  connectionKind?: ModelConnectionKind;
  field: string;
  issue: string;
  severity: "error" | "warning";
};

type SavedInputEntryMode = "history" | "personal";

const SAVED_INPUT_ENTRY_LIMIT = 20;

const CONNECTION_KIND_LABELS: Record<ModelConnectionKind, string> = {
  deterministic_smoke: "Deterministic smoke",
  provider: "Provider-backed",
};

function validPackageId(value: string | undefined): string | null {
  const trimmed = value?.trim();
  return trimmed && /^[1-9]\d*$/.test(trimmed) ? trimmed : null;
}

function isUnknownRecord(value: unknown): value is UnknownRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
function stringValue(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function modelConnectionKindValue(value: unknown): ModelConnectionKind | null {
  return value === "provider" || value === "deterministic_smoke" ? value : null;
}

function connectionKindLabel(
  value: ModelConnectionKind | null | undefined,
): string {
  return CONNECTION_KIND_LABELS[value ?? "provider"];
}

function diagnosticFromRecord(
  value: unknown,
  severity: "error" | "warning",
): PackageDiagnostic {
  const record = isUnknownRecord(value) ? value : {};
  const field = stringValue(record.field) || stringValue(record.path) || "$";
  const connectionKind = modelConnectionKindValue(record.connectionKind);
  return {
    ...(connectionKind ? { connectionKind } : {}),
    field,
    issue:
      stringValue(record.issue) ||
      stringValue(record.message) ||
      "Review this package diagnostic.",
    severity,
  };
}

function diagnosticsFromLaunch(
  read: WorkflowPackageLaunchRead | undefined,
): PackageDiagnostic[] {
  if (!read) {
    return [];
  }
  const blockingErrors = Array.isArray(read.blockingErrors)
    ? read.blockingErrors
    : [];
  const warnings = Array.isArray(read.warnings) ? read.warnings : [];
  return [
    ...blockingErrors.map((diagnostic) =>
      diagnosticFromRecord(diagnostic, "error"),
    ),
    ...warnings.map((diagnostic) =>
      diagnosticFromRecord(diagnostic, "warning"),
    ),
  ];
}

function diagnosticBadge(diagnostic: PackageDiagnostic) {
  return diagnostic.severity === "error" ? (
    <Badge variant="destructive">Blocking</Badge>
  ) : (
    <Badge
      className="border-chart-3/30 bg-chart-3/10 text-chart-3"
      variant="outline"
    >
      Warning
    </Badge>
  );
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function isNotFoundError(error: unknown): boolean {
  return error instanceof ApiRequestError && error.status === 404;
}

function newestRuntimeInputEntries(
  entries: readonly WorkflowPackageRuntimeInputEntryRead[],
  timestampKey: "createdAt" | "updatedAt",
): WorkflowPackageRuntimeInputEntryRead[] {
  return [...entries].sort((left, right) => {
    const timestampDelta =
      Date.parse(right[timestampKey]) - Date.parse(left[timestampKey]);
    return timestampDelta === 0 ? right.id - left.id : timestampDelta;
  });
}

function savedInputEntryLabel(
  entry: WorkflowPackageRuntimeInputEntryRead,
  mode: SavedInputEntryMode,
) {
  const name = entry.name?.trim();
  if (name) {
    return name;
  }
  if (mode === "history" && entry.sourceRunId) {
    return `Run #${entry.sourceRunId}`;
  }
  return mode === "history" ? `History #${entry.id}` : `Preset #${entry.id}`;
}

function LaunchPageSkeleton() {
  return (
    <WorkspacePageShell
      bodyAriaLabel="Workflow package launch loading workspace"
      bodyClassName="gap-4"
      contextBar={<Skeleton className="h-24 w-full" />}
      testId="workflow-package-launch-page"
    >
      <Skeleton className="h-44 w-full" />
      <Skeleton className="h-96 w-full" />
    </WorkspacePageShell>
  );
}
function LaunchPageMessage({
  actionHref = "/workflow-packages",
  actionLabel = "Back to workflow packages",
  description,
  title,
}: {
  actionHref?: string;
  actionLabel?: string;
  description: string;
  title: string;
}) {
  return (
    <WorkspacePageShell
      bodyAriaLabel="Workflow package launch message workspace"
      bodyClassName="gap-4"
      contextBar={
        <PageContextBar
          description="Open a saved workflow package before queueing a run."
          title="Launch Workflow Package"
        />
      }
      testId="workflow-package-launch-page"
    >
      <Card
        className="min-w-0 border-destructive/30 bg-destructive/5 shadow-sm"
        data-testid="workflow-package-launch-error"
      >
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <AlertCircle className="size-5" />
            {title}
          </CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild size="sm" variant="outline">
            <Link to={actionHref}>{actionLabel}</Link>
          </Button>
        </CardContent>
      </Card>
    </WorkspacePageShell>
  );
}

function RuntimeInputValidationAlert({
  errors,
}: {
  errors: readonly ApiErrorDetail[];
}) {
  if (errors.length === 0) {
    return null;
  }

  return (
    <Alert
      data-testid="runtime-input-validation-feedback"
      variant="destructive"
    >
      <AlertCircle />
      <AlertTitle>Runtime inputs need attention</AlertTitle>
      <AlertDescription>
        <ul className="list-disc space-y-1 pl-5">
          {errors.map((error) => (
            <li
              className="min-w-0 break-words"
              key={`${error.field}-${error.issue}`}
            >
              <code className="break-all rounded bg-muted/40 px-1 py-0.5 text-xs">
                {error.field}
              </code>
              : {error.issue}
            </li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}

function DiagnosticConstraintItem({
  diagnostic,
}: {
  diagnostic: PackageDiagnostic;
}) {
  return (
    <div className="grid min-w-0 gap-2 rounded-lg border bg-background/70 p-3 text-sm md:grid-cols-[auto_minmax(0,12rem)_minmax(0,1fr)] md:items-center">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        {diagnosticBadge(diagnostic)}
        {diagnostic.connectionKind ? (
          <Badge
            variant={
              diagnostic.connectionKind === "deterministic_smoke"
                ? "secondary"
                : "outline"
            }
          >
            {connectionKindLabel(diagnostic.connectionKind)}
          </Badge>
        ) : null}
      </div>
      <code className="min-w-0 break-all rounded bg-muted/40 px-2 py-1 text-xs">
        {diagnostic.field}
      </code>
      <span className="min-w-0 break-words text-muted-foreground">
        {diagnostic.issue}
      </span>
    </div>
  );
}

function diagnosticConstraintSection({
  diagnostics,
  emptyCopy,
  testId,
}: {
  diagnostics: readonly PackageDiagnostic[];
  emptyCopy?: string;
  testId: string;
}) {
  if (diagnostics.length === 0 && !emptyCopy) {
    return [];
  }

  return [
    <div className="min-w-0 space-y-2" data-testid={testId} key={testId}>
      {diagnostics.length === 0 ? (
        <p className="rounded-lg border border-dashed bg-background/60 p-3 text-sm text-muted-foreground">
          {emptyCopy}
        </p>
      ) : (
        diagnostics.map((diagnostic, diagnosticIndex) => (
          <DiagnosticConstraintItem
            diagnostic={diagnostic}
            key={`${diagnostic.severity}-${diagnostic.field}-${diagnostic.issue}-${diagnosticIndex}`}
          />
        ))
      )}
    </div>,
  ];
}

function ModelConnectionModeSummary({
  diagnostics,
  read,
}: {
  diagnostics: PackageDiagnostic[];
  read: WorkflowPackageLaunchRead | undefined;
}) {
  if (!read) {
    return null;
  }

  const smokeCount = diagnostics.filter(
    (diagnostic) => diagnostic.connectionKind === "deterministic_smoke",
  ).length;
  return (
    <div
      className="min-w-0 space-y-2 rounded-lg border bg-muted/20 p-3 text-sm text-muted-foreground"
      data-testid="workflow-package-model-connection-modes"
    >
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className="font-medium text-foreground">
          Model connection modes
        </span>
        <Badge variant="outline">{connectionKindLabel("provider")}</Badge>
        {smokeCount > 0 ? (
          <Badge variant="secondary">
            {connectionKindLabel("deterministic_smoke")}
          </Badge>
        ) : null}
      </div>
      <EvidenceCluster
        items={[
          {
            description: "Saved model connections remain the primary launch path.",
            label: "Provider",
            tone: "neutral",
            value: connectionKindLabel("provider"),
          },
          {
            description:
              smokeCount > 0
                ? "Offline deterministic launch paths are visible as warnings, not blockers."
                : "No deterministic smoke warnings were reported for this launch metadata.",
            label: "Smoke",
            tone: smokeCount > 0 ? "warning" : "verified",
            value: smokeCount,
          },
        ]}
        layout="grid"
      />
      <p>
        {smokeCount > 0
          ? `${smokeCount} deterministic smoke connection${smokeCount === 1 ? "" : "s"} will run offline; remaining saved model connections stay provider-backed.`
          : "No deterministic smoke warnings were reported; saved model connections are provider-backed for this launch metadata."}
      </p>
    </div>
  );
}

function SavedInputEntryRow(props: {
  deletePending: boolean;
  entry: WorkflowPackageRuntimeInputEntryRead;
  mode: SavedInputEntryMode;
  updatePending: boolean;
  onDelete: (entry: WorkflowPackageRuntimeInputEntryRead) => void;
  onLoad: (entry: WorkflowPackageRuntimeInputEntryRead) => void;
  onUpdate: (entry: WorkflowPackageRuntimeInputEntryRead) => void;
}) {
  const {
    deletePending,
    entry,
    mode,
    onDelete,
    onLoad,
    onUpdate,
    updatePending,
  } = props;
  const label = savedInputEntryLabel(entry, mode);
  const timestamp = mode === "history" ? entry.createdAt : entry.updatedAt;

  return (
    <div
      className="min-w-0 space-y-2 rounded-lg border bg-background/60 p-3"
      data-testid={`saved-input-${mode}-${entry.id}`}
    >
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <p className="min-w-0 max-w-full truncate text-sm font-medium">
              {label}
            </p>
            {entry.stale.stale ? (
              <Badge
                className="border-chart-3/30 bg-chart-3/10 text-chart-3"
                variant="outline"
              >
                Stale
              </Badge>
            ) : null}
          </div>
          <p className="text-xs text-muted-foreground">
            {mode === "history" ? "Captured" : "Updated"}{" "}
            {formatDateTime(timestamp)}
          </p>
        </div>
        <div className="flex w-full flex-wrap gap-2 sm:w-auto sm:justify-end">
          <Button
            className="h-7 px-2 text-xs"
            size="sm"
            type="button"
            variant="outline"
            aria-label={`Load ${mode} input ${label}`}
            onClick={() => onLoad(entry)}
          >
            Load
          </Button>
          {mode === "personal" ? (
            <>
              <Button
                className="h-7 px-2 text-xs"
                disabled={updatePending}
                size="sm"
                type="button"
                variant="outline"
                aria-label={`Overwrite personal input ${label}`}
                onClick={() => onUpdate(entry)}
              >
                {updatePending ? (
                  <Loader2 className="animate-spin" data-icon="inline-start" />
                ) : null}
                Overwrite
              </Button>
              <Button
                className="h-7 px-2 text-xs"
                disabled={deletePending}
                size="sm"
                type="button"
                variant="ghost"
                aria-label={`Delete personal input ${label}`}
                onClick={() => onDelete(entry)}
              >
                {deletePending ? (
                  <Loader2 className="animate-spin" data-icon="inline-start" />
                ) : (
                  <Trash2 className="size-3" data-icon="inline-start" />
                )}
                Delete
              </Button>
            </>
          ) : null}
        </div>
      </div>
      {entry.stale.stale ? (
        <div className="rounded-md border border-chart-3/30 bg-chart-3/10 px-2 py-1 text-xs text-muted-foreground">
          <p className="font-medium text-foreground">
            Saved against older workflow metadata.
          </p>
          {entry.stale.reasons.length > 0 ? (
            <ul className="mt-1 list-disc space-y-0.5 pl-4">
              {entry.stale.reasons.map((reason) => (
                <li key={`${entry.id}-${reason.field}-${reason.issue}`}>
                  {reason.field}: {reason.issue}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function LaunchIdentityContextBar({
  blockingCount,
  packageId,
  ready,
  warningCount,
  workflowPackage,
}: {
  blockingCount: number;
  packageId: string;
  ready: boolean;
  warningCount: number;
  workflowPackage: WorkflowPackageRead;
}) {
  const readinessLabel = ready
    ? "Ready to launch"
    : blockingCount > 0
      ? "Blocked"
      : "Review warnings";

  return (
    <div className="min-w-0" data-testid="workflow-package-launch-identity">
      <PageContextBar
        actions={
          <div
            className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row lg:justify-end"
            data-testid="workflow-package-launch-actions"
          >
            <Button
              asChild
              className="w-full sm:w-auto"
              size="sm"
              variant="outline"
            >
              <Link to={`/workflow-packages/${packageId}`}>
                Open authoring editor
              </Link>
            </Button>
          </div>
        }
        className="border-border/70 bg-card/95 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-card/85"
        description={
          workflowPackage.description ||
          "Queue a run from the currently persisted workflow package."
        }
        meta={
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <Badge variant="secondary">Saved package launch</Badge>
            <span className="font-medium text-foreground">
              {workflowPackage.name}
            </span>
            <span className="min-w-0 break-all font-mono">
              {workflowPackage.key}
            </span>
            <span>Package #{workflowPackage.id}</span>
          </div>
        }
        status={
          <ResourceStatusStrip
            items={[
              {
                label: "Readiness",
                tone: ready
                  ? "success"
                  : blockingCount > 0
                    ? "danger"
                    : "warning",
                value: readinessLabel,
              },
              {
                label: "Blocking",
                tone: blockingCount > 0 ? "danger" : "success",
                value: blockingCount,
              },
              {
                label: "Warnings",
                tone: warningCount > 0 ? "warning" : "success",
                value: warningCount,
              },
            ]}
          />
        }
        title="Launch Workflow Package"
      />
    </div>
  );
}

function LaunchContextCard({
  workflowPackage,
}: {
  workflowPackage: WorkflowPackageRead;
}) {
  return (
    <div data-testid="workflow-package-launch-context">
      <ConsoleSection
        description={`Read-only package identity and artifact context for package #${workflowPackage.id}.`}
        title="Package identity"
      >
        <EvidenceCluster
          items={[
            {
              description: "Persisted package key used for run provenance.",
              label: "Key",
              value: (
                <span className="break-all font-mono text-xs">
                  {workflowPackage.key}
                </span>
              ),
            },
            {
              description: "Saved package record selected by the route.",
              label: "Package",
              value: workflowPackage.name,
            },
            {
              description: "Manifest snapshot available for launch evidence.",
              label: "Manifest",
              tone: workflowPackage.manifestHash ? "verified" : "warning",
              value: (
                <span className="break-all font-mono text-xs">
                  {workflowPackage.manifestHash ?? "Not recorded"}
                </span>
              ),
            },
            {
              description: "Compiled artifact snapshot available for launch evidence.",
              label: "Compiled",
              tone: workflowPackage.compiledHash ? "verified" : "warning",
              value: (
                <span className="break-all font-mono text-xs">
                  {workflowPackage.compiledHash ?? "Not recorded"}
                </span>
              ),
            },
            {
              description: "Latest persisted package update.",
              label: "Updated",
              value: formatDateTime(workflowPackage.updatedAt),
            },
            {
              description: "Original package creation time.",
              label: "Created",
              value: formatDateTime(workflowPackage.createdAt),
            },
          ]}
        />
      </ConsoleSection>
    </div>
  );
}

function LaunchReadinessCard({
  blockingCount,
  diagnostics,
  isLoadingMetadata,
  metadataError,
  readinessRead,
  ready,
  warningCount,
  onPreflight,
  preflightPending,
}: {
  blockingCount: number;
  diagnostics: readonly PackageDiagnostic[];
  isLoadingMetadata: boolean;
  metadataError: unknown;
  readinessRead: WorkflowPackageLaunchRead | undefined;
  ready: boolean;
  warningCount: number;
  onPreflight: () => void;
  preflightPending: boolean;
}) {
  const blockingDiagnostics = diagnostics.filter(
    (diagnostic) => diagnostic.severity === "error",
  );
  const warningDiagnostics = diagnostics.filter(
    (diagnostic) => diagnostic.severity === "warning",
  );
  const readinessLabel = ready
    ? "Ready to launch"
    : blockingCount > 0
      ? "Needs attention"
      : warningCount > 0
        ? "Ready with warnings"
        : "Awaiting launch metadata";
  const readinessDescription = readinessRead
    ? blockingCount > 0
      ? `${readinessRead.packageKey} · Blocked by launch diagnostics`
      : readinessRead.packageKey
    : "Launch metadata has not loaded yet.";

  return (
    <div data-testid="workflow-package-preflight-panel">
      <ConsoleSection
        actions={
          <Button
            className="w-full sm:w-auto"
            disabled={preflightPending}
            size="sm"
            type="button"
            variant="outline"
            onClick={onPreflight}
          >
            {preflightPending ? (
              <Loader2 className="animate-spin" data-icon="inline-start" />
            ) : (
              <FileCheck2 data-icon="inline-start" />
            )}
            Run preflight
          </Button>
        }
        description="Load launch metadata, preflight the saved package, and review launch-only diagnostics before queueing a run."
        title="Readiness console"
        tone={blockingCount > 0 ? "danger" : warningCount > 0 ? "warning" : "default"}
      >
        <div className="min-w-0 space-y-4">
          {isLoadingMetadata ? (
            <div className="min-w-0 rounded-xl border bg-muted/30 p-4 text-sm text-muted-foreground">
              Loading launch metadata...
            </div>
          ) : null}
          {metadataError ? (
            <Alert
              data-testid="workflow-package-launch-metadata-error"
              variant="destructive"
            >
              <AlertCircle />
              <AlertTitle>Launch metadata unavailable</AlertTitle>
              <AlertDescription>
                {errorMessage(metadataError, "Failed to load launch metadata.")}
              </AlertDescription>
            </Alert>
          ) : null}
          <div data-testid="workflow-package-preflight-status">
            <ResourceStatusStrip
              density="comfortable"
              items={[
                {
                  description: readinessDescription,
                  label: "Readiness",
                  tone: ready
                    ? "success"
                    : blockingCount > 0
                      ? "danger"
                      : "warning",
                  value: readinessLabel,
                },
                {
                  description: "Stops run creation until resolved.",
                  label: "Blocking",
                  tone: blockingCount > 0 ? "danger" : "success",
                  value: blockingCount,
                },
                {
                  description: "Visible but non-blocking launch evidence.",
                  label: "Warnings",
                  tone: warningCount > 0 ? "warning" : "success",
                  value: warningCount,
                },
              ]}
            />
          </div>
          <div data-testid="workflow-package-preflight-evidence">
            <EvidenceCluster
              items={[
                {
                  description: preflightPending
                    ? "Preflight request is running."
                    : "Displayed metadata is the latest launch read or preflight result.",
                  label: "Preflight",
                  tone: ready ? "verified" : blockingCount > 0 ? "danger" : "warning",
                  value: readinessRead ? "Loaded" : "Pending",
                },
                {
                  description: "Workflow selected for metadata and run creation.",
                  label: "Workflow",
                  value: readinessRead?.workflowKey ?? "Not selected",
                },
                {
                  description: "Manifest hash returned with launch metadata.",
                  label: "Manifest",
                  tone: readinessRead?.manifestHash ? "verified" : "warning",
                  value: readinessRead?.manifestHash ? (
                    <span className="break-all font-mono text-xs">
                      {readinessRead.manifestHash}
                    </span>
                  ) : (
                    "Not recorded"
                  ),
                },
                {
                  description: "Backend-provided workflow input schema is kept as the JSON editor source.",
                  label: "Input schema",
                  tone: readinessRead?.inputSchema ? "verified" : "warning",
                  value: readinessRead?.inputSchema ? "Available" : "Unavailable",
                },
              ]}
            />
          </div>
          <ModelConnectionModeSummary
            diagnostics={[...diagnostics]}
            read={readinessRead}
          />
          <div
            className="rounded-lg border bg-muted/20 p-3 text-sm text-muted-foreground"
            data-testid="workflow-package-capability-readiness-note"
          >
            Capability blockers prevent run creation. Warnings stay
            launch-visible as degraded capability or probe-status notes so
            operators can decide whether to continue before queueing a run.
          </div>
          <div data-testid="workflow-package-constraint-inspector">
            <ConstraintInspector
              blocking={diagnosticConstraintSection({
                diagnostics: blockingDiagnostics,
                testId: "workflow-package-launch-blockers",
              })}
              requirements={[
                "Run preflight uses the selected workflow key and server-side package metadata.",
                "Launch creates a run only after preflight returns ready.",
              ]}
              summary={
                readinessRead
                  ? `${blockingCount} blocking issue${blockingCount === 1 ? "" : "s"} and ${warningCount} warning${warningCount === 1 ? "" : "s"} for ${readinessRead.packageKey}.`
                  : "Launch metadata has not loaded yet."
              }
              title="Capability constraints"
              warnings={diagnosticConstraintSection({
                diagnostics: warningDiagnostics,
                emptyCopy: "No warnings reported.",
                testId: "workflow-package-launch-warnings",
              })}
            />
          </div>
        </div>
      </ConsoleSection>
    </div>
  );
}

function SavedInputsHelper(props: {
  createDisabled: boolean;
  createPending: boolean;
  deletePending: boolean;
  error: Error | null;
  historyEntries: readonly WorkflowPackageRuntimeInputEntryRead[];
  loading: boolean;
  personalEntries: readonly WorkflowPackageRuntimeInputEntryRead[];
  presetName: string;
  updatePending: boolean;
  workflowKey: string;
  onCreate: () => void;
  onDelete: (entry: WorkflowPackageRuntimeInputEntryRead) => void;
  onLoad: (entry: WorkflowPackageRuntimeInputEntryRead) => void;
  onPresetNameChange: (value: string) => void;
  onUpdate: (entry: WorkflowPackageRuntimeInputEntryRead) => void;
}) {
  const {
    createDisabled,
    createPending,
    deletePending,
    error,
    historyEntries,
    loading,
    onCreate,
    onDelete,
    onLoad,
    onPresetNameChange,
    onUpdate,
    personalEntries,
    presetName,
    updatePending,
    workflowKey,
  } = props;
  const personalLimitReached =
    personalEntries.length >= SAVED_INPUT_ENTRY_LIMIT;
  const sortedPersonal = newestRuntimeInputEntries(
    personalEntries,
    "updatedAt",
  );
  const sortedHistory = newestRuntimeInputEntries(historyEntries, "createdAt");
  return (
    <div
      className="min-w-0 space-y-3 rounded-xl border bg-muted/20 p-3"
      data-testid="runtime-input-saved-inputs-helper"
    >
      <div className="flex min-w-0 flex-col gap-1">
        <div className="flex min-w-0 items-center justify-between gap-2">
          <h4 className="text-sm font-semibold">Saved Inputs</h4>
          <Badge variant="outline">{workflowKey || "workflow"}</Badge>
        </div>
        <p className="text-xs text-muted-foreground">
          Load presets or prior launch inputs.
        </p>
      </div>
      {loading ? (
        <div className="flex items-center gap-2 rounded-lg border bg-background/60 p-3 text-xs text-muted-foreground">
          <Loader2 className="size-3 animate-spin" />
          Loading saved inputs for {workflowKey || "this workflow"}...
        </div>
      ) : null}
      {error ? (
        <Alert variant="destructive">
          <AlertCircle />
          <AlertTitle>Saved inputs unavailable</AlertTitle>
          <AlertDescription>{error.message}</AlertDescription>
        </Alert>
      ) : null}
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h5 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Personal
          </h5>
          <Badge variant="secondary">
            {personalEntries.length}/{SAVED_INPUT_ENTRY_LIMIT}
          </Badge>
        </div>
        <div className="flex min-w-0 flex-col gap-2 sm:flex-row">
          <Input
            className="h-8 min-w-0 text-xs"
            aria-label="Personal preset name"
            placeholder="Preset name"
            value={presetName}
            onChange={(event) => onPresetNameChange(event.target.value)}
          />
          <Button
            className="h-8 w-full text-xs sm:w-auto"
            disabled={createDisabled || createPending || personalLimitReached}
            size="sm"
            type="button"
            onClick={onCreate}
          >
            {createPending ? (
              <Loader2 className="animate-spin" data-icon="inline-start" />
            ) : (
              <Save data-icon="inline-start" />
            )}
            Save current JSON
          </Button>
        </div>
        {personalLimitReached ? (
          <p className="text-xs text-destructive">
            Personal presets are capped at 20 per workflow. Delete one before
            saving another.
          </p>
        ) : null}
        {sortedPersonal.length === 0 ? (
          <p className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">
            No personal presets saved for this workflow.
          </p>
        ) : null}
        <div className="space-y-2">
          {sortedPersonal.map((entry) => (
            <SavedInputEntryRow
              key={entry.id}
              deletePending={deletePending}
              entry={entry}
              mode="personal"
              updatePending={updatePending}
              onDelete={onDelete}
              onLoad={onLoad}
              onUpdate={onUpdate}
            />
          ))}
        </div>
      </div>
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h5 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            History
          </h5>
          <Badge variant="secondary">
            {historyEntries.length}/{SAVED_INPUT_ENTRY_LIMIT}
          </Badge>
        </div>
        {sortedHistory.length === 0 ? (
          <p className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">
            No launch history yet.
          </p>
        ) : null}
        <div className="space-y-2">
          {sortedHistory.map((entry) => (
            <SavedInputEntryRow
              key={entry.id}
              deletePending={false}
              entry={entry}
              mode="history"
              updatePending={false}
              onDelete={onDelete}
              onLoad={onLoad}
              onUpdate={onUpdate}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

export function WorkflowPackageLaunchPage() {
  const { packageId: routePackageId } = useParams<{ packageId: string }>();
  const navigate = useNavigate();
  const packageId = validPackageId(routePackageId) ?? undefined;
  const [workflowKey, setWorkflowKey] = useState("");
  const [preflightRead, setPreflightRead] = useState<
    WorkflowPackageLaunchRead | undefined
  >(undefined);
  const [parametersText, setParametersText] = useState(() => stringifyJson({}));
  const [runtimeInputErrors, setRuntimeInputErrors] = useState<
    ApiErrorDetail[]
  >([]);
  const [personalPresetName, setPersonalPresetName] = useState("");
  const parametersEditedRef = useRef(false);
  const lastTemplateIdentityRef = useRef<string | null>(null);
  const resolvedWorkflowKey = workflowKey.trim();

  const packageQuery = useWorkflowPackage(packageId);
  const launchQuery = useWorkflowPackageLaunch(
    packageId,
    resolvedWorkflowKey || undefined,
  );
  const preflightPackage = usePreflightWorkflowPackage();
  const createLaunch = useCreateWorkflowPackageLaunch();
  const runtimeInputRegistry = useWorkflowPackageRuntimeInputRegistry(
    packageId,
    resolvedWorkflowKey,
  );
  const createPersonalEntry =
    useCreateWorkflowPackageRuntimeInputPersonalEntry();
  const updatePersonalEntry =
    useUpdateWorkflowPackageRuntimeInputPersonalEntry();
  const deletePersonalEntry =
    useDeleteWorkflowPackageRuntimeInputPersonalEntry();
  const launchRead = launchQuery.data;
  const readinessRead = preflightRead ?? launchRead;
  const diagnostics = useMemo(
    () => diagnosticsFromLaunch(readinessRead),
    [readinessRead],
  );
  const blockingCount = diagnostics.filter(
    (diagnostic) => diagnostic.severity === "error",
  ).length;
  const warningCount = diagnostics.filter(
    (diagnostic) => diagnostic.severity === "warning",
  ).length;
  const ready = readinessRead?.ready === true && blockingCount === 0;
  const inputSchemaFingerprint = useMemo(
    () => stringifyJson(launchRead?.inputSchema),
    [launchRead?.inputSchema],
  );
  const inputSchemaSnapshot = useMemo(
    () =>
      inputSchemaFingerprint
        ? (JSON.parse(inputSchemaFingerprint) as unknown)
        : undefined,
    [inputSchemaFingerprint],
  );
  const inputTemplate = useMemo(
    () => createLaunchParametersTemplate(inputSchemaSnapshot),
    [inputSchemaSnapshot],
  );
  const parameterTemplateText = useMemo(
    () => resetLaunchParametersTemplate(inputTemplate),
    [inputTemplate],
  );
  const launchFormIdentity = `${packageId ?? ""}:${resolvedWorkflowKey}:${inputSchemaFingerprint}`;

  useEffect(() => {
    if (launchRead?.workflowKey && !workflowKey) {
      setWorkflowKey(launchRead.workflowKey);
    }
  }, [launchRead?.workflowKey, workflowKey]);

  useEffect(() => {
    if (lastTemplateIdentityRef.current === launchFormIdentity) {
      return;
    }
    lastTemplateIdentityRef.current = launchFormIdentity;
    setRuntimeInputErrors([]);
    if (!parametersEditedRef.current) {
      setParametersText(parameterTemplateText);
    }
  }, [launchFormIdentity, parameterTemplateText]);

  if (!packageId) {
    return (
      <LaunchPageMessage
        description="The launch route needs a persisted numeric workflow package id. Open a saved package before launching."
        title="Invalid workflow package launch route"
      />
    );
  }

  if (packageQuery.isPending) {
    return <LaunchPageSkeleton />;
  }

  if (packageQuery.isError) {
    return (
      <LaunchPageMessage
        description={
          isNotFoundError(packageQuery.error)
            ? "No saved workflow package exists for this launch route."
            : errorMessage(
                packageQuery.error,
                "Failed to load workflow package.",
              )
        }
        title={
          isNotFoundError(packageQuery.error)
            ? "Workflow package not found"
            : "Workflow package could not be loaded"
        }
      />
    );
  }

  if (!packageQuery.data) {
    return (
      <LaunchPageMessage
        description="The package summary did not load, so launch controls stayed unavailable."
        title="Workflow package context unavailable"
      />
    );
  }

  const resetParameters = () => {
    parametersEditedRef.current = false;
    setParametersText(parameterTemplateText);
    setRuntimeInputErrors([]);
  };

  const parseCurrentRuntimeInputs = () => {
    setRuntimeInputErrors([]);
    try {
      return parseLaunchParametersJson(parametersText);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Runtime inputs JSON must be a valid object.";
      setRuntimeInputErrors([{ field: "parameters", issue: message }]);
      toast.error(message);
      return null;
    }
  };

  const loadSavedInput = (entry: WorkflowPackageRuntimeInputEntryRead) => {
    parametersEditedRef.current = true;
    setParametersText(stringifyJson(entry.payload));
    setRuntimeInputErrors([]);
    toast.success("Saved input loaded into the JSON editor");
  };

  const runLaunchPreflight =
    async (): Promise<WorkflowPackageLaunchRead | null> => {
      try {
        const result = await preflightPackage.mutateAsync({
          packageId,
          payload: { parameters: {}, workflowKey: resolvedWorkflowKey || null },
        });
        setPreflightRead(result);
        const resultDiagnostics = diagnosticsFromLaunch(result);
        if (
          resultDiagnostics.some(
            (diagnostic) => diagnostic.severity === "error",
          )
        ) {
          toast.warning("Package preflight found blocking diagnostics");
        } else {
          toast.success(
            result.warnings.length > 0
              ? "Package preflight passed with warnings"
              : "Package preflight passed",
          );
        }
        return result;
      } catch (error) {
        toast.error(
          error instanceof Error ? error.message : "Package preflight failed.",
        );
        return null;
      }
    };

  const savePersonalInput = async () => {
    if (!resolvedWorkflowKey) {
      return;
    }
    const name = personalPresetName.trim();
    if (!name) {
      toast.error("Name this personal preset before saving it.");
      return;
    }
    const payload = parseCurrentRuntimeInputs();
    if (!payload) {
      return;
    }
    try {
      await createPersonalEntry.mutateAsync({
        packageId,
        payload: { name, payload },
        workflowKey: resolvedWorkflowKey,
      });
      setPersonalPresetName("");
      toast.success("Saved personal runtime input preset");
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Failed to save personal runtime input preset.",
      );
    }
  };

  const overwritePersonalInput = async (
    entry: WorkflowPackageRuntimeInputEntryRead,
  ) => {
    if (!resolvedWorkflowKey) {
      return;
    }
    const payload = parseCurrentRuntimeInputs();
    if (!payload) {
      return;
    }
    const name = personalPresetName.trim() || entry.name;
    try {
      await updatePersonalEntry.mutateAsync({
        entryId: entry.id,
        packageId,
        payload: { name: name || null, payload },
        workflowKey: resolvedWorkflowKey,
      });
      setPersonalPresetName("");
      toast.success("Updated personal runtime input preset");
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Failed to update personal runtime input preset.",
      );
    }
  };

  const deletePersonalInput = async (
    entry: WorkflowPackageRuntimeInputEntryRead,
  ) => {
    if (!resolvedWorkflowKey) {
      return;
    }
    try {
      await deletePersonalEntry.mutateAsync({
        entryId: entry.id,
        packageId,
        workflowKey: resolvedWorkflowKey,
      });
      toast.success("Deleted personal runtime input preset");
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Failed to delete personal runtime input preset.",
      );
    }
  };

  const updateWorkflowKey = (nextWorkflowKey: string) => {
    parametersEditedRef.current = false;
    setWorkflowKey(nextWorkflowKey);
    setPreflightRead(undefined);
    setParametersText(parameterTemplateText);
    setRuntimeInputErrors([]);
  };

  const updateParametersText = (nextParametersText: string) => {
    parametersEditedRef.current = true;
    setParametersText(nextParametersText);
  };

  const launchPackage = async () => {
    setRuntimeInputErrors([]);
    let parameters: UnknownRecord;
    try {
      parameters = parseLaunchParametersJson(parametersText);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Runtime inputs JSON must be a valid object.";
      setRuntimeInputErrors([{ field: "parameters", issue: message }]);
      toast.error(message);
      return;
    }
    const preflight = await runLaunchPreflight();
    if (!preflight) {
      return;
    }
    if (!preflight.ready) {
      toast.error("Resolve blocking preflight diagnostics before launch.");
      return;
    }
    try {
      const run = await createLaunch.mutateAsync({
        packageId,
        payload: { parameters, workflowKey: resolvedWorkflowKey || null },
      });
      toast.success("Package run queued");
      navigate(`/runs/${run.id}`);
    } catch (error) {
      if (error instanceof ApiRequestError && error.details.length > 0) {
        setRuntimeInputErrors(error.details);
      }
      toast.error(
        error instanceof Error
          ? error.message
          : "Failed to launch workflow package.",
      );
    }
  };

  return (
    <WorkspacePageShell
      bodyAriaLabel="Workflow package launch workspace"
      bodyClassName="gap-4"
      contextBar={
        <LaunchIdentityContextBar
          blockingCount={blockingCount}
          packageId={packageId}
          ready={ready}
          warningCount={warningCount}
          workflowPackage={packageQuery.data}
        />
      }
      testId="workflow-package-launch-page"
    >
      <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <LaunchReadinessCard
          blockingCount={blockingCount}
          diagnostics={diagnostics}
          isLoadingMetadata={launchQuery.isPending}
          metadataError={launchQuery.isError ? launchQuery.error : null}
          readinessRead={readinessRead}
          ready={ready}
          warningCount={warningCount}
          onPreflight={() => void runLaunchPreflight()}
          preflightPending={preflightPackage.isPending}
        />

        <div data-testid="workflow-package-launch-tab">
          <div data-testid="workflow-package-run-config">
            <ConsoleSection
              description="Select a workflow, provide runtime input JSON, manage saved inputs, and queue a run from this package snapshot."
              title="Run configuration"
            >
              <div className="min-w-0 space-y-4">
                <div className="min-w-0 space-y-2">
                  <Label htmlFor="workflow-key">Workflow key</Label>
                  <Input
                    id="workflow-key"
                    aria-label="Workflow key"
                    placeholder="Workflow key"
                    value={workflowKey}
                    onChange={(event) => updateWorkflowKey(event.target.value)}
                  />
                </div>
                <div className="min-w-0 rounded-xl border bg-background/60">
                  <div className="flex min-w-0 flex-col gap-3 px-4 pt-4 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0 space-y-1">
                      <h3 className="text-base font-semibold tracking-tight">
                        Runtime inputs
                      </h3>
                      <p className="text-sm text-muted-foreground">
                        Runtime inputs must be a JSON object.
                      </p>
                    </div>
                    <Button
                      className="w-full sm:w-auto"
                      size="sm"
                      type="button"
                      variant="outline"
                      onClick={resetParameters}
                    >
                      Reset to template
                    </Button>
                  </div>
                  <div className="min-w-0 space-y-4 p-4">
                    {!inputTemplate.schemaSupported ? (
                      <Alert className="border-chart-3/30 bg-chart-3/10">
                        <AlertCircle />
                        <AlertTitle>Schema template started empty</AlertTitle>
                        <AlertDescription>
                          <p>{inputTemplate.reason}</p>
                          {inputTemplate.issues.length > 0 ? (
                            <ul className="list-disc pl-5">
                              {inputTemplate.issues.map((issue) => (
                                <li key={`${issue.field}-${issue.issue}`}>
                                  {issue.field}: {issue.issue}
                                </li>
                              ))}
                            </ul>
                          ) : null}
                        </AlertDescription>
                      </Alert>
                    ) : null}
                    <RuntimeInputValidationAlert errors={runtimeInputErrors} />
                    <div
                      className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,22rem)] xl:grid-cols-1 2xl:grid-cols-[minmax(0,1fr)_minmax(18rem,22rem)]"
                      data-testid="runtime-input-console-grid"
                    >
                      <div
                        className="min-w-0 space-y-2"
                        data-testid="runtime-input-json-panel"
                      >
                        <Label htmlFor="runtime-json">Runtime inputs JSON</Label>
                        <Textarea
                          id="runtime-json"
                          aria-label="Runtime inputs JSON"
                          className="min-h-72 max-w-full overflow-x-auto whitespace-pre font-mono text-xs"
                          rows={14}
                          value={parametersText}
                          onChange={(event) =>
                            updateParametersText(event.target.value)
                          }
                        />
                      </div>
                      <SavedInputsHelper
                        createDisabled={
                          !resolvedWorkflowKey ||
                          runtimeInputRegistry.isPending ||
                          runtimeInputRegistry.isFetching ||
                          !personalPresetName.trim()
                        }
                        createPending={createPersonalEntry.isPending}
                        deletePending={deletePersonalEntry.isPending}
                        error={
                          runtimeInputRegistry.isError
                            ? runtimeInputRegistry.error
                            : null
                        }
                        historyEntries={runtimeInputRegistry.data?.history ?? []}
                        loading={
                          runtimeInputRegistry.isPending ||
                          runtimeInputRegistry.isFetching
                        }
                        personalEntries={runtimeInputRegistry.data?.personal ?? []}
                        presetName={personalPresetName}
                        updatePending={updatePersonalEntry.isPending}
                        workflowKey={resolvedWorkflowKey}
                        onCreate={() => void savePersonalInput()}
                        onDelete={(entry) => void deletePersonalInput(entry)}
                        onLoad={loadSavedInput}
                        onPresetNameChange={setPersonalPresetName}
                        onUpdate={(entry) => void overwritePersonalInput(entry)}
                      />
                    </div>
                  </div>
                </div>
                <div
                  className="flex min-w-0 flex-col gap-2 sm:flex-row sm:justify-end"
                  data-testid="workflow-package-run-actions"
                >
                  <Button
                    className="w-full sm:w-auto"
                    disabled={preflightPackage.isPending || launchQuery.isPending}
                    type="button"
                    variant="outline"
                    onClick={() => void runLaunchPreflight()}
                  >
                    {preflightPackage.isPending ? (
                      <Loader2
                        className="animate-spin"
                        data-icon="inline-start"
                      />
                    ) : (
                      <FileCheck2 data-icon="inline-start" />
                    )}
                    Run preflight
                  </Button>
                  <Button
                    className="w-full sm:w-auto"
                    disabled={
                      createLaunch.isPending ||
                      preflightPackage.isPending ||
                      launchQuery.isPending ||
                      launchQuery.isError
                    }
                    type="button"
                    onClick={() => void launchPackage()}
                  >
                    {createLaunch.isPending ? (
                      <Loader2
                        className="animate-spin"
                        data-icon="inline-start"
                      />
                    ) : (
                      <PlayCircle data-icon="inline-start" />
                    )}
                    Launch Run
                  </Button>
                </div>
              </div>
            </ConsoleSection>
          </div>
        </div>
      </div>

      <LaunchContextCard workflowPackage={packageQuery.data} />
    </WorkspacePageShell>
  );
}
