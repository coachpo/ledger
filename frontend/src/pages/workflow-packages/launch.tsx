import {
  AlertCircle,
  ChevronDown,
  FileCheck2,
  Loader2,
  PlayCircle,
  Save,
  SquarePen,
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { PageContextBar } from "@/components/shared/page-context-bar";
import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/components/ui/utils";
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
import type {
  WorkflowPackageLaunchRead,
  WorkflowPackageRead,
  WorkflowPackageRuntimeInputEntryRead,
} from "@/lib/types/workflow-package";

type PackageDiagnostic = {
  field: string;
  issue: string;
  severity: "error" | "warning";
};

type SavedInputEntryMode = "history" | "personal";

const SAVED_INPUT_ENTRY_LIMIT = 20;

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

function diagnosticFromRecord(
  value: unknown,
  severity: "error" | "warning",
): PackageDiagnostic {
  const record = isUnknownRecord(value) ? value : {};
  const field = stringValue(record.field) || stringValue(record.path) || "$";
  return {
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

type ReadinessChipTone = "neutral" | "success" | "warning" | "danger";

const readinessChipVariantByTone: Record<
  ReadinessChipTone,
  "secondary" | "outline" | "destructive"
> = {
  danger: "destructive",
  neutral: "outline",
  success: "secondary",
  warning: "outline",
};

function ReadinessStatusChip({
  label,
  tone = "neutral",
  value,
}: {
  label: string;
  tone?: ReadinessChipTone;
  value: string | number;
}) {
  return (
    <Badge
      aria-label={`${label}: ${value}`}
      className={cn(
        "max-w-full gap-1.5 px-2 py-0.5 text-xs leading-5",
        tone === "warning" ? "border-chart-3/30 bg-chart-3/10 text-chart-3" : null,
      )}
      data-tone={tone}
      variant={readinessChipVariantByTone[tone]}
    >
      <span className="font-medium">{label}</span>
      <span className="min-w-0 truncate">{value}</span>
    </Badge>
  );
}

function DiagnosticList({
  diagnostics,
  testId,
  title,
}: {
  diagnostics: readonly PackageDiagnostic[];
  testId: string;
  title: string;
}) {
  if (diagnostics.length === 0) {
    return null;
  }

  return (
    <div className="min-w-0 space-y-2" data-testid={testId}>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </h3>
      <div className="min-w-0 divide-y rounded-lg border bg-background/60" role="list">
        {diagnostics.map((diagnostic, diagnosticIndex) => (
          <div
            className="grid min-w-0 gap-2 p-3 text-sm md:grid-cols-[auto_minmax(0,11rem)_minmax(0,1fr)] md:items-center"
            key={`${diagnostic.severity}-${diagnostic.field}-${diagnostic.issue}-${diagnosticIndex}`}
            role="listitem"
          >
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              {diagnosticBadge(diagnostic)}
            </div>
            <code className="min-w-0 break-all rounded bg-muted/40 px-2 py-1 text-xs">
              {diagnostic.field}
            </code>
            <span className="min-w-0 break-words text-muted-foreground">
              {diagnostic.issue}
            </span>
          </div>
        ))}
      </div>
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

function PackageDetailsDisclosure({
  workflowPackage,
}: {
  workflowPackage: WorkflowPackageRead;
}) {
  return (
    <Collapsible className="min-w-0" data-testid="workflow-package-launch-identity">
      <div className="flex min-w-0 flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        <span>Package #{workflowPackage.id}</span>
        <span aria-hidden="true">·</span>
        <code className="min-w-0 break-all font-mono text-foreground">
          {workflowPackage.key}
        </code>
        <span aria-hidden="true">·</span>
        <span>Updated {formatDateTime(workflowPackage.updatedAt)}</span>
        <span aria-hidden="true">·</span>
        <CollapsibleTrigger asChild>
          <Button
            className="h-7 gap-1 px-1.5 text-xs"
            size="sm"
            type="button"
            variant="ghost"
          >
            Details
            <ChevronDown className="size-3" />
          </Button>
        </CollapsibleTrigger>
      </div>
      <CollapsibleContent
        className="pt-2"
        data-testid="workflow-package-launch-details"
      >
        <dl className="grid min-w-0 gap-2 rounded-lg border bg-muted/20 p-3 text-xs sm:grid-cols-2 xl:grid-cols-3">
          <div className="min-w-0">
            <dt className="font-medium text-muted-foreground">Key</dt>
            <dd className="break-all font-mono text-foreground">
              {workflowPackage.key}
            </dd>
          </div>
          <div className="min-w-0">
            <dt className="font-medium text-muted-foreground">Package name</dt>
            <dd className="break-words text-foreground">{workflowPackage.name}</dd>
          </div>
          <div className="min-w-0">
            <dt className="font-medium text-muted-foreground">Manifest hash</dt>
            <dd className="break-all font-mono text-foreground">
              {workflowPackage.manifestHash ?? "Not recorded"}
            </dd>
          </div>
          <div className="min-w-0">
            <dt className="font-medium text-muted-foreground">Compiled hash</dt>
            <dd className="break-all font-mono text-foreground">
              {workflowPackage.compiledHash ?? "Not recorded"}
            </dd>
          </div>
          <div className="min-w-0">
            <dt className="font-medium text-muted-foreground">Created</dt>
            <dd className="text-foreground">
              {formatDateTime(workflowPackage.createdAt)}
            </dd>
          </div>
          <div className="min-w-0">
            <dt className="font-medium text-muted-foreground">Updated</dt>
            <dd className="text-foreground">
              {formatDateTime(workflowPackage.updatedAt)}
            </dd>
          </div>
        </dl>
      </CollapsibleContent>
    </Collapsible>
  );
}

function LaunchHeader({
  workflowPackage,
}: {
  workflowPackage: WorkflowPackageRead;
}) {
  return (
    <PageContextBar
      actions={
        <Button asChild size="sm" variant="outline">
          <Link to={`/workflow-packages/${workflowPackage.id}`}>
            <SquarePen data-icon="inline-start" />
            Open Editor
          </Link>
        </Button>
      }
      description={
        workflowPackage.description ||
        "Queue a run from the currently persisted workflow package."
      }
      meta={<PackageDetailsDisclosure workflowPackage={workflowPackage} />}
      title="Launch Workflow Package"
    />
  );
}

function LaunchReadinessSummary({
  blockingCount,
  diagnostics,
  isLoadingMetadata,
  metadataError,
  preflightCompleted,
  preflightPending,
  readinessRead,
  ready,
  warningCount,
  workflowKey,
}: {
  blockingCount: number;
  diagnostics: readonly PackageDiagnostic[];
  isLoadingMetadata: boolean;
  metadataError: unknown;
  preflightCompleted: boolean;
  preflightPending: boolean;
  readinessRead: WorkflowPackageLaunchRead | undefined;
  ready: boolean;
  warningCount: number;
  workflowKey: string;
}) {
  const blockingDiagnostics = diagnostics.filter(
    (diagnostic) => diagnostic.severity === "error",
  );
  const warningDiagnostics = diagnostics.filter(
    (diagnostic) => diagnostic.severity === "warning",
  );
  const primaryStatusMessage = metadataError
    ? "Launch metadata unavailable"
    : preflightPending
      ? "Preflight is validating launch metadata."
      : !preflightCompleted
        ? "Run preflight to load launch metadata and validate this package before launch."
        : ready
          ? "Ready to launch."
          : blockingCount > 0
            ? "Resolve blocking launch diagnostics before launching."
            : warningCount > 0
              ? "Preflight completed with warnings."
              : "Preflight completed, but launch readiness was not confirmed.";
  const metadataValue = metadataError
    ? "Launch metadata unavailable"
    : isLoadingMetadata
      ? "Metadata loading"
      : readinessRead
        ? "Metadata loaded"
        : "Metadata missing";
  const preflightValue = preflightPending
    ? "Preflight running"
    : preflightCompleted
      ? ready
        ? "Preflight ready"
        : blockingCount > 0
          ? "Preflight blocked"
          : warningCount > 0
            ? "Preflight warnings"
            : "Preflight complete"
      : "Preflight pending";

  return (
    <Card
      className="min-w-0 gap-4"
      data-testid="workflow-package-preflight-panel"
    >
      <CardHeader className="px-4 pt-4">
        <CardTitle className="text-sm font-semibold tracking-tight">
          Launch readiness
        </CardTitle>
        <CardDescription
          className="text-sm leading-5"
          data-testid="workflow-package-launch-next-step"
        >
          {primaryStatusMessage}
        </CardDescription>
      </CardHeader>
      <CardContent className="min-w-0 space-y-4 px-4 pb-4">
        {isLoadingMetadata ? (
          <p className="text-sm text-muted-foreground">
            Loading launch metadata...
          </p>
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
        <div
          className="flex min-w-0 flex-wrap items-center gap-2"
          data-testid="workflow-package-preflight-status"
        >
          <ReadinessStatusChip
            label="Metadata"
            tone={metadataError ? "danger" : isLoadingMetadata ? "warning" : readinessRead ? "success" : "neutral"}
            value={metadataValue}
          />
          <ReadinessStatusChip
            label="Preflight"
            tone={preflightPending ? "warning" : preflightCompleted ? (ready ? "success" : blockingCount > 0 ? "danger" : "warning") : "neutral"}
            value={preflightValue}
          />
          <ReadinessStatusChip
            label="Workflow"
            tone={workflowKey || readinessRead?.workflowKey ? "success" : "warning"}
            value={workflowKey || readinessRead?.workflowKey || "Workflow not selected"}
          />
          <ReadinessStatusChip
            label="Manifest"
            tone={readinessRead?.manifestHash ? "success" : "warning"}
            value={readinessRead?.manifestHash ? "Manifest recorded" : "Manifest not recorded"}
          />
          <ReadinessStatusChip
            label="Schema"
            tone={readinessRead?.inputSchema ? "success" : "warning"}
            value={readinessRead?.inputSchema ? "Input schema available" : "Input schema unavailable"}
          />
          {blockingCount > 0 ? (
            <ReadinessStatusChip
              label="Blocking"
              tone="danger"
              value={blockingCount}
            />
          ) : null}
          {warningCount > 0 ? (
            <ReadinessStatusChip
              label="Warnings"
              tone="warning"
              value={warningCount}
            />
          ) : null}
        </div>
        <DiagnosticList
          diagnostics={blockingDiagnostics}
          testId="workflow-package-launch-blockers"
          title="Blocking diagnostics"
        />
        <DiagnosticList
          diagnostics={warningDiagnostics}
          testId="workflow-package-launch-warnings"
          title="Warnings"
        />
      </CardContent>
    </Card>
  );
}

function StickyLaunchActionBar({
  launchDisabledReason,
  launchPending,
  launchQueryPending,
  preflightPending,
  onLaunch,
  onPreflight,
}: {
  launchDisabledReason: string | null;
  launchPending: boolean;
  launchQueryPending: boolean;
  preflightPending: boolean;
  onLaunch: () => void;
  onPreflight: () => void;
}) {
  const disabledReasonId = "workflow-package-launch-disabled-reason";

  return (
    <div
      className="sticky top-0 z-10 flex min-w-0 flex-col gap-2 rounded-xl border bg-background/95 p-3 shadow-sm backdrop-blur supports-[backdrop-filter]:bg-background/85 sm:flex-row sm:items-center sm:justify-between"
      data-testid="workflow-package-run-actions"
    >
      <p className="min-w-0 text-sm text-muted-foreground">
        Review the runtime JSON above, preflight the package, then launch a run.
      </p>
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center sm:justify-end">
        {launchDisabledReason ? (
          <p
            className="text-xs text-muted-foreground"
            id={disabledReasonId}
          >
            {launchDisabledReason}
          </p>
        ) : null}
        <Button
          className="w-full sm:w-auto"
          disabled={preflightPending || launchQueryPending}
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
        <Button
          aria-describedby={launchDisabledReason ? disabledReasonId : undefined}
          className="w-full sm:w-auto"
          disabled={Boolean(launchDisabledReason)}
          type="button"
          onClick={onLaunch}
        >
          {launchPending ? (
            <Loader2 className="animate-spin" data-icon="inline-start" />
          ) : (
            <PlayCircle data-icon="inline-start" />
          )}
          Launch Run
        </Button>
      </div>
    </div>
  );
}

function SchemaTemplateWarning({
  issues,
  reason,
}: {
  issues: readonly { field: string; issue: string }[];
  reason: string | null;
}) {
  return (
    <Collapsible
      className="min-w-0 rounded-lg border border-chart-3/30 bg-chart-3/10 p-3 text-xs text-muted-foreground"
      data-testid="runtime-input-schema-template-warning"
    >
      <div className="flex min-w-0 items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <AlertCircle className="size-4 shrink-0 text-chart-3" />
          <p className="min-w-0 font-medium text-foreground">
            Schema template started empty
          </p>
        </div>
        <CollapsibleTrigger asChild>
          <Button
            className="h-7 shrink-0 gap-1 px-2 text-xs"
            size="sm"
            type="button"
            variant="ghost"
          >
            Details
            <ChevronDown className="size-3" />
          </Button>
        </CollapsibleTrigger>
      </div>
      <CollapsibleContent className="min-w-0 pt-2">
        <div className="min-w-0 space-y-1 border-t border-chart-3/30 pt-2">
          <p>{reason ?? "Schema could not be converted into a launch JSON template."}</p>
          {issues.length > 0 ? (
            <ul className="list-disc pl-5">
              {issues.map((issue) => (
                <li key={`${issue.field}-${issue.issue}`}>
                  {issue.field}: {issue.issue}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function SavedInputsTabs(props: {
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
    <div className="min-w-0 space-y-3" data-testid="runtime-input-saved-inputs-helper">
      <div className="flex min-w-0 flex-col gap-1">
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">Saved inputs</h3>
          <Badge variant="outline">{workflowKey || "workflow"}</Badge>
        </div>
        <p className="text-xs text-muted-foreground">
          Load saved personal presets or reuse launch history for this workflow.
        </p>
      </div>
      {loading ? (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="size-3 animate-spin" />
          Loading saved inputs for {workflowKey || "this workflow"}...
        </p>
      ) : null}
      {error ? (
        <Alert variant="destructive">
          <AlertCircle />
          <AlertTitle>Saved inputs unavailable</AlertTitle>
          <AlertDescription>{error.message}</AlertDescription>
        </Alert>
      ) : null}
      <Tabs className="min-w-0 gap-3" defaultValue="presets">
        <TabsList className="w-full justify-start sm:w-fit">
          <TabsTrigger value="presets">
            Presets
            <Badge className="ml-1" variant="secondary">
              {personalEntries.length}/{SAVED_INPUT_ENTRY_LIMIT}
            </Badge>
          </TabsTrigger>
          <TabsTrigger value="history">
            History
            <Badge className="ml-1" variant="secondary">
              {historyEntries.length}/{SAVED_INPUT_ENTRY_LIMIT}
            </Badge>
          </TabsTrigger>
        </TabsList>
        <TabsContent className="min-w-0 space-y-3" value="presets">
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
            <p className="text-xs text-muted-foreground">
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
        </TabsContent>
        <TabsContent className="min-w-0 space-y-3" value="history">
          {sortedHistory.length === 0 ? (
            <p className="text-xs text-muted-foreground">
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
        </TabsContent>
      </Tabs>
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

  const preflightCompleted = Boolean(preflightRead);
  const launchDisabledReason = createLaunch.isPending
    ? "Launch request is already in progress."
    : preflightPackage.isPending
      ? "Launch disabled while preflight is running."
      : launchQuery.isPending
        ? "Launch disabled while launch metadata loads."
        : launchQuery.isError
          ? "Launch disabled until launch metadata is available."
          : !preflightCompleted
            ? "Launch disabled until preflight completes."
            : blockingCount > 0
              ? "Launch disabled until blocking diagnostics are resolved."
              : !ready
                ? "Launch disabled until this package is ready."
                : null;

  return (
    <WorkspacePageShell
      bodyAriaLabel="Workflow package launch workspace"
      bodyClassName="gap-3"
      contextBar={<LaunchHeader workflowPackage={packageQuery.data} />}
      testId="workflow-package-launch-page"
    >
      <LaunchReadinessSummary
        blockingCount={blockingCount}
        diagnostics={diagnostics}
        isLoadingMetadata={launchQuery.isPending}
        metadataError={launchQuery.isError ? launchQuery.error : null}
        preflightCompleted={preflightCompleted}
        preflightPending={preflightPackage.isPending}
        readinessRead={readinessRead}
        ready={ready}
        warningCount={warningCount}
        workflowKey={resolvedWorkflowKey}
      />

      <div data-testid="workflow-package-launch-tab">
        <Card className="min-w-0 gap-4" data-testid="workflow-package-run-config">
          <CardHeader className="px-4 pt-4">
            <div className="min-w-0">
              <CardTitle className="text-sm font-semibold tracking-tight">
                Runtime inputs
              </CardTitle>
              <CardDescription className="mt-1 text-xs leading-5">
                Select a workflow key and provide a JSON object for launch.
              </CardDescription>
            </div>
            <CardAction>
              <Button
                className="w-full sm:w-auto"
                size="sm"
                type="button"
                variant="outline"
                onClick={resetParameters}
              >
                Reset to template
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent className="min-w-0 space-y-4 px-4 pb-4">
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
            {!inputTemplate.schemaSupported ? (
              <SchemaTemplateWarning
                issues={inputTemplate.issues}
                reason={inputTemplate.reason}
              />
            ) : null}
            <RuntimeInputValidationAlert errors={runtimeInputErrors} />
            <div
              className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,22rem)]"
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
                  onChange={(event) => updateParametersText(event.target.value)}
                />
              </div>
              <SavedInputsTabs
                createDisabled={
                  !resolvedWorkflowKey ||
                  runtimeInputRegistry.isPending ||
                  runtimeInputRegistry.isFetching ||
                  !personalPresetName.trim()
                }
                createPending={createPersonalEntry.isPending}
                deletePending={deletePersonalEntry.isPending}
                error={
                  runtimeInputRegistry.isError ? runtimeInputRegistry.error : null
                }
                historyEntries={runtimeInputRegistry.data?.history ?? []}
                loading={
                  runtimeInputRegistry.isPending || runtimeInputRegistry.isFetching
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
          </CardContent>
        </Card>
      </div>

      <StickyLaunchActionBar
        launchDisabledReason={launchDisabledReason}
        launchPending={createLaunch.isPending}
        launchQueryPending={launchQuery.isPending}
        preflightPending={preflightPackage.isPending}
        onLaunch={() => void launchPackage()}
        onPreflight={() => void runLaunchPreflight()}
      />
    </WorkspacePageShell>
  );
}
