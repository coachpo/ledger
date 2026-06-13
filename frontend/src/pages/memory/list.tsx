import { FileText, History, Plus, RotateCcw, Search, ShieldCheck, SquarePen, X } from "lucide-react";
import { type ReactNode, useId, useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";

import { EmptyStatePanel } from "@/components/shared/empty-state-panel";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { PageContextBar } from "@/components/shared/page-context-bar";
import { ResourceRowCard } from "@/components/shared/resource-row-card";
import {
  ResourceStatusBadge,
  ResourceStatusStrip,
  type ResourceStatusTone,
} from "@/components/shared/resource-status-strip";
import {
  SheetInspectorLayout,
  SplitInspectorLayout,
  type SplitInspectorLayoutTab,
} from "@/components/shared/split-inspector-layout";
import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useIsMobile } from "@/components/ui/use-mobile";
import { cn } from "@/components/ui/utils";
import { useSplitInspectorState } from "@/hooks/use-split-inspector-state";
import {
  useAdminMemoryEntries,
  useAdminMemoryEntry,
  useAdminMemoryEvents,
  useAdminMemoryRevisions,
  useCreateAdminMemoryEntry,
  useCreateAdminMemoryRevision,
  useUpdateAdminMemoryStatus,
} from "@/hooks/use-memory";
import { formatDateTime } from "@/lib/format";
import type {
  MemoryAdminCreateRequest,
  MemoryAdminEntryRead,
  MemoryAdminEventListRead,
  MemoryAdminListItemRead,
  MemoryAdminListParams,
  MemoryAdminRevisionCreateRequest,
  MemoryAdminRevisionListRead,
  MemoryAdminStatusUpdateRequest,
  MemoryLifecycleStatus,
  MemoryProvenance,
  MemoryRevisionAction,
  MemoryScope,
  MemoryScopeType,
  MemorySubjectRef,
} from "@/lib/types/memory";

const DEFAULT_OPERATOR_AGENT_KEY = "local-instance-operator";
const ALL_SCOPES_FILTER = "__all_scopes__";
const ALL_STATUSES_FILTER = "__all_statuses__";
const STATUS_VALUES: readonly MemoryLifecycleStatus[] = ["pending", "resolved", "expired"];
const SCOPE_TYPE_VALUES: readonly MemoryScopeType[] = [
  "package",
  "workflow",
  "run",
  "agent",
  "namespace",
];
const RUNTIME_IMPACT_COPY =
  "Resolved memory in a matching scope may appear in future workflow lookup; pending or expired memory remains visible here for operators but is excluded from default runtime lookup.";

type MemoryInspectorTab = "detail" | "revisions" | "events";
type JsonObject = Record<string, unknown>;
type AdminRevisionVariables = {
  memoryId: string;
  payload: MemoryAdminRevisionCreateRequest;
};

type CreateDraft = {
  agentKey: string;
  attributesJson: string;
  content: string;
  kind: string;
  packageKey: string;
  runId: string;
  scopeKey: string;
  scopeType: MemoryScopeType;
  status: MemoryLifecycleStatus;
  subjectId: string;
  subjectKind: string;
  subjectLabel: string;
  summary: string;
  workflowKey: string;
};

type RevisionDraft = {
  attributesJson: string;
  content: string;
  summary: string;
};

type StatusDraft = {
  attributesJson: string;
  status: MemoryLifecycleStatus;
  summary: string;
};

function optionalText(value: string): string | undefined {
  const normalized = value.trim();
  return normalized ? normalized : undefined;
}

function optionalRunId(value: string): number | undefined {
  const normalized = value.trim();
  if (!normalized) {
    return undefined;
  }
  const parsed = Number(normalized);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : undefined;
}

function parseRequiredRunId(value: string): number | null {
  return optionalRunId(value) ?? null;
}

function parseJsonObject(value: string, label: string): JsonObject | null {
  const normalized = value.trim();
  if (!normalized) {
    return {};
  }
  try {
    const parsed = JSON.parse(normalized);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as JsonObject;
    }
  } catch {
    // User-editable JSON is validated at the form boundary.
  }
  toast.error(`${label} must be a JSON object.`);
  return null;
}

function titleCase(value: string): string {
  return value
    .replace(/[-_]/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function statusTone(status: MemoryLifecycleStatus): ResourceStatusTone {
  if (status === "resolved") {
    return "success";
  }
  if (status === "pending") {
    return "warning";
  }
  return "muted";
}

function revisionTone(action: MemoryRevisionAction): ResourceStatusTone {
  return action === "created" ? "success" : action === "superseded" ? "muted" : "neutral";
}

function formatScope(scope: MemoryScope): string {
  return scope.scopeType === "namespace"
    ? `Namespace ${scope.scopeKey}`
    : `${titleCase(scope.scopeType)} ${scope.scopeKey}`;
}

function formatProvenance(provenance: MemoryProvenance): string {
  const workflow = provenance.workflowKey ? ` · ${provenance.workflowKey}` : "";
  const creator = provenance.createdByType ? `${provenance.createdByType} · ` : "";
  return `${creator}${provenance.agentKey}@${provenance.agentVersion}${workflow} · run #${provenance.runId}`;
}

function subjectRefSummary(item: Pick<MemoryAdminListItemRead, "subjectRefs">): string {
  if (item.subjectRefs.length === 0) {
    return "No subject refs";
  }
  return item.subjectRefs.map((subject) => `${subject.kind}:${subject.id}`).join(" · ");
}

function buildSubjectRefs(draft: CreateDraft): MemorySubjectRef[] {
  const subjectKind = optionalText(draft.subjectKind);
  const subjectId = optionalText(draft.subjectId);
  if (!subjectKind || !subjectId) {
    return [];
  }
  return [
    {
      id: subjectId,
      kind: subjectKind,
      label: optionalText(draft.subjectLabel) ?? null,
    },
  ];
}

function buildOperatorProvenance({
  agentKey,
  runId,
  workflowKey,
}: {
  agentKey: string;
  runId: number;
  workflowKey?: string;
}): MemoryProvenance {
  return {
    agentKey: optionalText(agentKey) ?? DEFAULT_OPERATOR_AGENT_KEY,
    agentVersion: 1,
    createdByType: "operator",
    runId,
    ...(workflowKey ? { workflowKey } : {}),
  };
}

function buildAdminListParams({
  agentKey,
  kind,
  packageKey,
  query,
  runId,
  scopeType,
  status,
  workflowKey,
}: {
  agentKey: string;
  kind: string;
  packageKey: string;
  query: string;
  runId: string;
  scopeType: string;
  status: string;
  workflowKey: string;
}): MemoryAdminListParams {
  const params: MemoryAdminListParams = {};
  const normalizedPackageKey = optionalText(packageKey);
  const normalizedWorkflowKey = optionalText(workflowKey);
  const normalizedAgentKey = optionalText(agentKey);
  const normalizedKind = optionalText(kind);
  const normalizedQuery = optionalText(query);
  const parsedRunId = optionalRunId(runId);

  if (normalizedPackageKey) params.packageKey = normalizedPackageKey;
  if (normalizedWorkflowKey) params.workflowKey = normalizedWorkflowKey;
  if (normalizedAgentKey) params.agentKey = normalizedAgentKey;
  if (parsedRunId) params.runId = parsedRunId;
  if (scopeType !== ALL_SCOPES_FILTER) params.scopeType = scopeType as MemoryScopeType;
  if (normalizedKind) params.kind = normalizedKind;
  if (status !== ALL_STATUSES_FILTER) params.status = status as MemoryLifecycleStatus;
  if (normalizedQuery) params.query = normalizedQuery;

  return params;
}

function JsonBlock({ label, value }: { label: string; value: unknown }) {
  return (
    <section className="flex min-w-0 flex-col gap-2">
      <h4 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </h4>
      <pre className="max-h-56 overflow-auto rounded-md border bg-muted/20 p-3 text-xs">
        {JSON.stringify(value, null, 2)}
      </pre>
    </section>
  );
}

function DetailField({ label, mono = false, value }: { label: string; mono?: boolean; value: ReactNode }) {
  return (
    <div className="min-w-0 rounded-md border bg-muted/20 p-3">
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd className={cn("mt-1 break-words text-sm", mono ? "font-mono text-xs" : null)}>{value}</dd>
    </div>
  );
}

function TextField({
  label,
  onChange,
  placeholder,
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  placeholder?: string;
  value: string;
}) {
  const reactId = useId();
  const id = `memory-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${reactId}`;

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <Label className="text-sm" htmlFor={id}>{label}</Label>
      <Input
        className="h-8 text-xs"
        id={id}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        value={value}
      />
    </div>
  );
}

function TextareaField({
  label,
  onChange,
  placeholder,
  rows = 4,
  value,
}: {
  label: string;
  onChange: (value: string) => void;
  placeholder?: string;
  rows?: number;
  value: string;
}) {
  const reactId = useId();
  const id = `memory-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${reactId}`;

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <Label className="text-sm" htmlFor={id}>{label}</Label>
      <Textarea
        className="text-xs"
        id={id}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        rows={rows}
        value={value}
      />
    </div>
  );
}

function MemoryContextContract({ onReset }: { onReset: () => void }) {
  return (
    <div data-testid="memory-admin-notice">
      <PageContextBar
        actions={
          <Button onClick={onReset} size="sm" type="button" variant="outline">
            <RotateCcw data-icon="inline-start" />
            Reset filters
          </Button>
        }
        description="Manage canonical memory across packages, scopes, and lifecycle states from the trusted local operator console."
        layout="toolbar"
        meta={
          <span>
            Mixed package rows are intentional here; runtime lookup still resolves only matching scopes and statuses.
          </span>
        }
        title="Memory"
      />
    </div>
  );
}

function MemoryLoadState({ error }: { error: unknown }) {
  return (
    <InventoryStatePanel
      description={error instanceof Error ? error.message : "The admin memory request failed."}
      testId="memory-load-error"
      title="Unable to load operator memory"
      tone="danger"
    />
  );
}

function QueryStateCard({ label }: { label: string }) {
  return (
    <Card>
      <CardContent className="py-8 text-sm text-muted-foreground">{label}</CardContent>
    </Card>
  );
}

function MemoryListCard({
  item,
  onSelect,
  selected,
}: {
  item: MemoryAdminListItemRead;
  onSelect: (memoryId: string) => void;
  selected: boolean;
}) {
  return (
    <ResourceRowCard
      actions={
        <Button
          className="w-full sm:w-auto"
          onClick={() => onSelect(item.memoryId)}
          size="sm"
          type="button"
          variant={selected ? "secondary" : "outline"}
        >
          <FileText data-icon="inline-start" />
          Open memory
        </Button>
      }
      badges={
        <>
          <Badge variant="outline">{item.kind}</Badge>
          <ResourceStatusBadge label={item.status} tone={statusTone(item.status)} />
          <Badge variant="secondary">{formatScope(item.scope)}</Badge>
        </>
      }
      description={<span className="line-clamp-2">{item.excerpt}</span>}
      density="compactPlus"
      metadata={`${subjectRefSummary(item)} · ${formatProvenance(item.provenance)}`}
      selected={selected}
      testId={`memory-row-${item.memoryId}`}
      title={item.summary}
      footer={item.lastEventType ? `Latest audit event: ${item.lastEventType}` : `Updated ${formatDateTime(item.updatedAt ?? item.createdAt)}`}
    />
  );
}

function SelectField<TValue extends string>({
  children,
  label,
  onChange,
  value,
}: {
  children: ReactNode;
  label: string;
  onChange: (value: TValue) => void;
  value: TValue;
}) {
  const reactId = useId();
  const id = `memory-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${reactId}`;
  return (
    <div className="flex min-w-0 flex-col gap-2">
      <Label className="text-sm" htmlFor={id}>{label}</Label>
      <Select onValueChange={(next) => onChange(next as TValue)} value={value}>
        <SelectTrigger id={id} size="sm">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>{children}</SelectGroup>
        </SelectContent>
      </Select>
    </div>
  );
}

function RuntimeImpactNotice() {
  return (
    <div className="rounded-md border bg-muted/20 p-3 text-xs leading-5 text-muted-foreground" data-testid="memory-runtime-impact-copy">
      {RUNTIME_IMPACT_COPY}
    </div>
  );
}

function MemoryAdminFilterControls({
  agentKey,
  kind,
  packageKey,
  query,
  runId,
  scopeType,
  setAgentKey,
  setKind,
  setPackageKey,
  setQuery,
  setRunId,
  setScopeType,
  setStatus,
  setWorkflowKey,
  status,
  total,
  workflowKey,
}: {
  agentKey: string;
  kind: string;
  packageKey: string;
  query: string;
  runId: string;
  scopeType: string;
  setAgentKey: (value: string) => void;
  setKind: (value: string) => void;
  setPackageKey: (value: string) => void;
  setQuery: (value: string) => void;
  setRunId: (value: string) => void;
  setScopeType: (value: string) => void;
  setStatus: (value: string) => void;
  setWorkflowKey: (value: string) => void;
  status: string;
  total: number;
  workflowKey: string;
}) {
  return (
    <Card data-testid="memory-admin-filter-controls">
      <CardHeader className="px-4 pt-4">
        <div className="flex min-w-0 flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <CardTitle className="text-base">Operator filters</CardTitle>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              Narrow the admin-managed corpus by package, workflow, agent, run, scope type, kind, status, or lexical query. Clearing all filters restores the full trusted corpus.
            </p>
          </div>
          <ResourceStatusStrip
            items={[
              { label: "Loaded", value: `${total} memory entries`, tone: "neutral" },
              { label: "Mode", value: "trusted operator", tone: "success" },
            ]}
          />
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 px-4 pb-4">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4" data-testid="memory-admin-filter-card">
          <TextField label="Package key" onChange={setPackageKey} placeholder="pkg_alpha" value={packageKey} />
          <TextField label="Workflow key" onChange={setWorkflowKey} placeholder="risk-review" value={workflowKey} />
          <TextField label="Agent key" onChange={setAgentKey} placeholder="analyst" value={agentKey} />
          <TextField label="Run id" onChange={setRunId} placeholder="41" value={runId} />
        </div>
        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_12rem_12rem_12rem]">
          <div className="relative" role="search">
            <Search className="pointer-events-none absolute left-2.5 top-2 size-4 text-muted-foreground" />
            <Input
              aria-label="Search canonical memory"
              className="h-8 pl-8 text-xs"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search summaries, content, or subject refs..."
              value={query}
            />
          </div>
          <TextField label="Kind" onChange={setKind} placeholder="insight" value={kind} />
          <SelectField label="Scope type" onChange={setScopeType} value={scopeType}>
            <SelectItem value={ALL_SCOPES_FILTER}>All scopes</SelectItem>
            {SCOPE_TYPE_VALUES.map((value) => <SelectItem key={value} value={value}>{titleCase(value)}</SelectItem>)}
          </SelectField>
          <SelectField label="Status" onChange={setStatus} value={status}>
            <SelectItem value={ALL_STATUSES_FILTER}>All statuses</SelectItem>
            {STATUS_VALUES.map((value) => <SelectItem key={value} value={value}>{titleCase(value)}</SelectItem>)}
          </SelectField>
        </div>
      </CardContent>
    </Card>
  );
}

function createInitialDraft(): CreateDraft {
  return {
    agentKey: DEFAULT_OPERATOR_AGENT_KEY,
    attributesJson: "{}",
    content: "",
    kind: "note",
    packageKey: "",
    runId: "",
    scopeKey: "",
    scopeType: "package",
    status: "resolved",
    subjectId: "",
    subjectKind: "",
    subjectLabel: "",
    summary: "",
    workflowKey: "",
  };
}

function MemoryCreateDialog({
  onCreate,
  pending,
}: {
  onCreate: (payload: MemoryAdminCreateRequest) => Promise<void>;
  pending: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<CreateDraft>(() => createInitialDraft());
  const update = <TKey extends keyof CreateDraft>(key: TKey, value: CreateDraft[TKey]) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };
  const submit = async (event: { preventDefault: () => void }) => {
    event.preventDefault();
    const scopeKey = optionalText(draft.scopeKey);
    const packageKey = optionalText(draft.packageKey);
    const runId = parseRequiredRunId(draft.runId);
    const attributes = parseJsonObject(draft.attributesJson, "Create attributes");
    if (!scopeKey || !packageKey || !runId || !attributes) {
      toast.error("Create memory needs package key, run id, scope key, and valid attributes.");
      return;
    }
    await onCreate({
      attributes,
      content: draft.content,
      kind: optionalText(draft.kind) ?? "note",
      provenance: buildOperatorProvenance({
        agentKey: draft.agentKey,
        runId,
        workflowKey: optionalText(draft.workflowKey),
      }),
      scope: { scopeKey, scopeType: draft.scopeType },
      status: draft.status,
      subjectRefs: buildSubjectRefs(draft),
      summary: draft.summary,
    });
    setDraft(createInitialDraft());
    setOpen(false);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" type="button">
          <Plus data-icon="inline-start" />
          Create memory
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Create operator memory</DialogTitle>
          <DialogDescription>
            Write canonical memory with explicit scope, lifecycle status, and local operator provenance.
          </DialogDescription>
        </DialogHeader>
        <form className="grid gap-4" onSubmit={submit}>
          <RuntimeImpactNotice />
          <div className="grid gap-3 md:grid-cols-2">
            <TextField label="Summary" onChange={(value) => update("summary", value)} value={draft.summary} />
            <TextField label="Kind" onChange={(value) => update("kind", value)} value={draft.kind} />
            <TextField label="Package key" onChange={(value) => update("packageKey", value)} value={draft.packageKey} />
            <TextField label="Workflow key" onChange={(value) => update("workflowKey", value)} value={draft.workflowKey} />
            <TextField label="Agent key" onChange={(value) => update("agentKey", value)} value={draft.agentKey} />
            <TextField label="Run id" onChange={(value) => update("runId", value)} value={draft.runId} />
            <SelectField label="Scope type" onChange={(value) => update("scopeType", value)} value={draft.scopeType}>
              {SCOPE_TYPE_VALUES.map((value) => <SelectItem key={value} value={value}>{titleCase(value)}</SelectItem>)}
            </SelectField>
            <TextField label="Scope key" onChange={(value) => update("scopeKey", value)} value={draft.scopeKey} />
            <SelectField label="Initial status" onChange={(value) => update("status", value)} value={draft.status}>
              {STATUS_VALUES.map((value) => <SelectItem key={value} value={value}>{titleCase(value)}</SelectItem>)}
            </SelectField>
            <TextField label="Subject kind" onChange={(value) => update("subjectKind", value)} value={draft.subjectKind} />
            <TextField label="Subject id" onChange={(value) => update("subjectId", value)} value={draft.subjectId} />
            <TextField label="Subject label" onChange={(value) => update("subjectLabel", value)} value={draft.subjectLabel} />
          </div>
          <TextareaField label="Content" onChange={(value) => update("content", value)} rows={5} value={draft.content} />
          <TextareaField label="Attributes JSON" onChange={(value) => update("attributesJson", value)} rows={3} value={draft.attributesJson} />
          <DialogFooter>
            <Button disabled={pending} type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button disabled={pending} type="submit">Create memory</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function RevisionDialog({
  detail,
  onRevise,
  pending,
}: {
  detail: MemoryAdminEntryRead | undefined;
  onRevise: (payload: AdminRevisionVariables) => Promise<void>;
  pending: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<RevisionDraft>({ attributesJson: "{}", content: "", summary: "" });
  const selectedMemoryId = detail?.memoryId;
  const update = <TKey extends keyof RevisionDraft>(key: TKey, value: RevisionDraft[TKey]) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };
  const submit = async (event: { preventDefault: () => void }) => {
    event.preventDefault();
    if (!detail || !selectedMemoryId) {
      return;
    }
    const attributes = parseJsonObject(draft.attributesJson, "Revision attributes");
    if (!attributes) {
      return;
    }
    await onRevise({
      memoryId: selectedMemoryId,
      payload: {
        attributes,
        content: draft.content,
        provenance: { ...detail.provenance, createdByType: "operator" },
        subjectRefs: detail.subjectRefs,
        summary: draft.summary,
      },
    });
    setDraft({ attributesJson: "{}", content: "", summary: "" });
    setOpen(false);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button disabled={!detail} size="sm" type="button" variant="outline">
          <SquarePen data-icon="inline-start" />
          Revise
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Revise selected memory</DialogTitle>
          <DialogDescription>
            Add a new operator-authored revision while preserving the selected memory identity and audit trail.
          </DialogDescription>
        </DialogHeader>
        <form className="grid gap-4" onSubmit={submit}>
          <RuntimeImpactNotice />
          <TextField label="Revision summary" onChange={(value) => update("summary", value)} value={draft.summary} />
          <TextareaField label="Revision content" onChange={(value) => update("content", value)} rows={6} value={draft.content} />
          <TextareaField label="Revision attributes JSON" onChange={(value) => update("attributesJson", value)} rows={3} value={draft.attributesJson} />
          <DialogFooter>
            <Button disabled={pending} type="button" variant="outline" onClick={() => setOpen(false)}>Cancel</Button>
            <Button disabled={pending || !detail} type="submit">Create revision</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function StatusUpdateForm({
  detail,
  onUpdateStatus,
  pending,
}: {
  detail: MemoryAdminEntryRead | undefined;
  onUpdateStatus: (payload: { memoryId: string; payload: MemoryAdminStatusUpdateRequest }) => Promise<void>;
  pending: boolean;
}) {
  const [draft, setDraft] = useState<StatusDraft>({ attributesJson: "{}", status: "resolved", summary: "" });
  const selectedMemoryId = detail?.memoryId;
  const update = <TKey extends keyof StatusDraft>(key: TKey, value: StatusDraft[TKey]) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };
  const submit = async (event: { preventDefault: () => void }) => {
    event.preventDefault();
    if (!selectedMemoryId) {
      return;
    }
    const attributes = parseJsonObject(draft.attributesJson, "Status attributes");
    if (!attributes) {
      return;
    }
    await onUpdateStatus({
      memoryId: selectedMemoryId,
      payload: {
        attributes,
        observedAt: new Date().toISOString(),
        status: draft.status,
        summary: optionalText(draft.summary),
      },
    });
    toast.success("Memory status updated");
  };

  return (
    <form className="grid gap-3 rounded-md border bg-muted/20 p-3" data-testid="memory-status-form" onSubmit={submit}>
      <div className="flex min-w-0 items-center gap-2 text-sm font-medium">
        <ShieldCheck className="size-4" />
        Lifecycle status
      </div>
      <RuntimeImpactNotice />
      <div className="grid gap-3 md:grid-cols-2">
        <SelectField label="New status" onChange={(value) => update("status", value)} value={draft.status}>
          {STATUS_VALUES.map((value) => <SelectItem key={value} value={value}>{titleCase(value)}</SelectItem>)}
        </SelectField>
        <TextField label="Status summary" onChange={(value) => update("summary", value)} value={draft.summary} />
      </div>
      <TextareaField label="Status attributes JSON" onChange={(value) => update("attributesJson", value)} rows={3} value={draft.attributesJson} />
      <div>
        <Button disabled={pending || !detail} size="sm" type="submit">Update status</Button>
      </div>
    </form>
  );
}

function DetailInspection({
  detail,
  onUpdateStatus,
  statusPending,
}: {
  detail: MemoryAdminEntryRead;
  onUpdateStatus: (payload: { memoryId: string; payload: MemoryAdminStatusUpdateRequest }) => Promise<void>;
  statusPending: boolean;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-5" data-testid="memory-detail-panel">
      <ResourceStatusStrip
        items={[
          { label: "Status", value: detail.status, tone: statusTone(detail.status) },
          { label: "Kind", value: detail.kind },
          { label: "Scope", value: formatScope(detail.scope), tone: "muted" },
        ]}
      />
      <div className="rounded-md border bg-muted/20 p-3 text-sm">
        <p className="whitespace-pre-wrap break-words">{detail.content}</p>
      </div>
      <dl className="grid gap-3 text-sm md:grid-cols-2">
        <DetailField label="Memory id" mono value={detail.memoryId} />
        <DetailField label="Revision id" mono value={detail.revisionId} />
        <DetailField label="Created" value={formatDateTime(detail.createdAt)} />
        <DetailField label="Updated" value={formatDateTime(detail.updatedAt ?? detail.createdAt)} />
        <DetailField label="Provenance" value={formatProvenance(detail.provenance)} />
        <DetailField label="Latest revision" value={`v${detail.revision.version} · ${detail.revision.contentHash}`} />
      </dl>
      <JsonBlock label="Attributes" value={detail.attributes} />
      {detail.outcome ? <JsonBlock label="Outcome" value={detail.outcome} /> : null}
      {detail.reflections.length > 0 ? <JsonBlock label="Reflections" value={detail.reflections} /> : null}
      {detail.auditLinks ? <JsonBlock label="Audit links" value={detail.auditLinks} /> : null}
      <StatusUpdateForm detail={detail} onUpdateStatus={onUpdateStatus} pending={statusPending} />
    </div>
  );
}

function RevisionCard({ revision }: { revision: MemoryAdminRevisionListRead["items"][number] }) {
  return (
    <article className="flex min-w-0 flex-col gap-2 rounded-md border bg-background/70 p-3 text-sm">
      <div className="flex flex-wrap gap-2">
        <Badge variant="outline">v{revision.version}</Badge>
        <ResourceStatusBadge label={revision.revisionAction} tone={revisionTone(revision.revisionAction)} />
        <ResourceStatusBadge label={revision.status} tone={statusTone(revision.status)} />
      </div>
      <p className="break-words font-medium">{revision.summary}</p>
      <p className="break-words text-muted-foreground">{revision.content}</p>
      <p className="break-words text-xs text-muted-foreground">
        {formatDateTime(revision.createdAt)} · {revision.sourceAgentKey} · run #{revision.sourceRunId}
      </p>
    </article>
  );
}

function RevisionsInspection({ revisions }: { revisions: readonly MemoryAdminRevisionListRead["items"][number][] }) {
  if (revisions.length === 0) {
    return <EmptyStatePanel description="This memory has no operator-visible revision history yet." title="No revisions returned" />;
  }

  return (
    <section className="flex min-w-0 flex-col gap-3" data-testid="memory-revisions-panel">
      {revisions.map((revision) => <RevisionCard key={revision.revisionId} revision={revision} />)}
    </section>
  );
}

function EventCard({ event }: { event: MemoryAdminEventListRead["items"][number] }) {
  return (
    <article className="flex min-w-0 flex-col gap-3 rounded-md border bg-background/70 p-3 text-sm">
      <div className="flex flex-wrap gap-2">
        <Badge variant="outline">event #{event.eventId}</Badge>
        <Badge variant="secondary">{event.eventType}</Badge>
        {event.retrievalMode ? <Badge variant="outline">{event.retrievalMode}</Badge> : null}
      </div>
      <p className="text-xs text-muted-foreground">
        {formatDateTime(event.createdAt)} · run #{event.runId}
      </p>
      {event.excerpt ? <p className="break-words text-muted-foreground">{event.excerpt}</p> : null}
      <JsonBlock label="Result snapshot" value={event.resultSnapshot} />
      <JsonBlock label="Status snapshot" value={event.statusSnapshot} />
    </article>
  );
}

function EventsInspection({ events }: { events: readonly MemoryAdminEventListRead["items"][number][] }) {
  if (events.length === 0) {
    return <EmptyStatePanel description="No audit events are recorded for this memory yet." title="No events returned" />;
  }

  return (
    <section className="flex min-w-0 flex-col gap-3" data-testid="memory-events-panel">
      {events.map((event) => <EventCard event={event} key={event.eventId} />)}
    </section>
  );
}

function MemoryListPane({
  hasActiveFilters,
  isError,
  isPending,
  items,
  listError,
  onSelect,
  selectedMemoryId,
  total,
}: {
  hasActiveFilters: boolean;
  isError: boolean;
  isPending: boolean;
  items: readonly MemoryAdminListItemRead[];
  listError: unknown;
  onSelect: (memoryId: string) => void;
  selectedMemoryId: string | null;
  total: number;
}) {
  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b bg-card/80 px-4 py-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold tracking-tight">Trusted operator corpus</h2>
          <p className="break-words text-xs text-muted-foreground">
            Rows from different packages and scopes can appear together by design.
          </p>
        </div>
        <Badge variant="outline">{items.length} shown · {total} total</Badge>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3">
        <div className="grid gap-3" data-testid="memory-results-list">
          {isPending ? <QueryStateCard label="Loading operator memory..." /> : null}
          {isError ? <MemoryLoadState error={listError} /> : null}
          {!isPending && !isError && items.length === 0 ? (
            <div data-testid="memory-empty-state">
              <InventoryStatePanel
                description={
                  hasActiveFilters
                    ? "The current admin filters narrowed the operator corpus to zero. Reset filters to review all canonical memory."
                    : "No canonical memory exists yet. Create operator memory when there is a durable fact or decision worth carrying into matching workflow lookup."
                }
                testId="memory-empty-state-panel"
                title={
                  hasActiveFilters
                    ? "No memory entries match these filters"
                    : "No canonical memory exists yet"
                }
              />
            </div>
          ) : null}
          {!isPending && !isError && items.map((item) => (
            <MemoryListCard
              item={item}
              key={item.memoryId}
              onSelect={onSelect}
              selected={item.memoryId === selectedMemoryId}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function buildInspectorTabs({
  detail,
  detailError,
  detailPending,
  events,
  eventsError,
  eventsPending,
  onUpdateStatus,
  revisions,
  revisionsError,
  revisionsPending,
  statusPending,
}: {
  detail: MemoryAdminEntryRead | undefined;
  detailError: unknown;
  detailPending: boolean;
  events: readonly MemoryAdminEventListRead["items"][number][] | undefined;
  eventsError: unknown;
  eventsPending: boolean;
  onUpdateStatus: (payload: { memoryId: string; payload: MemoryAdminStatusUpdateRequest }) => Promise<void>;
  revisions: readonly MemoryAdminRevisionListRead["items"][number][] | undefined;
  revisionsError: unknown;
  revisionsPending: boolean;
  statusPending: boolean;
}): SplitInspectorLayoutTab<MemoryInspectorTab>[] {
  return [
    {
      content: detailPending ? <QueryStateCard label="Loading admin detail..." /> : detail ? <DetailInspection detail={detail} onUpdateStatus={onUpdateStatus} statusPending={statusPending} /> : <MemoryLoadState error={detailError} />,
      label: "Detail",
      value: "detail",
    },
    {
      content: revisionsPending ? <QueryStateCard label="Loading revision history..." /> : revisionsError ? <MemoryLoadState error={revisionsError} /> : <RevisionsInspection revisions={revisions ?? []} />,
      label: "Revisions",
      value: "revisions",
    },
    {
      content: eventsPending ? <QueryStateCard label="Loading audit events..." /> : eventsError ? <MemoryLoadState error={eventsError} /> : <EventsInspection events={events ?? []} />,
      label: "Audit events",
      value: "events",
    },
  ];
}

export function MemoryListPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const isMobileInspector = useIsMobile();
  const selectedMemoryId = searchParams.get("memoryId");
  const [packageKey, setPackageKey] = useState(searchParams.get("packageKey") ?? "");
  const [workflowKey, setWorkflowKey] = useState(searchParams.get("workflowKey") ?? "");
  const [agentKey, setAgentKey] = useState(searchParams.get("agentKey") ?? "");
  const [runId, setRunId] = useState(searchParams.get("runId") ?? "");
  const [scopeType, setScopeType] = useState(searchParams.get("scopeType") ?? ALL_SCOPES_FILTER);
  const [query, setQuery] = useState(searchParams.get("query") ?? "");
  const [kind, setKind] = useState(searchParams.get("kind") ?? "");
  const [status, setStatus] = useState(searchParams.get("status") ?? ALL_STATUSES_FILTER);
  const inspector = useSplitInspectorState<string, MemoryInspectorTab>({
    initialOpen: Boolean(selectedMemoryId),
    initialSelection: selectedMemoryId,
    initialTab: "detail",
  });

  const listParams = useMemo(() => buildAdminListParams({
    agentKey,
    kind,
    packageKey,
    query,
    runId,
    scopeType,
    status,
    workflowKey,
  }), [agentKey, kind, packageKey, query, runId, scopeType, status, workflowKey]);
  const listQuery = useAdminMemoryEntries(listParams, { enabled: true });
  const canInspect = Boolean(selectedMemoryId);
  const detailQuery = useAdminMemoryEntry(selectedMemoryId ?? undefined, { enabled: canInspect });
  const revisionsQuery = useAdminMemoryRevisions(selectedMemoryId ?? undefined, {}, { enabled: canInspect });
  const eventsQuery = useAdminMemoryEvents(selectedMemoryId ?? undefined, {}, { enabled: canInspect });
  const createMutation = useCreateAdminMemoryEntry();
  const revisionMutation = useCreateAdminMemoryRevision();
  const statusMutation = useUpdateAdminMemoryStatus();

  const selectMemory = (memoryId: string) => {
    inspector.select(memoryId, { tab: "detail" });
    const next = new URLSearchParams(searchParams);
    next.set("memoryId", memoryId);
    setSearchParams(next);
  };

  const closeInspector = () => {
    inspector.clearSelection();
    const next = new URLSearchParams(searchParams);
    next.delete("memoryId");
    setSearchParams(next);
  };

  const resetFilters = () => {
    setPackageKey("");
    setWorkflowKey("");
    setAgentKey("");
    setRunId("");
    setScopeType(ALL_SCOPES_FILTER);
    setQuery("");
    setKind("");
    setStatus(ALL_STATUSES_FILTER);
    const next = new URLSearchParams(searchParams);
    ["packageKey", "workflowKey", "agentKey", "runId", "scopeType", "query", "kind", "status"].forEach((key) => next.delete(key));
    setSearchParams(next);
  };

  const createMemory = async (payload: MemoryAdminCreateRequest) => {
    const created = await createMutation.mutateAsync(payload);
    toast.success("Memory created");
    selectMemory(created.memoryId);
  };

  const reviseMemory = async (variables: AdminRevisionVariables) => {
    await revisionMutation.mutateAsync(variables);
    toast.success("Memory revision created");
  };

  const updateStatus = async (variables: Parameters<typeof statusMutation.mutateAsync>[0]) => {
    await statusMutation.mutateAsync(variables);
  };

  const items = listQuery.data?.items ?? [];
  const total = listQuery.data?.total ?? items.length;
  const hasActiveFilters = Object.keys(listParams).length > 0;
  const inspectorTabs = buildInspectorTabs({
    detail: detailQuery.data,
    detailError: detailQuery.error,
    detailPending: detailQuery.isPending,
    events: eventsQuery.data?.items,
    eventsError: eventsQuery.error,
    eventsPending: eventsQuery.isPending,
    onUpdateStatus: updateStatus,
    revisions: revisionsQuery.data?.items,
    revisionsError: revisionsQuery.error,
    revisionsPending: revisionsQuery.isPending,
    statusPending: statusMutation.isPending,
  });
  const inspectorOpen = Boolean(selectedMemoryId) && inspector.isInspectorOpen;
  const memoryListPane = (
    <MemoryListPane
      hasActiveFilters={hasActiveFilters}
      isError={listQuery.isError}
      isPending={listQuery.isPending}
      items={items}
      listError={listQuery.error}
      onSelect={selectMemory}
      selectedMemoryId={selectedMemoryId}
      total={total}
    />
  );
  const memoryEmptyInspector = (
    <EmptyStatePanel
      description="Open a memory entry to inspect admin detail, scope, provenance, latest revision, revision history, and audit events without leaving /memory."
      icon={<FileText className="size-4" />}
      title="Select memory to inspect"
    />
  );
  const memoryInspectorActions = (
    <>
      <RevisionDialog detail={detailQuery.data} onRevise={reviseMemory} pending={revisionMutation.isPending} />
      {selectedMemoryId ? (
        <Button onClick={closeInspector} size="sm" type="button" variant="outline">
          <X data-icon="inline-start" />
          Close
        </Button>
      ) : null}
    </>
  );

  return (
    <WorkspacePageShell
      bodyAriaLabel="Memory admin workspace"
      bodyClassName="gap-3"
      contextBar={<MemoryContextContract onReset={resetFilters} />}
      testId="memory-list-page"
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-stretch">
        <div className="min-w-0 flex-1">
          <MemoryAdminFilterControls
            agentKey={agentKey}
            kind={kind}
            packageKey={packageKey}
            query={query}
            runId={runId}
            scopeType={scopeType}
            setAgentKey={setAgentKey}
            setKind={setKind}
            setPackageKey={setPackageKey}
            setQuery={setQuery}
            setRunId={setRunId}
            setScopeType={setScopeType}
            setStatus={setStatus}
            setWorkflowKey={setWorkflowKey}
            status={status}
            total={total}
            workflowKey={workflowKey}
          />
        </div>
        <Card className="lg:w-80" data-testid="memory-write-card">
          <CardHeader className="px-4 pt-4">
            <CardTitle className="flex items-center gap-2 text-base">
              <History className="size-4" />
              Write controls
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 px-4 pb-4 text-xs text-muted-foreground">
            <RuntimeImpactNotice />
            <MemoryCreateDialog onCreate={createMemory} pending={createMutation.isPending} />
          </CardContent>
        </Card>
      </div>
      {isMobileInspector ? (
        <SheetInspectorLayout<MemoryInspectorTab>
          activeTab={inspector.activeTab}
          className="min-h-[34rem] flex-1"
          emptyInspector={memoryEmptyInspector}
          inspectorActions={memoryInspectorActions}
          inspectorAriaLabel="Memory admin sheet"
          inspectorOpen={inspectorOpen}
          inspectorTitle={selectedMemoryId ? `Memory ${selectedMemoryId}` : "Memory inspector"}
          leftPane={memoryListPane}
          leftPaneAriaLabel="Operator memory inventory"
          onActiveTabChange={inspector.setActiveTab}
          onInspectorOpenChange={(open) => {
            if (!open) closeInspector();
          }}
          sheetDescription="Inspect admin detail, revisions, and audit events without stacking a second panel in the mobile workspace."
          tabs={selectedMemoryId ? inspectorTabs : undefined}
          testId="memory-sheet-inspector"
        />
      ) : (
        <SplitInspectorLayout<MemoryInspectorTab>
          activeTab={inspector.activeTab}
          className="min-h-[34rem] flex-1"
          emptyInspector={memoryEmptyInspector}
          inspectorActions={memoryInspectorActions}
          inspectorAriaLabel="Memory admin panel"
          inspectorOpen={inspectorOpen}
          inspectorTitle={selectedMemoryId ? `Memory ${selectedMemoryId}` : "Memory inspector"}
          leftPane={memoryListPane}
          leftPaneAriaLabel="Operator memory inventory"
          leftPanel={{ defaultSize: 38, minSize: 20 }}
          onActiveTabChange={inspector.setActiveTab}
          rightPanel={{ defaultSize: 62, minSize: 35 }}
          tabs={selectedMemoryId ? inspectorTabs : undefined}
          testId="memory-split-inspector"
        />
      )}
    </WorkspacePageShell>
  );
}
