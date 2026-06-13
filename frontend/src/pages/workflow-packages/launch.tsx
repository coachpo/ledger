import {
  AlertCircle,
  ChevronDown,
  FileCheck2,
  Loader2,
  PlayCircle,
  SquarePen,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { SchemaValueEntryForm } from "@/components/platform-authoring/generated-form/schema-form";
import {
  SavedRuntimeInputRegistryPanel,
  type SavedRuntimeInputRegistryEntry,
} from "@/components/shared/saved-runtime-input-registry-panel";
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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/components/ui/utils";
import {
  useCreateWorkflowPackageLaunch,
  useCreateWorkflowPackageRuntimeInputPresetEntry,
  useDeleteWorkflowPackageRuntimeInputPresetEntry,
  usePreflightWorkflowPackage,
  useUpdateWorkflowPackageRuntimeInputPresetEntry,
  useWorkflowPackage,
  useWorkflowPackageLaunch,
  useWorkflowPackageManifest,
  useWorkflowPackageRuntimeInputRegistry,
} from "@/hooks/use-workflow-packages";
import { ApiRequestError } from "@/lib/api-client";
import { formatDateTime } from "@/lib/format";
import { stringifyJson } from "@/lib/platform-authoring/common/serialization";
import { getWorkflowOptions } from "@/lib/workflow-options";
import {
  createLaunchDraftFromValidatedPayload,
  createLaunchInputState,
  createLaunchPayloadFromDraft,
  formatLaunchDraftJson,
  parseLaunchPayloadJson,
  reconcileLaunchDraftChange,
} from "@/lib/platform-authoring/schema/launch-input-state";
import type { ValueEntryObject } from "@/lib/platform-authoring/values/types";
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

type SavedInputEntryMode = "history" | "preset";
type LaunchInputMode = "form" | "json";

const SAVED_INPUT_ENTRY_LIMIT = 20;
const EMPTY_RUNTIME_INPUT_ENTRIES: readonly WorkflowPackageRuntimeInputEntryRead[] =
  [];

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
        tone === "warning"
          ? "border-chart-3/30 bg-chart-3/10 text-chart-3"
          : null,
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
      <div
        className="min-w-0 divide-y rounded-lg border bg-background/60"
        role="list"
      >
        {diagnostics.map((diagnostic, diagnosticIndex) => (
          <div
            className="flex min-w-0 flex-wrap items-start gap-2 p-3 text-sm"
            key={`${diagnostic.severity}-${diagnostic.field}-${diagnostic.issue}-${diagnosticIndex}`}
            role="listitem"
          >
            {diagnosticBadge(diagnostic)}
            <span className="min-w-0 flex-1 basis-60 break-words text-muted-foreground">
              <code className="break-all rounded bg-muted/40 px-1 py-0.5 text-xs text-foreground">
                {diagnostic.field}
              </code>
              {`: ${diagnostic.issue}`}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function savedRuntimeInputRegistryEntry(
  entry: WorkflowPackageRuntimeInputEntryRead,
  mode: SavedInputEntryMode,
): SavedRuntimeInputRegistryEntry {
  const timestamp = mode === "history" ? entry.createdAt : entry.updatedAt;

  return {
    id: entry.id,
    label: savedInputEntryLabel(entry, mode),
    mode,
    sourceLabel: `${mode === "history" ? "Captured" : "Updated"} ${formatDateTime(timestamp)}`,
    stale: entry.stale.stale,
    staleReasonLines: entry.stale.reasons.map(
      (reason) => `${reason.field}: ${reason.issue}`,
    ),
  };
}

function PackageDetailsDisclosure({
  workflowPackage,
}: {
  workflowPackage: WorkflowPackageRead;
}) {
  return (
    <Collapsible
      className="min-w-0"
      data-testid="workflow-package-launch-identity"
    >
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
            <dd className="break-words text-foreground">
              {workflowPackage.name}
            </dd>
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
  primaryStatusOverride,
  readinessRead,
  ready,
  warningCount,
  workflowTone,
  workflowValue,
}: {
  blockingCount: number;
  diagnostics: readonly PackageDiagnostic[];
  isLoadingMetadata: boolean;
  metadataError: unknown;
  preflightCompleted: boolean;
  preflightPending: boolean;
  primaryStatusOverride?: string | null;
  readinessRead: WorkflowPackageLaunchRead | undefined;
  ready: boolean;
  warningCount: number;
  workflowTone: ReadinessChipTone;
  workflowValue: string;
}) {
  const blockingDiagnostics = diagnostics.filter(
    (diagnostic) => diagnostic.severity === "error",
  );
  const warningDiagnostics = diagnostics.filter(
    (diagnostic) => diagnostic.severity === "warning",
  );
  const primaryStatusMessage =
    primaryStatusOverride ??
    (metadataError
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
                : "Preflight completed, but launch readiness was not confirmed.");
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
            tone={
              metadataError
                ? "danger"
                : isLoadingMetadata
                  ? "warning"
                  : readinessRead
                    ? "success"
                    : "neutral"
            }
            value={metadataValue}
          />
          <ReadinessStatusChip
            label="Preflight"
            tone={
              preflightPending
                ? "warning"
                : preflightCompleted
                  ? ready
                    ? "success"
                    : blockingCount > 0
                      ? "danger"
                      : "warning"
                  : "neutral"
            }
            value={preflightValue}
          />
          <ReadinessStatusChip
            label="Workflow"
            tone={workflowTone}
            value={workflowValue}
          />
          <ReadinessStatusChip
            label="Manifest"
            tone={readinessRead?.manifestHash ? "success" : "warning"}
            value={
              readinessRead?.manifestHash
                ? "Manifest recorded"
                : "Manifest not recorded"
            }
          />
          <ReadinessStatusChip
            label="Schema"
            tone={readinessRead?.inputSchema ? "success" : "warning"}
            value={
              readinessRead?.inputSchema
                ? "Input schema available"
                : "Input schema unavailable"
            }
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
  preflightBlocked,
  preflightPending,
  onLaunch,
  onPreflight,
}: {
  launchDisabledReason: string | null;
  launchPending: boolean;
  launchQueryPending: boolean;
  preflightBlocked: boolean;
  preflightPending: boolean;
  onLaunch: () => void;
  onPreflight: () => void;
}) {
  const disabledReasonId = "workflow-package-launch-disabled-reason";

  return (
    <div
      className="sticky top-0 z-10 flex min-w-0 flex-col gap-2 rounded-xl border bg-background/95 p-3 shadow-sm sm:flex-row sm:items-center sm:justify-between"
      data-testid="workflow-package-run-actions"
    >
      <p className="min-w-0 text-sm text-muted-foreground">
        Review the runtime inputs above, preflight the package, then launch a
        run.
      </p>
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center sm:justify-end">
        {launchDisabledReason ? (
          <p className="text-xs text-muted-foreground" id={disabledReasonId}>
            {launchDisabledReason}
          </p>
        ) : null}
        <Button
          className="w-full sm:w-auto"
          disabled={preflightBlocked || preflightPending || launchQueryPending}
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
          <p>
            {reason ??
              "Schema could not be converted into a launch JSON template."}
          </p>
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

export function WorkflowPackageLaunchPage() {
  const { packageId: routePackageId } = useParams<{ packageId: string }>();
  const navigate = useNavigate();
  const packageId = validPackageId(routePackageId) ?? undefined;
  const [workflowKey, setWorkflowKey] = useState("");
  const [preflightRead, setPreflightRead] = useState<
    WorkflowPackageLaunchRead | undefined
  >(undefined);
  const [parametersText, setParametersText] = useState(() => stringifyJson({}));
  const [launchDraft, setLaunchDraft] = useState<ValueEntryObject | null>(null);
  const [launchInputMode, setLaunchInputMode] =
    useState<LaunchInputMode>("form");
  const [runtimeInputErrors, setRuntimeInputErrors] = useState<
    ApiErrorDetail[]
  >([]);
  const [presetName, setPresetName] = useState("");
  const parametersEditedRef = useRef(false);
  const lastTemplateIdentityRef = useRef<string | null>(null);
  const resolvedWorkflowKey = workflowKey.trim();

  const packageQuery = useWorkflowPackage(packageId);
  const manifestQuery = useWorkflowPackageManifest(packageId);
  const manifestWorkflowOptions = useMemo(
    () => (manifestQuery.data ? getWorkflowOptions(manifestQuery.data) : []),
    [manifestQuery.data],
  );
  const selectedManifestWorkflow = useMemo(
    () =>
      manifestWorkflowOptions.find(
        (option) => option.key === resolvedWorkflowKey,
      ) ?? null,
    [manifestWorkflowOptions, resolvedWorkflowKey],
  );
  const workflowOptions = useMemo(
    () =>
      manifestQuery.data
        ? getWorkflowOptions(manifestQuery.data, resolvedWorkflowKey || null)
        : [],
    [manifestQuery.data, resolvedWorkflowKey],
  );
  const selectedWorkflowOption = useMemo(
    () =>
      workflowOptions.find((option) => option.key === resolvedWorkflowKey) ??
      null,
    [workflowOptions, resolvedWorkflowKey],
  );
  const activeWorkflowKey = selectedManifestWorkflow?.key ?? "";
  const workflowSelected = Boolean(activeWorkflowKey);
  const launchQuery = useWorkflowPackageLaunch(
    packageId,
    activeWorkflowKey || undefined,
  );
  const preflightPackage = usePreflightWorkflowPackage();
  const createLaunch = useCreateWorkflowPackageLaunch();
  const runtimeInputRegistry = useWorkflowPackageRuntimeInputRegistry(
    packageId,
    activeWorkflowKey,
  );
  const createPresetEntry =
    useCreateWorkflowPackageRuntimeInputPresetEntry();
  const updatePresetEntry =
    useUpdateWorkflowPackageRuntimeInputPresetEntry();
  const deletePresetEntry =
    useDeleteWorkflowPackageRuntimeInputPresetEntry();
  const launchRead = workflowSelected ? launchQuery.data : undefined;
  const launchMetadataError =
    workflowSelected && launchQuery.isError ? launchQuery.error : null;
  const launchMetadataPending = workflowSelected && launchQuery.isPending;
  const savedInputsError =
    workflowSelected && runtimeInputRegistry.isError
      ? runtimeInputRegistry.error
      : null;
  const savedInputsLoading =
    workflowSelected &&
    (runtimeInputRegistry.isPending || runtimeInputRegistry.isFetching);
  const savedHistoryEntries = useMemo(
    () =>
      workflowSelected
        ? (runtimeInputRegistry.data?.history ?? EMPTY_RUNTIME_INPUT_ENTRIES)
        : EMPTY_RUNTIME_INPUT_ENTRIES,
    [runtimeInputRegistry.data?.history, workflowSelected],
  );
  const savedPresetEntries = useMemo(
    () =>
      workflowSelected
        ? (runtimeInputRegistry.data?.presets ?? EMPTY_RUNTIME_INPUT_ENTRIES)
        : EMPTY_RUNTIME_INPUT_ENTRIES,
    [runtimeInputRegistry.data?.presets, workflowSelected],
  );
  const savedHistoryPanelEntries = useMemo(
    () =>
      newestRuntimeInputEntries(savedHistoryEntries, "createdAt").map((entry) =>
        savedRuntimeInputRegistryEntry(entry, "history"),
      ),
    [savedHistoryEntries],
  );
  const savedPresetPanelEntries = useMemo(
    () =>
      newestRuntimeInputEntries(savedPresetEntries, "updatedAt").map(
        (entry) => savedRuntimeInputRegistryEntry(entry, "preset"),
      ),
    [savedPresetEntries],
  );
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
  const ready =
    Boolean(activeWorkflowKey) &&
    readinessRead?.ready === true &&
    blockingCount === 0;
  const effectiveInputSchema = useMemo(
    () =>
      launchRead?.inputSchema ??
      selectedManifestWorkflow?.inputSchema ??
      selectedWorkflowOption?.inputSchema ??
      {},
    [launchRead?.inputSchema, selectedManifestWorkflow, selectedWorkflowOption],
  );
  const inputSchemaFingerprint = useMemo(
    () => stringifyJson(effectiveInputSchema),
    [effectiveInputSchema],
  );
  const inputSchemaSnapshot = useMemo(
    () =>
      inputSchemaFingerprint
        ? (JSON.parse(inputSchemaFingerprint) as unknown)
        : {},
    [inputSchemaFingerprint],
  );
  const launchInputState = useMemo(
    () => createLaunchInputState(inputSchemaSnapshot),
    [inputSchemaSnapshot],
  );
  const activeLaunchDraft = launchInputState.schemaSupported
    ? (launchDraft ?? launchInputState.draft)
    : null;
  const activeLaunchInputMode: LaunchInputMode = launchInputState.schemaSupported
    ? launchInputMode
    : "json";
  const activeFormParametersText = activeLaunchDraft
    ? formatLaunchDraftJson(activeLaunchDraft)
    : launchInputState.formattedJson;
  const activeParametersText =
    launchInputState.schemaSupported && activeLaunchInputMode === "form"
      ? activeFormParametersText
      : parametersText;
  const launchFormIdentity = `${packageId ?? ""}:${activeWorkflowKey}:${inputSchemaFingerprint}`;
  const updateWorkflowKey = useCallback(
    (nextWorkflowKey: string) => {
      const normalizedWorkflowKey = nextWorkflowKey.trim();
      if (normalizedWorkflowKey === resolvedWorkflowKey) {
        return;
      }
      parametersEditedRef.current = false;
      setWorkflowKey(normalizedWorkflowKey);
      setPreflightRead(undefined);
      setRuntimeInputErrors([]);
      setLaunchDraft(null);
      setLaunchInputMode("form");
      setParametersText(stringifyJson({}));
    },
    [resolvedWorkflowKey],
  );

  useEffect(() => {
    if (lastTemplateIdentityRef.current === launchFormIdentity) {
      return;
    }
    lastTemplateIdentityRef.current = launchFormIdentity;
    parametersEditedRef.current = false;
    setRuntimeInputErrors([]);
    setLaunchDraft(launchInputState.draft);
    setLaunchInputMode("form");
    setParametersText(launchInputState.formattedJson);
  }, [
    launchFormIdentity,
    launchInputState.draft,
    launchInputState.formattedJson,
  ]);

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
    setLaunchDraft(launchInputState.draft);
    setLaunchInputMode("form");
    setParametersText(launchInputState.formattedJson);
    setRuntimeInputErrors([]);
  };

  const runtimeInputJsonError = (error: unknown): ApiErrorDetail[] => {
    const message =
      error instanceof Error
        ? error.message
        : "Runtime inputs JSON must be a valid object.";
    return [{ field: "parameters", issue: message }];
  };

  const applyAdvancedJsonToForm = ({
    showSuccess = true,
    switchToForm = true,
  }: {
    showSuccess?: boolean;
    switchToForm?: boolean;
  } = {}): UnknownRecord | null => {
    try {
      const payload = parseLaunchPayloadJson(parametersText);
      const { draft, issues } = createLaunchDraftFromValidatedPayload(
        launchInputState,
        payload,
      );
      if (issues.length > 0 || !draft) {
        setRuntimeInputErrors(issues);
        toast.error("Advanced JSON does not match the workflow input schema.");
        return null;
      }
      setLaunchDraft(draft);
      setParametersText(formatLaunchDraftJson(draft));
      setRuntimeInputErrors([]);
      if (switchToForm) {
        setLaunchInputMode("form");
      }
      if (showSuccess) {
        toast.success("Advanced JSON applied to the launch form");
      }
      return createLaunchPayloadFromDraft(draft);
    } catch (error) {
      const details = runtimeInputJsonError(error);
      setRuntimeInputErrors(details);
      toast.error(details[0]?.issue ?? "Runtime inputs JSON is invalid.");
      return null;
    }
  };

  const updateLaunchInputMode = (nextMode: LaunchInputMode) => {
    if (nextMode === activeLaunchInputMode) {
      return;
    }
    if (nextMode === "json") {
      setParametersText(activeFormParametersText);
      setLaunchInputMode("json");
      setRuntimeInputErrors([]);
      return;
    }
    applyAdvancedJsonToForm({ showSuccess: false, switchToForm: true });
  };

  const resetAdvancedJsonToFormPayload = () => {
    setParametersText(activeFormParametersText);
    setRuntimeInputErrors([]);
  };

  const parseCurrentRuntimeInputs = (): UnknownRecord | null => {
    if (launchInputState.schemaSupported) {
      if (activeLaunchInputMode === "json") {
        return applyAdvancedJsonToForm({
          showSuccess: false,
          switchToForm: false,
        });
      }
      setRuntimeInputErrors([]);
      return activeLaunchDraft ? createLaunchPayloadFromDraft(activeLaunchDraft) : {};
    }
    try {
      const payload = parseLaunchPayloadJson(parametersText);
      setRuntimeInputErrors([]);
      return payload;
    } catch (error) {
      const details = runtimeInputJsonError(error);
      setRuntimeInputErrors(details);
      toast.error(details[0]?.issue ?? "Runtime inputs JSON is invalid.");
      return null;
    }
  };

  const loadSavedInput = (entry: WorkflowPackageRuntimeInputEntryRead) => {
    if (!workflowSelected) {
      return;
    }
    parametersEditedRef.current = true;
    if (launchInputState.schemaSupported) {
      const { draft, issues } = createLaunchDraftFromValidatedPayload(
        launchInputState,
        entry.payload,
      );
      if (issues.length > 0 || !draft) {
        setLaunchDraft(null);
        setLaunchInputMode("json");
        setParametersText(stringifyJson(entry.payload));
        setRuntimeInputErrors(issues);
        toast.error("Saved input needs review before it can update the form.");
        return;
      }
      setLaunchDraft(draft);
      setLaunchInputMode("form");
      setParametersText(formatLaunchDraftJson(draft));
    } else {
      setParametersText(stringifyJson(entry.payload));
    }
    setRuntimeInputErrors([]);
    toast.success(
      launchInputState.schemaSupported
        ? "Saved input loaded into the launch form"
        : "Saved input loaded into the JSON editor",
    );
  };

  const runLaunchPreflight = async (
    runtimeParameters?: UnknownRecord,
  ): Promise<WorkflowPackageLaunchRead | null> => {
    const parameters = runtimeParameters ?? parseCurrentRuntimeInputs();
    if (!parameters) {
      return null;
    }
    try {
      const result = await preflightPackage.mutateAsync({
        packageId,
        payload: { parameters, workflowKey: activeWorkflowKey || null },
      });
      setPreflightRead(result);
      const resultDiagnostics = diagnosticsFromLaunch(result);
      if (
        resultDiagnostics.some((diagnostic) => diagnostic.severity === "error")
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

  const savePresetInput = async () => {
    if (!activeWorkflowKey) {
      return;
    }
    const name = presetName.trim();
    if (!name) {
      toast.error("Name this saved runtime input preset before saving it.");
      return;
    }
    const payload = parseCurrentRuntimeInputs();
    if (!payload) {
      return;
    }
    try {
      await createPresetEntry.mutateAsync({
        packageId,
        payload: { name, payload },
        workflowKey: activeWorkflowKey,
      });
      setPresetName("");
      toast.success("Saved runtime input preset");
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Failed to save runtime input preset.",
      );
    }
  };

  const overwritePresetInput = async (
    entry: WorkflowPackageRuntimeInputEntryRead,
  ) => {
    if (!activeWorkflowKey) {
      return;
    }
    const payload = parseCurrentRuntimeInputs();
    if (!payload) {
      return;
    }
    const name = presetName.trim() || entry.name;
    try {
      await updatePresetEntry.mutateAsync({
        entryId: entry.id,
        packageId,
        payload: { name: name || null, payload },
        workflowKey: activeWorkflowKey,
      });
      setPresetName("");
      toast.success("Updated saved runtime input preset");
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Failed to update saved runtime input preset.",
      );
    }
  };

  const deletePresetInput = async (
    entry: WorkflowPackageRuntimeInputEntryRead,
  ) => {
    if (!activeWorkflowKey) {
      return;
    }
    try {
      await deletePresetEntry.mutateAsync({
        entryId: entry.id,
        packageId,
        workflowKey: activeWorkflowKey,
      });
      toast.success("Deleted saved runtime input preset");
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Failed to delete saved runtime input preset.",
      );
    }
  };

  const updateParametersText = (nextParametersText: string) => {
    parametersEditedRef.current = true;
    if (launchInputState.schemaSupported) {
      setLaunchInputMode("json");
    }
    setParametersText(nextParametersText);
    setRuntimeInputErrors([]);
  };

  const updateLaunchDraft = (nextDraft: ValueEntryObject) => {
    parametersEditedRef.current = true;
    setRuntimeInputErrors([]);
    setLaunchDraft((previousDraft) =>
      reconcileLaunchDraftChange(launchInputState, previousDraft, nextDraft),
    );
  };

  const launchPackage = async () => {
    const parameters = parseCurrentRuntimeInputs();
    if (!parameters) {
      return;
    }
    const preflight = await runLaunchPreflight(parameters);
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
        payload: { parameters, workflowKey: activeWorkflowKey || null },
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

  const workflowSelectionMessage = manifestQuery.isPending
    ? "Loading workflows from this package manifest."
    : manifestQuery.isError
      ? "Workflow selector unavailable until the package manifest loads."
      : manifestWorkflowOptions.length === 0
        ? "This package manifest does not declare any workflows."
        : resolvedWorkflowKey && !selectedManifestWorkflow
          ? "Selected workflow is no longer present in the current manifest. Choose a workflow to continue."
          : !workflowSelected
            ? "Choose a workflow to continue."
            : null;
  const workflowSelectionError = manifestQuery.isError
    ? errorMessage(manifestQuery.error, "Failed to load manifest workflows.")
    : null;
  const workflowDescription =
    workflowSelectionMessage || !selectedWorkflowOption?.description
      ? null
      : selectedWorkflowOption.description;
  const workflowStatusTone: ReadinessChipTone = workflowSelectionError
    ? "danger"
    : manifestQuery.isPending
      ? "warning"
      : activeWorkflowKey
        ? "success"
        : manifestWorkflowOptions.length === 0
          ? "warning"
          : resolvedWorkflowKey
            ? "danger"
            : "warning";
  const workflowStatusValue = workflowSelectionError
    ? "Manifest unavailable"
    : manifestQuery.isPending
      ? "Loading workflows"
      : activeWorkflowKey
        ? activeWorkflowKey
        : manifestWorkflowOptions.length === 0
          ? "No workflows declared"
          : resolvedWorkflowKey
            ? "Workflow no longer available"
            : "Workflow selection required";
  const workflowActionBlockReason = manifestQuery.isPending
    ? "Workflow actions disabled while manifest workflows load."
    : manifestQuery.isError
      ? "Workflow actions disabled until manifest workflows are available."
      : manifestWorkflowOptions.length === 0
        ? "Workflow actions disabled because this manifest has no workflows."
        : resolvedWorkflowKey && !selectedManifestWorkflow
          ? "Workflow actions disabled until you choose a valid manifest workflow."
          : !workflowSelected
            ? "Choose a workflow to continue."
            : null;
  const preflightCompleted = Boolean(preflightRead);
  const launchDisabledReason = workflowActionBlockReason
    ? workflowActionBlockReason
    : createLaunch.isPending
      ? "Launch request is already in progress."
      : preflightPackage.isPending
        ? "Launch disabled while preflight is running."
        : launchMetadataPending
          ? "Launch disabled while launch metadata loads."
          : launchMetadataError
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
        isLoadingMetadata={launchMetadataPending}
        metadataError={launchMetadataError}
        preflightCompleted={preflightCompleted}
        preflightPending={preflightPackage.isPending}
        primaryStatusOverride={workflowSelectionMessage}
        readinessRead={readinessRead}
        ready={ready}
        warningCount={warningCount}
        workflowTone={workflowStatusTone}
        workflowValue={workflowStatusValue}
      />

      <div data-testid="workflow-package-launch-tab">
        <Card
          className="min-w-0 gap-4"
          data-testid="workflow-package-run-config"
        >
          <CardHeader className="px-4 pt-4">
            <div className="min-w-0">
              <CardTitle className="text-sm font-semibold tracking-tight">
                Runtime inputs
              </CardTitle>
              <CardDescription className="mt-1 text-xs leading-5">
                Choose a workflow from the manifest and provide launch inputs
                from the generated schema form.
              </CardDescription>
            </div>
            <CardAction>
              <Button
                className="w-full sm:w-auto"
                disabled={!workflowSelected}
                size="sm"
                type="button"
                variant="outline"
                onClick={resetParameters}
              >
                Reset to template
              </Button>
            </CardAction>
          </CardHeader>
          <CardContent className="flex min-w-0 flex-col gap-4 px-4 pb-4">
            <div className="flex min-w-0 flex-col gap-2">
              <Label htmlFor="workflow-selector">Workflow</Label>
              <Select
                disabled={
                  manifestQuery.isPending ||
                  manifestQuery.isError ||
                  workflowOptions.length === 0
                }
                value={resolvedWorkflowKey || undefined}
                onValueChange={updateWorkflowKey}
              >
                <SelectTrigger aria-label="Workflow" id="workflow-selector">
                  <SelectValue placeholder="Choose a workflow" />
                </SelectTrigger>
                <SelectContent>
                  <SelectGroup>
                    {workflowOptions.length > 0 ? (
                      workflowOptions.map((option) => (
                        <SelectItem key={option.key} value={option.key}>
                          {option.label}
                        </SelectItem>
                      ))
                    ) : (
                      <SelectItem disabled value="workflow-unavailable">
                        {manifestQuery.isPending
                          ? "Loading workflows..."
                          : manifestQuery.isError
                            ? "Workflow manifest unavailable"
                            : "No workflows available"}
                      </SelectItem>
                    )}
                  </SelectGroup>
                </SelectContent>
              </Select>
              {workflowSelectionMessage ? (
                <Alert
                  data-testid="workflow-package-workflow-selector-feedback"
                  variant={workflowSelectionError ? "destructive" : "default"}
                >
                  <AlertCircle />
                  <AlertTitle>Workflow selection</AlertTitle>
                  <AlertDescription>
                    <div className="flex min-w-0 flex-col gap-1">
                      <span>{workflowSelectionMessage}</span>
                      {workflowSelectionError ? (
                        <span>{workflowSelectionError}</span>
                      ) : null}
                    </div>
                  </AlertDescription>
                </Alert>
              ) : workflowDescription ? (
                <p className="text-xs text-muted-foreground">
                  {workflowDescription}
                </p>
              ) : null}
            </div>
            {!launchInputState.schemaSupported ? (
              <SchemaTemplateWarning
                issues={launchInputState.issues}
                reason={launchInputState.reason}
              />
            ) : null}
            <RuntimeInputValidationAlert errors={runtimeInputErrors} />
            <div
              className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,22rem)]"
              data-testid="runtime-input-console-grid"
            >
              <div
                className="flex min-w-0 flex-col gap-4"
                data-testid="runtime-input-json-panel"
              >
                {launchInputState.schemaSupported ? (
                  <div
                    className="flex min-w-0 flex-col gap-2 rounded-lg border bg-muted/10 p-3"
                    data-testid="runtime-input-mode-controls"
                  >
                    <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <div className="flex min-w-0 flex-col gap-1">
                        <Label>Input mode</Label>
                        <p className="text-xs text-muted-foreground">
                          Form mode is canonical. JSON mode lets you edit a raw
                          object and apply it back to the form after validation.
                        </p>
                      </div>
                      <ToggleGroup
                        aria-label="Launch input mode"
                        className="w-full sm:w-fit"
                        type="single"
                        value={activeLaunchInputMode}
                        onValueChange={(value) => {
                          if (value === "form" || value === "json") {
                            updateLaunchInputMode(value);
                          }
                        }}
                      >
                        <ToggleGroupItem
                          className="h-8 px-3 text-xs"
                          disabled={!workflowSelected}
                          value="form"
                        >
                          Form
                        </ToggleGroupItem>
                        <ToggleGroupItem
                          className="h-8 px-3 text-xs"
                          disabled={!workflowSelected}
                          value="json"
                        >
                          JSON
                        </ToggleGroupItem>
                      </ToggleGroup>
                    </div>
                  </div>
                ) : null}
                {launchInputState.schemaSupported &&
                launchInputState.schema &&
                activeLaunchDraft &&
                activeLaunchInputMode === "form" ? (
                  <div
                    className="flex min-w-0 flex-col gap-3 rounded-xl border bg-background/60 p-3"
                    data-testid="runtime-input-primary-form"
                  >
                    <div className="flex min-w-0 flex-col gap-1">
                      <div className="flex min-w-0 flex-wrap items-center gap-2">
                        <Badge variant="secondary">Primary</Badge>
                        <p className="text-sm font-medium text-foreground">
                          Supported-schema input surface
                        </p>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Required and defaulted inputs are active now; optional
                        inputs without defaults stay visible as addable rows.
                      </p>
                    </div>
                    <SchemaValueEntryForm
                      data-testid="runtime-input-schema-form"
                      disabled={!workflowSelected}
                      label="Runtime inputs"
                      schema={launchInputState.schema}
                      value={activeLaunchDraft}
                      onChange={(nextValue) =>
                        updateLaunchDraft(nextValue as ValueEntryObject)
                      }
                    />
                  </div>
                ) : null}
                {launchInputState.schemaSupported &&
                activeLaunchInputMode === "json" ? (
                  <Alert data-testid="runtime-input-json-mode-notice">
                    <AlertCircle />
                    <AlertTitle>Advanced JSON mode</AlertTitle>
                    <AlertDescription>
                      Apply valid JSON to update the canonical form. Invalid JSON
                      stays local and blocks preflight, launch, save, and
                      overwrite actions.
                    </AlertDescription>
                  </Alert>
                ) : null}
                {launchInputState.schemaSupported ? (
                  <Collapsible
                    className="flex min-w-0 flex-col gap-3 rounded-lg border border-dashed bg-muted/10 p-3"
                    data-testid="runtime-input-advanced-json"
                    defaultOpen
                  >
                    <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                      <div className="flex min-w-0 flex-col gap-1">
                        <p className="text-sm font-medium text-foreground">
                          {activeLaunchInputMode === "form"
                            ? "Advanced JSON preview"
                            : "Advanced JSON editor"}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {activeLaunchInputMode === "form"
                            ? "Read-only canonical payload derived from the schema form."
                            : "Edit a JSON object, then apply it to validate and update the form."}
                        </p>
                      </div>
                      <CollapsibleTrigger asChild>
                        <Button
                          className="w-full sm:w-auto"
                          size="sm"
                          type="button"
                          variant="outline"
                        >
                          {activeLaunchInputMode === "form"
                            ? "Advanced JSON preview"
                            : "Advanced JSON editor"}
                          <ChevronDown data-icon="inline-end" />
                        </Button>
                      </CollapsibleTrigger>
                    </div>
                    <CollapsibleContent>
                      <div className="flex min-w-0 flex-col gap-3">
                        <div className="flex min-w-0 flex-col gap-2">
                          <Label htmlFor="runtime-json">Runtime inputs JSON</Label>
                          <Textarea
                            id="runtime-json"
                            aria-invalid={
                              runtimeInputErrors.length > 0 ? true : undefined
                            }
                            aria-label="Runtime inputs JSON"
                            className="min-h-48 max-w-full overflow-x-auto whitespace-pre font-mono text-xs"
                            disabled={!workflowSelected}
                            readOnly={activeLaunchInputMode === "form"}
                            rows={10}
                            value={activeParametersText}
                            onChange={(event) =>
                              updateParametersText(event.target.value)
                            }
                          />
                        </div>
                        <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center sm:justify-end">
                          <Button
                            disabled={
                              !workflowSelected || activeLaunchInputMode !== "json"
                            }
                            size="sm"
                            type="button"
                            variant="outline"
                            onClick={() => applyAdvancedJsonToForm()}
                          >
                            Apply JSON to form
                          </Button>
                          <Button
                            disabled={!workflowSelected}
                            size="sm"
                            type="button"
                            variant="ghost"
                            onClick={resetAdvancedJsonToFormPayload}
                          >
                            Reset to form payload
                          </Button>
                        </div>
                      </div>
                    </CollapsibleContent>
                  </Collapsible>
                ) : (
                  <div className="flex min-w-0 flex-col gap-2">
                    <Label htmlFor="runtime-json">Runtime inputs JSON</Label>
                    <Textarea
                      id="runtime-json"
                      aria-label="Runtime inputs JSON"
                      className="min-h-72 max-w-full overflow-x-auto whitespace-pre font-mono text-xs"
                      disabled={!workflowSelected}
                      rows={14}
                      value={activeParametersText}
                      onChange={(event) =>
                        updateParametersText(event.target.value)
                      }
                    />
                  </div>
                )}
              </div>
              <SavedRuntimeInputRegistryPanel
                capMessage="Saved runtime input presets are capped at 20 per workflow. Delete one before saving another."
                createDisabled={
                  !workflowSelected ||
                  savedInputsLoading ||
                  !presetName.trim()
                }
                createPending={createPresetEntry.isPending}
                deletePending={deletePresetEntry.isPending}
                disableTabsWhenUnavailable
                error={savedInputsError}
                errorTitle="Saved inputs unavailable"
                helperCopy={
                  workflowSelected
                    ? "Load saved runtime input presets or reuse launch history for this workflow."
                    : "Choose a workflow to load saved runtime input presets or launch history."
                }
                historyEmptyMessage="No launch history yet."
                historyEntries={savedHistoryPanelEntries}
                loading={savedInputsLoading}
                loadingMessage={`Loading saved inputs for ${activeWorkflowKey}...`}
                presetEntries={savedPresetPanelEntries}
                presetEmptyMessage="No saved runtime input presets for this workflow."
                presetNameLabel="Saved runtime input preset name"
                presetNamePlaceholder="Preset name"
                presetNameValue={presetName}
                presetLimit={SAVED_INPUT_ENTRY_LIMIT}
                rowTestIdPrefix="saved-input"
                saveLabel="Save current JSON"
                staleNoticeTitle="Saved against older workflow metadata."
                testId="runtime-input-saved-inputs-helper"
                title="Saved inputs"
                updatePending={updatePresetEntry.isPending}
                workflowBadgeFallback="workflow pending"
                workflowEnabled={workflowSelected}
                workflowKey={activeWorkflowKey}
                onCreate={() => void savePresetInput()}
                onDelete={(entry) => {
                  const savedEntry = savedPresetEntries.find(
                    (candidate) => candidate.id === entry.id,
                  );
                  if (savedEntry) {
                    void deletePresetInput(savedEntry);
                  }
                }}
                onLoad={(entry) => {
                  const savedEntry =
                    entry.mode === "history"
                      ? savedHistoryEntries.find(
                          (candidate) => candidate.id === entry.id,
                        )
                      : savedPresetEntries.find(
                          (candidate) => candidate.id === entry.id,
                        );
                  if (savedEntry) {
                    loadSavedInput(savedEntry);
                  }
                }}
                onOverwrite={(entry) => {
                  const savedEntry = savedPresetEntries.find(
                    (candidate) => candidate.id === entry.id,
                  );
                  if (savedEntry) {
                    void overwritePresetInput(savedEntry);
                  }
                }}
                onPresetNameChange={setPresetName}
              />
            </div>
          </CardContent>
        </Card>
      </div>

      <StickyLaunchActionBar
        launchDisabledReason={launchDisabledReason}
        launchPending={createLaunch.isPending}
        launchQueryPending={launchMetadataPending}
        preflightBlocked={Boolean(workflowActionBlockReason)}
        preflightPending={preflightPackage.isPending}
        onLaunch={() => void launchPackage()}
        onPreflight={() => void runLaunchPreflight()}
      />
    </WorkspacePageShell>
  );
}
