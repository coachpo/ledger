import {
  AlertCircle,
  CheckCircle2,
  FileCheck2,
  Loader2,
  PlayCircle,
  Save,
  Trash2,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";

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

function connectionKindLabel(value: ModelConnectionKind | null | undefined): string {
  return CONNECTION_KIND_LABELS[value ?? "provider"];
}

function diagnosticFromRecord(value: unknown, severity: "error" | "warning"): PackageDiagnostic {
  const record = isUnknownRecord(value) ? value : {};
  const field = stringValue(record.field) || stringValue(record.path) || "$";
  const connectionKind = modelConnectionKindValue(record.connectionKind);
  return {
    ...(connectionKind ? { connectionKind } : {}),
    field,
    issue: stringValue(record.issue) || stringValue(record.message) || "Review this package diagnostic.",
    severity,
  };
}

function diagnosticsFromLaunch(read: WorkflowPackageLaunchRead | undefined): PackageDiagnostic[] {
  if (!read) {
    return [];
  }
  const blockingErrors = Array.isArray(read.blockingErrors) ? read.blockingErrors : [];
  const warnings = Array.isArray(read.warnings) ? read.warnings : [];
  return [
    ...blockingErrors.map((diagnostic) => diagnosticFromRecord(diagnostic, "error")),
    ...warnings.map((diagnostic) => diagnosticFromRecord(diagnostic, "warning")),
  ];
}

function diagnosticBadge(diagnostic: PackageDiagnostic) {
  return diagnostic.severity === "error" ? (
    <Badge variant="destructive">Blocking</Badge>
  ) : (
    <Badge className="border-chart-3/30 bg-chart-3/10 text-chart-3" variant="outline">Warning</Badge>
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
    const timestampDelta = Date.parse(right[timestampKey]) - Date.parse(left[timestampKey]);
    return timestampDelta === 0 ? right.id - left.id : timestampDelta;
  });
}

function savedInputEntryLabel(entry: WorkflowPackageRuntimeInputEntryRead, mode: SavedInputEntryMode) {
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
    <div className="min-w-0 space-y-4 overflow-x-hidden p-4" data-testid="workflow-package-launch-page">
      <Skeleton className="h-32 w-full" />
      <Skeleton className="h-44 w-full" />
      <Skeleton className="h-96 w-full" />
    </div>
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
    <div className="flex h-full min-w-0 flex-col gap-4 overflow-x-hidden overflow-y-auto p-4" data-testid="workflow-package-launch-page">
      <Card className="min-w-0 border-destructive/30 bg-destructive/5 shadow-sm" data-testid="workflow-package-launch-error">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive"><AlertCircle className="size-5" />{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild size="sm" variant="outline"><Link to={actionHref}>{actionLabel}</Link></Button>
        </CardContent>
      </Card>
    </div>
  );
}

function RuntimeInputValidationAlert({ errors }: { errors: readonly ApiErrorDetail[] }) {
  if (errors.length === 0) {
    return null;
  }

  return (
    <Alert data-testid="runtime-input-validation-feedback" variant="destructive">
      <AlertCircle />
      <AlertTitle>Runtime inputs need attention</AlertTitle>
      <AlertDescription>
        <ul className="list-disc space-y-1 pl-5">
          {errors.map((error) => (
            <li className="min-w-0 break-words" key={`${error.field}-${error.issue}`}>
              <code className="break-all rounded bg-muted/40 px-1 py-0.5 text-xs">{error.field}</code>: {error.issue}
            </li>
          ))}
        </ul>
      </AlertDescription>
    </Alert>
  );
}

function DiagnosticRows({ diagnostics }: { diagnostics: readonly PackageDiagnostic[] }) {
  if (diagnostics.length === 0) {
    return <p className="rounded-lg border border-dashed p-3 text-sm text-muted-foreground">No launch diagnostics reported.</p>;
  }

  return (
    <div className="space-y-2" data-testid="workflow-package-launch-diagnostics">
      {diagnostics.map((diagnostic) => (
        <div key={`${diagnostic.severity}-${diagnostic.field}-${diagnostic.issue}`} className="grid min-w-0 gap-2 rounded-lg border bg-background/60 p-3 text-sm md:grid-cols-[auto_minmax(0,12rem)_minmax(0,1fr)] md:items-center">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            {diagnosticBadge(diagnostic)}
            {diagnostic.connectionKind ? (
              <Badge variant={diagnostic.connectionKind === "deterministic_smoke" ? "secondary" : "outline"}>
                {connectionKindLabel(diagnostic.connectionKind)}
              </Badge>
            ) : null}
          </div>
          <code className="min-w-0 break-all rounded bg-muted/40 px-2 py-1 text-xs">{diagnostic.field}</code>
          <span className="min-w-0 break-words text-muted-foreground">{diagnostic.issue}</span>
        </div>
      ))}
    </div>
  );
}

function ModelConnectionModeSummary({ diagnostics, read }: { diagnostics: PackageDiagnostic[]; read: WorkflowPackageLaunchRead | undefined }) {
  if (!read) {
    return null;
  }

  const smokeCount = diagnostics.filter((diagnostic) => diagnostic.connectionKind === "deterministic_smoke").length;
  return (
    <div className="min-w-0 rounded-lg border bg-muted/30 p-4 text-sm text-muted-foreground" data-testid="workflow-package-model-connection-modes">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className="font-medium text-foreground">Model connection modes:</span>
        <Badge variant="outline">{connectionKindLabel("provider")}</Badge>
        {smokeCount > 0 ? <Badge variant="secondary">{connectionKindLabel("deterministic_smoke")}</Badge> : null}
      </div>
      <p className="mt-2">
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
  const { deletePending, entry, mode, onDelete, onLoad, onUpdate, updatePending } = props;
  const label = savedInputEntryLabel(entry, mode);
  const timestamp = mode === "history" ? entry.createdAt : entry.updatedAt;

  return (
    <div className="min-w-0 space-y-2 rounded-lg border bg-background/60 p-3" data-testid={`saved-input-${mode}-${entry.id}`}>
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-1">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <p className="min-w-0 max-w-full truncate text-sm font-medium">{label}</p>
            {entry.stale.stale ? <Badge className="border-chart-3/30 bg-chart-3/10 text-chart-3" variant="outline">Stale</Badge> : null}
          </div>
          <p className="text-xs text-muted-foreground">{mode === "history" ? "Captured" : "Updated"} {formatDateTime(timestamp)}</p>
        </div>
        <div className="flex w-full flex-wrap gap-2 sm:w-auto sm:justify-end">
          <Button className="h-7 px-2 text-xs" size="sm" type="button" variant="outline" aria-label={`Load ${mode} input ${label}`} onClick={() => onLoad(entry)}>
            Load
          </Button>
          {mode === "personal" ? (
            <>
              <Button className="h-7 px-2 text-xs" disabled={updatePending} size="sm" type="button" variant="outline" aria-label={`Overwrite personal input ${label}`} onClick={() => onUpdate(entry)}>
                {updatePending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : null}
                Overwrite
              </Button>
              <Button className="h-7 px-2 text-xs" disabled={deletePending} size="sm" type="button" variant="ghost" aria-label={`Delete personal input ${label}`} onClick={() => onDelete(entry)}>
                {deletePending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <Trash2 className="size-3" data-icon="inline-start" />}
                Delete
              </Button>
            </>
          ) : null}
        </div>
      </div>
      {entry.stale.stale ? (
        <div className="rounded-md border border-chart-3/30 bg-chart-3/10 px-2 py-1 text-xs text-muted-foreground">
          <p className="font-medium text-foreground">Saved against older workflow metadata.</p>
          {entry.stale.reasons.length > 0 ? (
            <ul className="mt-1 list-disc space-y-0.5 pl-4">
              {entry.stale.reasons.map((reason) => (
                <li key={`${entry.id}-${reason.field}-${reason.issue}`}>{reason.field}: {reason.issue}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
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
  const personalLimitReached = personalEntries.length >= SAVED_INPUT_ENTRY_LIMIT;
  const sortedPersonal = newestRuntimeInputEntries(personalEntries, "updatedAt");
  const sortedHistory = newestRuntimeInputEntries(historyEntries, "createdAt");
  return (
    <div className="min-w-0 space-y-3 rounded-xl border bg-muted/20 p-3" data-testid="runtime-input-saved-inputs-helper">
      <div className="flex min-w-0 flex-col gap-1">
        <div className="flex min-w-0 items-center justify-between gap-2">
          <h4 className="text-sm font-semibold">Saved Inputs</h4>
          <Badge variant="outline">{workflowKey || "workflow"}</Badge>
        </div>
        <p className="text-xs text-muted-foreground">Load presets or prior launch inputs into the raw JSON editor. Loading never queues a run.</p>
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
          <h5 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Personal</h5>
          <Badge variant="secondary">{personalEntries.length}/{SAVED_INPUT_ENTRY_LIMIT}</Badge>
        </div>
        <div className="flex min-w-0 flex-col gap-2 sm:flex-row">
          <Input className="h-8 min-w-0 text-xs" aria-label="Personal preset name" placeholder="Preset name" value={presetName} onChange={(event) => onPresetNameChange(event.target.value)} />
          <Button className="h-8 w-full text-xs sm:w-auto" disabled={createDisabled || createPending || personalLimitReached} size="sm" type="button" onClick={onCreate}>
            {createPending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <Save data-icon="inline-start" />}
            Save current JSON
          </Button>
        </div>
        {personalLimitReached ? <p className="text-xs text-destructive">Personal presets are capped at 20 per workflow. Delete one before saving another.</p> : null}
        {sortedPersonal.length === 0 ? <p className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">No personal presets saved for this workflow.</p> : null}
        <div className="space-y-2">
          {sortedPersonal.map((entry) => (
            <SavedInputEntryRow key={entry.id} deletePending={deletePending} entry={entry} mode="personal" updatePending={updatePending} onDelete={onDelete} onLoad={onLoad} onUpdate={onUpdate} />
          ))}
        </div>
      </div>
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h5 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">History</h5>
          <Badge variant="secondary">{historyEntries.length}/{SAVED_INPUT_ENTRY_LIMIT}</Badge>
        </div>
        {sortedHistory.length === 0 ? <p className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">No launch history captured for this workflow yet.</p> : null}
        <div className="space-y-2">
          {sortedHistory.map((entry) => (
            <SavedInputEntryRow key={entry.id} deletePending={false} entry={entry} mode="history" updatePending={false} onDelete={onDelete} onLoad={onLoad} onUpdate={onUpdate} />
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
  const [preflightRead, setPreflightRead] = useState<WorkflowPackageLaunchRead | undefined>(undefined);
  const [parametersText, setParametersText] = useState(() => stringifyJson({}));
  const [runtimeInputErrors, setRuntimeInputErrors] = useState<ApiErrorDetail[]>([]);
  const [personalPresetName, setPersonalPresetName] = useState("");
  const parametersEditedRef = useRef(false);
  const lastTemplateIdentityRef = useRef<string | null>(null);
  const resolvedWorkflowKey = workflowKey.trim();

  const packageQuery = useWorkflowPackage(packageId);
  const launchQuery = useWorkflowPackageLaunch(packageId, resolvedWorkflowKey || undefined);
  const preflightPackage = usePreflightWorkflowPackage();
  const createLaunch = useCreateWorkflowPackageLaunch();
  const runtimeInputRegistry = useWorkflowPackageRuntimeInputRegistry(packageId, resolvedWorkflowKey);
  const createPersonalEntry = useCreateWorkflowPackageRuntimeInputPersonalEntry();
  const updatePersonalEntry = useUpdateWorkflowPackageRuntimeInputPersonalEntry();
  const deletePersonalEntry = useDeleteWorkflowPackageRuntimeInputPersonalEntry();
  const launchRead = launchQuery.data;
  const readinessRead = preflightRead ?? launchRead;
  const diagnostics = useMemo(() => diagnosticsFromLaunch(readinessRead), [readinessRead]);
  const blockingCount = diagnostics.filter((diagnostic) => diagnostic.severity === "error").length;
  const warningCount = diagnostics.filter((diagnostic) => diagnostic.severity === "warning").length;
  const ready = readinessRead?.ready === true && blockingCount === 0;
  const inputSchemaFingerprint = useMemo(() => stringifyJson(launchRead?.inputSchema), [launchRead?.inputSchema]);
  const inputSchemaSnapshot = useMemo(
    () => inputSchemaFingerprint ? JSON.parse(inputSchemaFingerprint) as unknown : undefined,
    [inputSchemaFingerprint],
  );
  const inputTemplate = useMemo(() => createLaunchParametersTemplate(inputSchemaSnapshot), [inputSchemaSnapshot]);
  const parameterTemplateText = useMemo(() => resetLaunchParametersTemplate(inputTemplate), [inputTemplate]);
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
        description={isNotFoundError(packageQuery.error)
          ? "No saved workflow package exists for this launch route."
          : errorMessage(packageQuery.error, "Failed to load workflow package.")}
        title={isNotFoundError(packageQuery.error) ? "Workflow package not found" : "Workflow package could not be loaded"}
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
      const message = error instanceof Error ? error.message : "Runtime inputs JSON must be a valid object.";
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

  const runLaunchPreflight = async (): Promise<WorkflowPackageLaunchRead | null> => {
    try {
      const result = await preflightPackage.mutateAsync({
        packageId,
        payload: { parameters: {}, workflowKey: resolvedWorkflowKey || null },
      });
      setPreflightRead(result);
      const resultDiagnostics = diagnosticsFromLaunch(result);
      if (resultDiagnostics.some((diagnostic) => diagnostic.severity === "error")) {
        toast.warning("Package preflight found blocking diagnostics");
      } else {
        toast.success(result.warnings.length > 0 ? "Package preflight passed with warnings" : "Package preflight passed");
      }
      return result;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Package preflight failed.");
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
      toast.error(error instanceof Error ? error.message : "Failed to save personal runtime input preset.");
    }
  };

  const overwritePersonalInput = async (entry: WorkflowPackageRuntimeInputEntryRead) => {
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
      toast.error(error instanceof Error ? error.message : "Failed to update personal runtime input preset.");
    }
  };

  const deletePersonalInput = async (entry: WorkflowPackageRuntimeInputEntryRead) => {
    if (!resolvedWorkflowKey) {
      return;
    }
    try {
      await deletePersonalEntry.mutateAsync({ entryId: entry.id, packageId, workflowKey: resolvedWorkflowKey });
      toast.success("Deleted personal runtime input preset");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to delete personal runtime input preset.");
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
      const message = error instanceof Error ? error.message : "Runtime inputs JSON must be a valid object.";
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
      toast.error(error instanceof Error ? error.message : "Failed to launch workflow package.");
    }
  };

  return (
    <div className="flex h-full min-w-0 flex-col gap-4 overflow-x-hidden overflow-y-auto p-4 font-sans" data-testid="workflow-package-launch-page">
      <Card className="min-w-0 border-border/70 bg-card/80 shadow-sm backdrop-blur">
        <CardContent className="flex min-w-0 flex-col gap-4 p-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="secondary">Saved package launch</Badge>
              {ready ? <Badge className="border-positive/30 bg-positive/10 text-positive" variant="outline">Ready</Badge> : null}
              {blockingCount > 0 ? <Badge variant="destructive">{blockingCount} blocking</Badge> : null}
            </div>
            <div className="space-y-1">
              <h1 className="text-xl font-semibold tracking-tight">Launch Workflow Package</h1>
              <p className="font-mono text-xs text-muted-foreground">{packageQuery.data.key}</p>
              <p className="max-w-3xl text-sm text-muted-foreground">{packageQuery.data.description || "Queue a run from the currently persisted workflow package."}</p>
            </div>
          </div>
          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row lg:justify-end" data-testid="workflow-package-launch-actions">
            <Button asChild className="w-full sm:w-auto" size="sm" variant="outline"><Link to={`/workflow-packages/${packageId}`}>Open authoring editor</Link></Button>
          </div>
        </CardContent>
      </Card>

      <Alert className="border-chart-3/30 bg-chart-3/10">
        <AlertCircle />
        <AlertTitle>Launch uses persisted package state</AlertTitle>
        <AlertDescription>
          This route reads the saved package summary and launch metadata from the backend. Unsaved changes in the authoring editor are not included until that package is saved.
        </AlertDescription>
      </Alert>

      <Card className="min-w-0 border-border/70 bg-card/80 shadow-sm backdrop-blur" data-testid="workflow-package-launch-context">
        <CardHeader className="border-b pb-4">
          <CardTitle>{packageQuery.data.name}</CardTitle>
          <CardDescription>Read-only launch context for package #{packageQuery.data.id}.</CardDescription>
        </CardHeader>
        <CardContent className="grid min-w-0 gap-3 p-4 text-sm text-muted-foreground md:grid-cols-2 xl:grid-cols-4">
          <div className="min-w-0 break-words"><span className="font-medium text-foreground">Manifest:</span> <span className="font-mono text-xs break-all">{packageQuery.data.manifestHash ?? "Not recorded"}</span></div>
          <div className="min-w-0 break-words"><span className="font-medium text-foreground">Compiled:</span> <span className="font-mono text-xs break-all">{packageQuery.data.compiledHash ?? "Not recorded"}</span></div>
          <div className="min-w-0 break-words"><span className="font-medium text-foreground">Updated:</span> {formatDateTime(packageQuery.data.updatedAt)}</div>
          <div className="min-w-0 break-words"><span className="font-medium text-foreground">Created:</span> {formatDateTime(packageQuery.data.createdAt)}</div>
        </CardContent>
      </Card>

      <Card className="min-w-0 border-border/70 bg-card/80 shadow-sm backdrop-blur" data-testid="workflow-package-preflight-panel">
        <CardHeader className="border-b pb-4">
          <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0 space-y-1">
              <CardTitle>Launch readiness</CardTitle>
              <CardDescription>Load launch metadata, preflight the saved package, and review launch-only diagnostics before queueing a run.</CardDescription>
            </div>
            <Button className="w-full sm:w-auto" disabled={preflightPackage.isPending} size="sm" type="button" variant="outline" onClick={() => void runLaunchPreflight()}>
              {preflightPackage.isPending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <FileCheck2 data-icon="inline-start" />}
              Run preflight
            </Button>
          </div>
        </CardHeader>
        <CardContent className="min-w-0 space-y-4 p-4">
          {launchQuery.isPending ? <div className="min-w-0 rounded-xl border bg-muted/30 p-4 text-sm text-muted-foreground">Loading launch metadata...</div> : null}
          {launchQuery.isError ? (
            <Alert data-testid="workflow-package-launch-metadata-error" variant="destructive">
              <AlertCircle />
              <AlertTitle>Launch metadata unavailable</AlertTitle>
              <AlertDescription>{errorMessage(launchQuery.error, "Failed to load launch metadata.")}</AlertDescription>
            </Alert>
          ) : null}
          <Alert className={ready ? "min-w-0 border-positive/30 bg-positive/10" : blockingCount > 0 ? "min-w-0 border-destructive/30" : "min-w-0 border-chart-3/30 bg-chart-3/10"} data-testid="workflow-package-preflight-status" variant={blockingCount > 0 ? "destructive" : "default"}>
            {ready ? <CheckCircle2 /> : <AlertCircle />}
            <AlertTitle>{ready ? "Ready to launch" : "Needs attention"}</AlertTitle>
            <AlertDescription>
              {readinessRead ? `${blockingCount} blocking issue${blockingCount === 1 ? "" : "s"} and ${warningCount} warning${warningCount === 1 ? "" : "s"} for ${readinessRead.packageKey}.` : "Launch metadata has not loaded yet."}
            </AlertDescription>
          </Alert>
          <ModelConnectionModeSummary diagnostics={diagnostics} read={readinessRead} />
          <DiagnosticRows diagnostics={diagnostics} />
        </CardContent>
      </Card>

      <Card className="min-w-0 border-border/70 bg-card/80 shadow-sm backdrop-blur" data-testid="workflow-package-launch-tab">
        <CardHeader className="border-b pb-4">
          <CardTitle>Launch package run</CardTitle>
          <CardDescription>Select a workflow key, provide runtime inputs, preflight, then queue a run from the saved package.</CardDescription>
        </CardHeader>
        <CardContent className="min-w-0 space-y-4 p-4">
          <div className="min-w-0 space-y-2"><Label htmlFor="workflow-key">Workflow key</Label><Input id="workflow-key" aria-label="Workflow key" placeholder="Workflow key" value={workflowKey} onChange={(event) => updateWorkflowKey(event.target.value)} /></div>
          <Card className="min-w-0 bg-background/60">
            <CardHeader>
              <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0 space-y-1">
                  <CardTitle className="text-base">Runtime inputs</CardTitle>
                  <CardDescription>Edit the schema-derived template as raw JSON. Launch parameters must remain a JSON object.</CardDescription>
                </div>
                <Button className="w-full sm:w-auto" size="sm" type="button" variant="outline" onClick={resetParameters}>Reset to template</Button>
              </div>
            </CardHeader>
            <CardContent className="min-w-0 space-y-4">
              {!inputTemplate.schemaSupported ? (
                <Alert className="border-chart-3/30 bg-chart-3/10">
                  <AlertCircle />
                  <AlertTitle>Schema template started empty</AlertTitle>
                  <AlertDescription>
                    <p>{inputTemplate.reason}</p>
                    {inputTemplate.issues.length > 0 ? (
                      <ul className="list-disc pl-5">
                        {inputTemplate.issues.map((issue) => <li key={`${issue.field}-${issue.issue}`}>{issue.field}: {issue.issue}</li>)}
                      </ul>
                    ) : null}
                  </AlertDescription>
                </Alert>
              ) : null}
              <RuntimeInputValidationAlert errors={runtimeInputErrors} />
              <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(18rem,22rem)]" data-testid="runtime-input-console-grid">
                <div className="min-w-0 space-y-2" data-testid="runtime-input-json-panel">
                  <Label htmlFor="runtime-json">Runtime inputs JSON</Label>
                  <Textarea id="runtime-json" aria-label="Runtime inputs JSON" className="min-h-72 max-w-full overflow-x-auto whitespace-pre font-mono text-xs" rows={14} value={parametersText} onChange={(event) => updateParametersText(event.target.value)} />
                </div>
                <SavedInputsHelper
                  createDisabled={!resolvedWorkflowKey || runtimeInputRegistry.isPending || runtimeInputRegistry.isFetching || !personalPresetName.trim()}
                  createPending={createPersonalEntry.isPending}
                  deletePending={deletePersonalEntry.isPending}
                  error={runtimeInputRegistry.isError ? runtimeInputRegistry.error : null}
                  historyEntries={runtimeInputRegistry.data?.history ?? []}
                  loading={runtimeInputRegistry.isPending || runtimeInputRegistry.isFetching}
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
          <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:justify-end" data-testid="workflow-package-run-actions">
            <Button className="w-full sm:w-auto" disabled={preflightPackage.isPending || launchQuery.isPending} type="button" variant="outline" onClick={() => void runLaunchPreflight()}>
              {preflightPackage.isPending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <FileCheck2 data-icon="inline-start" />}
              Run preflight
            </Button>
            <Button className="w-full sm:w-auto" disabled={createLaunch.isPending || preflightPackage.isPending || launchQuery.isPending || launchQuery.isError} type="button" onClick={() => void launchPackage()}>
              {createLaunch.isPending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <PlayCircle data-icon="inline-start" />}
              Launch Run
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
