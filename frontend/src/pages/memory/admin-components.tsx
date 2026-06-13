import {
  FileText,
  Plus,
  RotateCcw,
  Search,
  ShieldCheck,
  SquarePen,
} from "lucide-react";
import { type ReactNode, useId, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";

import { EmptyStatePanel } from "@/components/shared/empty-state-panel";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { PageContextBar } from "@/components/shared/page-context-bar";
import { ResourceRowCard } from "@/components/shared/resource-row-card";
import {
  ResourceStatusBadge,
  ResourceStatusStrip,
} from "@/components/shared/resource-status-strip";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import { cn } from "@/components/ui/utils";
import { formatDateTime } from "@/lib/format";
import type {
  MemoryAdminCreateRequest,
  MemoryAdminEntryRead,
  MemoryAdminEventListRead,
  MemoryAdminListItemRead,
  MemoryAdminRevisionListRead,
} from "@/lib/types/memory";

import {
  ALL_SCOPES_FILTER,
  ALL_STATUSES_FILTER,
  type AdminRevisionVariables,
  type AdminStatusVariables,
  type CreateDraft,
  RUNTIME_IMPACT_COPY,
  SCOPE_TYPE_VALUES,
  STATUS_VALUES,
  buildOperatorProvenance,
  buildSubjectRefs,
  createInitialDraft,
  createMemoryPayloadFromDraft,
  createRevisionDraft,
  createStatusDraft,
  formatProvenance,
  formatScope,
  optionalText,
  parseJsonObject,
  parseRequiredRunId,
  revisionTone,
  statusTone,
  subjectRefSummary,
  titleCase,
} from "./admin-helpers";

type TextFieldProps = {
  label: string;
  onChange: (value: string) => void;
  placeholder?: string;
  value: string;
};

type TextareaFieldProps = TextFieldProps & {
  rows?: number;
};

type SelectFieldProps<TValue extends string> = {
  children: ReactNode;
  label: string;
  onChange: (value: TValue) => void;
  value: TValue;
};

type MemoryAdminFilterControlsProps = {
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
  workflowKey: string;
};

type MemoryListPaneProps = {
  hasActiveFilters: boolean;
  isError: boolean;
  isPending: boolean;
  items: readonly MemoryAdminListItemRead[];
  listError: unknown;
  total: number;
};

type RevisionItem = MemoryAdminRevisionListRead["items"][number];
type EventItem = MemoryAdminEventListRead["items"][number];

function mutationErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export function JsonBlock({ label, value }: { label: string; value: unknown }) {
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

function DetailField({
  label,
  mono = false,
  value,
}: {
  label: string;
  mono?: boolean;
  value: ReactNode;
}) {
  return (
    <div className="min-w-0 rounded-md border bg-muted/20 p-3">
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd
        className={cn(
          "mt-1 break-words text-sm",
          mono ? "font-mono text-xs" : null,
        )}
      >
        {value}
      </dd>
    </div>
  );
}

function fieldId(label: string, reactId: string) {
  return `memory-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${reactId}`;
}

export function TextField({
  label,
  onChange,
  placeholder,
  value,
}: TextFieldProps) {
  const reactId = useId();
  const id = fieldId(label, reactId);

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <Label className="text-sm" htmlFor={id}>
        {label}
      </Label>
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

export function TextareaField({
  label,
  onChange,
  placeholder,
  rows = 4,
  value,
}: TextareaFieldProps) {
  const reactId = useId();
  const id = fieldId(label, reactId);

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <Label className="text-sm" htmlFor={id}>
        {label}
      </Label>
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

export function SelectField<TValue extends string>({
  children,
  label,
  onChange,
  value,
}: SelectFieldProps<TValue>) {
  const reactId = useId();
  const id = fieldId(label, reactId);

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <Label className="text-sm" htmlFor={id}>
        {label}
      </Label>
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

export function RuntimeImpactNotice() {
  return (
    <div
      className="rounded-md border bg-muted/20 p-3 text-xs leading-5 text-muted-foreground"
      data-testid="memory-runtime-impact-copy"
    >
      {RUNTIME_IMPACT_COPY}
    </div>
  );
}

export function MemoryContextContract({
  createAction,
  onReset,
}: {
  createAction: ReactNode;
  onReset: () => void;
}) {
  return (
    <div data-testid="memory-admin-notice">
      <PageContextBar
        actions={
          <div className="flex flex-wrap items-center gap-2">
            {createAction}
            <Button onClick={onReset} size="sm" type="button" variant="outline">
              <RotateCcw data-icon="inline-start" />
              Reset filters
            </Button>
          </div>
        }
        description="Manage canonical memory across packages, scopes, and lifecycle states from the trusted local operator console."
        layout="toolbar"
        title="Memory"
      />
    </div>
  );
}

export function MemoryDetailContext({
  actions,
  detail,
  memoryId,
}: {
  actions?: ReactNode;
  detail?: MemoryAdminEntryRead;
  memoryId: string;
}) {
  return (
    <PageContextBar
      actions={actions}
      description="Inspect one canonical memory entry, its append-only revisions, audit events, and trusted operator lifecycle controls."
      layout="toolbar"
      meta={
        <ResourceStatusStrip
          className="border-0 bg-transparent p-0"
          density="toolbar"
          items={[
            {
              label: "Memory",
              value: <span className="font-mono">{memoryId}</span>,
              tone: "muted",
            },
            ...(detail
              ? [
                  {
                    label: "Status",
                    value: detail.status,
                    tone: statusTone(detail.status),
                  },
                  {
                    label: "Scope",
                    value: formatScope(detail.scope),
                    tone: "muted" as const,
                  },
                ]
              : []),
          ]}
        />
      }
      title={detail?.summary || "Memory Detail"}
      toolbarMetaPlacement="middle"
    />
  );
}

export function MemoryLoadState({ error }: { error: unknown }) {
  return (
    <InventoryStatePanel
      description={
        error instanceof Error
          ? error.message
          : "The admin memory request failed."
      }
      testId="memory-load-error"
      title="Unable to load operator memory"
      tone="danger"
    />
  );
}

export function QueryStateCard({ label }: { label: string }) {
  return (
    <Card>
      <CardContent className="py-8 text-sm text-muted-foreground">
        {label}
      </CardContent>
    </Card>
  );
}

function MemoryListCard({ item }: { item: MemoryAdminListItemRead }) {
  const memoryPath = `/memory/${item.memoryId}`;

  return (
    <ResourceRowCard
      actions={
        <Button
          asChild
          className="w-full sm:w-auto"
          size="sm"
          type="button"
          variant="outline"
        >
          <Link to={memoryPath}>
            <FileText data-icon="inline-start" />
            Open detail
          </Link>
        </Button>
      }
      badges={
        <>
          <Badge variant="outline">{item.kind}</Badge>
          <ResourceStatusBadge
            label={item.status}
            tone={statusTone(item.status)}
          />
          <Badge variant="secondary">{formatScope(item.scope)}</Badge>
        </>
      }
      bodyAction={{
        kind: "link",
        label: `Open memory ${item.memoryId}`,
        to: memoryPath,
      }}
      description={<span className="line-clamp-2">{item.excerpt}</span>}
      density="compactPlus"
      footer={
        item.lastEventType
          ? `Latest audit event: ${item.lastEventType}`
          : `Updated ${formatDateTime(item.updatedAt ?? item.createdAt)}`
      }
      metadata={`${subjectRefSummary(item)} · ${formatProvenance(item.provenance)}`}
      testId={`memory-row-${item.memoryId}`}
      title={item.summary}
    />
  );
}

export function MemoryAdminFilterControls({
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
  workflowKey,
}: MemoryAdminFilterControlsProps) {
  const searchId = fieldId("Search canonical memory", useId());

  return (
    <Card data-testid="memory-admin-filter-controls">
      <CardHeader className="px-4 pt-4">
        <div className="flex min-w-0 flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <CardTitle className="text-base">Operator filters</CardTitle>
            <CardDescription className="mt-1 text-xs leading-5">
              Narrow the admin-managed corpus by package, workflow, agent, run,
              scope type, kind, status, or lexical query. Clearing all filters
              restores the full trusted corpus.
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 px-4 pb-4">
        <div
          className="grid gap-3 md:grid-cols-2 xl:grid-cols-4"
          data-testid="memory-admin-filter-card"
        >
          <TextField
            label="Package key"
            onChange={setPackageKey}
            placeholder="pkg_alpha"
            value={packageKey}
          />
          <TextField
            label="Workflow key"
            onChange={setWorkflowKey}
            placeholder="risk-review"
            value={workflowKey}
          />
          <TextField
            label="Agent key"
            onChange={setAgentKey}
            placeholder="analyst"
            value={agentKey}
          />
          <TextField
            label="Run id"
            onChange={setRunId}
            placeholder="41"
            value={runId}
          />
        </div>
        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_12rem_12rem_12rem]">
          <div className="flex min-w-0 flex-col gap-2">
            <Label className="text-sm" htmlFor={searchId}>
              Search canonical memory
            </Label>
            <div className="relative" role="search">
              <Search className="pointer-events-none absolute left-2.5 top-2 size-4 text-muted-foreground" />
              <Input
                className="h-8 pl-8 text-xs"
                id={searchId}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search summaries, content, or subject refs..."
                value={query}
              />
            </div>
          </div>
          <TextField
            label="Kind"
            onChange={setKind}
            placeholder="insight"
            value={kind}
          />
          <SelectField
            label="Scope type"
            onChange={setScopeType}
            value={scopeType}
          >
            <SelectItem value={ALL_SCOPES_FILTER}>All scopes</SelectItem>
            {SCOPE_TYPE_VALUES.map((value) => (
              <SelectItem key={value} value={value}>
                {titleCase(value)}
              </SelectItem>
            ))}
          </SelectField>
          <SelectField label="Status" onChange={setStatus} value={status}>
            <SelectItem value={ALL_STATUSES_FILTER}>All statuses</SelectItem>
            {STATUS_VALUES.map((value) => (
              <SelectItem key={value} value={value}>
                {titleCase(value)}
              </SelectItem>
            ))}
          </SelectField>
        </div>
      </CardContent>
    </Card>
  );
}

export function MemoryCreateDialog({
  onCreate,
  pending,
}: {
  onCreate: (payload: MemoryAdminCreateRequest) => Promise<void>;
  pending: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<CreateDraft>(() => createInitialDraft());
  const update = <TKey extends keyof CreateDraft>(
    key: TKey,
    value: CreateDraft[TKey],
  ) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };
  const submit = async (event: { preventDefault: () => void }) => {
    event.preventDefault();
    const packageKey = optionalText(draft.packageKey);
    const runId = parseRequiredRunId(draft.runId);
    const attributes = parseJsonObject(
      draft.attributesJson,
      "Create attributes",
    );
    if (!packageKey || !runId || !attributes) {
      toast.error(
        "Create memory needs package key, run id, scope key, and valid attributes.",
      );
      return;
    }
    const payload = createMemoryPayloadFromDraft(draft);
    if (!payload) {
      return;
    }
    try {
      await onCreate({
        ...payload,
        provenance: buildOperatorProvenance({
          agentKey: draft.agentKey,
          runId,
          workflowKey: optionalText(draft.workflowKey),
        }),
        subjectRefs: buildSubjectRefs(draft),
      });
      setDraft(createInitialDraft());
      setOpen(false);
    } catch (error) {
      toast.error(
        mutationErrorMessage(error, "Memory could not be created."),
      );
    }
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
          <DialogTitle>Create memory</DialogTitle>
          <DialogDescription>
            Write canonical memory with explicit scope, lifecycle status, and
            local operator provenance.
          </DialogDescription>
        </DialogHeader>
        <form className="grid gap-4" onSubmit={submit}>
          <div className="grid gap-3 md:grid-cols-2">
            <TextField
              label="Summary"
              onChange={(value) => update("summary", value)}
              value={draft.summary}
            />
            <TextField
              label="Kind"
              onChange={(value) => update("kind", value)}
              value={draft.kind}
            />
            <TextField
              label="Package key"
              onChange={(value) => update("packageKey", value)}
              value={draft.packageKey}
            />
            <TextField
              label="Workflow key"
              onChange={(value) => update("workflowKey", value)}
              value={draft.workflowKey}
            />
            <TextField
              label="Agent key"
              onChange={(value) => update("agentKey", value)}
              value={draft.agentKey}
            />
            <TextField
              label="Run id"
              onChange={(value) => update("runId", value)}
              value={draft.runId}
            />
            <SelectField
              label="Scope type"
              onChange={(value) => update("scopeType", value)}
              value={draft.scopeType}
            >
              {SCOPE_TYPE_VALUES.map((value) => (
                <SelectItem key={value} value={value}>
                  {titleCase(value)}
                </SelectItem>
              ))}
            </SelectField>
            <TextField
              label="Scope key"
              onChange={(value) => update("scopeKey", value)}
              value={draft.scopeKey}
            />
            <SelectField
              label="Initial status"
              onChange={(value) => update("status", value)}
              value={draft.status}
            >
              {STATUS_VALUES.map((value) => (
                <SelectItem key={value} value={value}>
                  {titleCase(value)}
                </SelectItem>
              ))}
            </SelectField>
            <TextField
              label="Subject kind"
              onChange={(value) => update("subjectKind", value)}
              value={draft.subjectKind}
            />
            <TextField
              label="Subject id"
              onChange={(value) => update("subjectId", value)}
              value={draft.subjectId}
            />
            <TextField
              label="Subject label"
              onChange={(value) => update("subjectLabel", value)}
              value={draft.subjectLabel}
            />
          </div>
          <TextareaField
            label="Content"
            onChange={(value) => update("content", value)}
            rows={5}
            value={draft.content}
          />
          <TextareaField
            label="Attributes JSON"
            onChange={(value) => update("attributesJson", value)}
            rows={3}
            value={draft.attributesJson}
          />
          <DialogFooter>
            <Button
              disabled={pending}
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
            <Button disabled={pending} type="submit">
              Create memory
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function RevisionDialog({
  detail,
  onRevise,
  pending,
}: {
  detail: MemoryAdminEntryRead | undefined;
  onRevise: (payload: AdminRevisionVariables) => Promise<void>;
  pending: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(createRevisionDraft);
  const selectedMemoryId = detail?.memoryId;
  const update = <TKey extends keyof ReturnType<typeof createRevisionDraft>>(
    key: TKey,
    value: ReturnType<typeof createRevisionDraft>[TKey],
  ) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };
  const submit = async (event: { preventDefault: () => void }) => {
    event.preventDefault();
    if (!detail || !selectedMemoryId) {
      return;
    }
    const attributes = parseJsonObject(
      draft.attributesJson,
      "Revision attributes",
    );
    if (!attributes) {
      return;
    }
    try {
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
      setDraft(createRevisionDraft());
      setOpen(false);
    } catch (error) {
      toast.error(
        mutationErrorMessage(error, "Memory revision could not be created."),
      );
    }
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
            Add a new operator-authored revision while preserving the selected
            memory identity and audit trail.
          </DialogDescription>
        </DialogHeader>
        <form className="grid gap-4" onSubmit={submit}>
          <RuntimeImpactNotice />
          <TextField
            label="Revision summary"
            onChange={(value) => update("summary", value)}
            value={draft.summary}
          />
          <TextareaField
            label="Revision content"
            onChange={(value) => update("content", value)}
            rows={6}
            value={draft.content}
          />
          <TextareaField
            label="Revision attributes JSON"
            onChange={(value) => update("attributesJson", value)}
            rows={3}
            value={draft.attributesJson}
          />
          <DialogFooter>
            <Button
              disabled={pending}
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
            <Button disabled={pending || !detail} type="submit">
              Create revision
            </Button>
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
  detail: MemoryAdminEntryRead;
  onUpdateStatus: (payload: AdminStatusVariables) => Promise<void>;
  pending: boolean;
}) {
  const [draft, setDraft] = useState(() => createStatusDraft(detail.status));
  const update = <TKey extends keyof ReturnType<typeof createStatusDraft>>(
    key: TKey,
    value: ReturnType<typeof createStatusDraft>[TKey],
  ) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };
  const submit = async (event: { preventDefault: () => void }) => {
    event.preventDefault();
    const attributes = parseJsonObject(
      draft.attributesJson,
      "Status attributes",
    );
    if (!attributes) {
      return;
    }
    try {
      await onUpdateStatus({
        memoryId: detail.memoryId,
        payload: {
          attributes,
          observedAt: new Date().toISOString(),
          status: draft.status,
          summary: optionalText(draft.summary),
        },
      });
      toast.success("Memory status updated");
    } catch (error) {
      toast.error(
        mutationErrorMessage(error, "Memory status could not be updated."),
      );
    }
  };

  return (
    <form
      className="grid gap-3 rounded-md border bg-muted/20 p-3"
      data-testid="memory-status-form"
      onSubmit={submit}
    >
      <div className="flex min-w-0 items-center gap-2 text-sm font-medium">
        <ShieldCheck />
        Lifecycle status
      </div>
      <RuntimeImpactNotice />
      <div className="grid gap-3 md:grid-cols-2">
        <SelectField
          label="New status"
          onChange={(value) => update("status", value)}
          value={draft.status}
        >
          {STATUS_VALUES.map((value) => (
            <SelectItem key={value} value={value}>
              {titleCase(value)}
            </SelectItem>
          ))}
        </SelectField>
        <TextField
          label="Status summary"
          onChange={(value) => update("summary", value)}
          value={draft.summary}
        />
      </div>
      <TextareaField
        label="Status attributes JSON"
        onChange={(value) => update("attributesJson", value)}
        rows={3}
        value={draft.attributesJson}
      />
      <div>
        <Button disabled={pending} size="sm" type="submit">
          Update status
        </Button>
      </div>
    </form>
  );
}

export function DetailInspection({
  detail,
  onUpdateStatus,
  statusPending,
}: {
  detail: MemoryAdminEntryRead;
  onUpdateStatus: (payload: AdminStatusVariables) => Promise<void>;
  statusPending: boolean;
}) {
  return (
    <div
      className="flex min-w-0 flex-col gap-5"
      data-testid="memory-detail-panel"
    >
      <ResourceStatusStrip
        items={[
          {
            label: "Status",
            value: detail.status,
            tone: statusTone(detail.status),
          },
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
        <DetailField
          label="Updated"
          value={formatDateTime(detail.updatedAt ?? detail.createdAt)}
        />
        <DetailField
          label="Provenance"
          value={formatProvenance(detail.provenance)}
        />
        <DetailField
          label="Latest revision"
          value={`v${detail.revision.version} · ${detail.revision.contentHash}`}
        />
      </dl>
      <JsonBlock label="Attributes" value={detail.attributes} />
      {detail.outcome ? (
        <JsonBlock label="Outcome" value={detail.outcome} />
      ) : null}
      {detail.reflections.length > 0 ? (
        <JsonBlock label="Reflections" value={detail.reflections} />
      ) : null}
      {detail.auditLinks ? (
        <JsonBlock label="Audit links" value={detail.auditLinks} />
      ) : null}
      <StatusUpdateForm
        key={`${detail.memoryId}-${detail.status}`}
        detail={detail}
        onUpdateStatus={onUpdateStatus}
        pending={statusPending}
      />
    </div>
  );
}

function RevisionCard({ revision }: { revision: RevisionItem }) {
  return (
    <article className="flex min-w-0 flex-col gap-2 rounded-md border bg-background/70 p-3 text-sm">
      <div className="flex flex-wrap gap-2">
        <Badge variant="outline">v{revision.version}</Badge>
        <ResourceStatusBadge
          label={revision.revisionAction}
          tone={revisionTone(revision.revisionAction)}
        />
        <ResourceStatusBadge
          label={revision.status}
          tone={statusTone(revision.status)}
        />
      </div>
      <p className="break-words font-medium">{revision.summary}</p>
      <p className="break-words text-muted-foreground">{revision.content}</p>
      <p className="break-words text-xs text-muted-foreground">
        {formatDateTime(revision.createdAt)} · {revision.sourceAgentKey} · run #
        {revision.sourceRunId}
      </p>
    </article>
  );
}

export function RevisionsInspection({
  revisions,
}: {
  revisions: readonly RevisionItem[];
}) {
  if (revisions.length === 0) {
    return (
      <EmptyStatePanel
        description="This memory has no operator-visible revision history yet."
        title="No revisions returned"
      />
    );
  }

  return (
    <section
      className="flex min-w-0 flex-col gap-3"
      data-testid="memory-revisions-panel"
    >
      {revisions.map((revision) => (
        <RevisionCard key={revision.revisionId} revision={revision} />
      ))}
    </section>
  );
}

function EventCard({ event }: { event: EventItem }) {
  return (
    <article className="flex min-w-0 flex-col gap-3 rounded-md border bg-background/70 p-3 text-sm">
      <div className="flex flex-wrap gap-2">
        <Badge variant="outline">event #{event.eventId}</Badge>
        <Badge variant="secondary">{event.eventType}</Badge>
        {event.retrievalMode ? (
          <Badge variant="outline">{event.retrievalMode}</Badge>
        ) : null}
      </div>
      <p className="text-xs text-muted-foreground">
        {formatDateTime(event.createdAt)} · run #{event.runId}
      </p>
      {event.excerpt ? (
        <p className="break-words text-muted-foreground">{event.excerpt}</p>
      ) : null}
      <JsonBlock label="Result snapshot" value={event.resultSnapshot} />
      <JsonBlock label="Status snapshot" value={event.statusSnapshot} />
    </article>
  );
}

export function EventsInspection({ events }: { events: readonly EventItem[] }) {
  if (events.length === 0) {
    return (
      <EmptyStatePanel
        description="No audit events are recorded for this memory yet."
        title="No events returned"
      />
    );
  }

  return (
    <section
      className="flex min-w-0 flex-col gap-3"
      data-testid="memory-events-panel"
    >
      {events.map((event) => (
        <EventCard event={event} key={event.eventId} />
      ))}
    </section>
  );
}

export function MemoryListPane({
  hasActiveFilters,
  isError,
  isPending,
  items,
  listError,
  total,
}: MemoryListPaneProps) {
  return (
    <Card className="min-w-0" data-testid="memory-results-card">
      <CardHeader className="px-4 pt-4">
        <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <CardTitle className="text-base">Trusted operator corpus</CardTitle>
          <Badge variant="outline">
            {items.length} shown · {total} total
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        <div className="grid gap-3" data-testid="memory-results-list">
          {isPending ? (
            <QueryStateCard label="Loading operator memory..." />
          ) : null}
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
          {!isPending &&
            !isError &&
            items.map((item) => (
              <MemoryListCard item={item} key={item.memoryId} />
            ))}
        </div>
      </CardContent>
    </Card>
  );
}

