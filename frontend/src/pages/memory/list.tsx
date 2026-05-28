import {
  Database,
  FileText,
  Search,
  ShieldCheck,
  TriangleAlert,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router";

import { EmptyStatePanel } from "@/components/shared/empty-state-panel";
import { ResourceRowCard } from "@/components/shared/resource-row-card";
import { ResourceStatusStrip, type ResourceStatusStripItem } from "@/components/shared/resource-status-strip";
import {
  SheetInspectorLayout,
  SplitInspectorLayout,
  type SplitInspectorLayoutTab,
} from "@/components/shared/split-inspector-layout";
import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useIsMobile } from "@/components/ui/use-mobile";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useSplitInspectorState } from "@/hooks/use-split-inspector-state";
import { useMemoryDetail, useMemoryEvents, useMemoryList, useMemoryRevisions } from "@/hooks/use-memory";
import { ApiRequestError } from "@/lib/api-client";
import { formatDateTime } from "@/lib/format";
import type {
  MemoryApiAccessContext,
  MemoryApiAccessRequest,
  MemoryApiEntryRead,
  MemoryApiEventRead,
  MemoryApiListItemRead,
  MemoryApiListRequest,
  MemoryRevisionRead,
  MemoryScope,
} from "@/lib/types/memory";

const DEFAULT_LIMIT = 20;
const DEFAULT_MAX_CHARACTERS = 6_000;
const MEMORY_ACCESS_DENIED_CODE = "memory_namespace_access_denied";

type PrivateMemoryScopeType = "run" | "package" | "workflow" | "agent";
type MemoryInspectorTab = "detail" | "revisions" | "events";

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

function privateScopeFromContext(
  scopeType: PrivateMemoryScopeType,
  context: MemoryApiAccessContext,
): MemoryScope | null {
  if (scopeType === "run") {
    return context.runId ? { scopeKey: String(context.runId), scopeType } : null;
  }
  if (scopeType === "package") {
    return { scopeKey: context.packageKey, scopeType };
  }
  if (scopeType === "workflow") {
    return context.workflowKey ? { scopeKey: context.workflowKey, scopeType } : null;
  }
  if (scopeType === "agent") {
    return context.agentKey ? { scopeKey: context.agentKey, scopeType } : null;
  }
  return null;
}

function isAccessDenied(error: unknown): boolean {
  return (
    error instanceof ApiRequestError &&
    (error.status === 403 || error.code === MEMORY_ACCESS_DENIED_CODE)
  );
}

function formatScope(scope: MemoryScope): string {
  return scope.scopeType === "namespace"
    ? `Shared namespace ${scope.scopeKey}`
    : `${scope.scopeType} scope ${scope.scopeKey}`;
}

function subjectRefSummary(item: Pick<MemoryApiListItemRead, "subjectRefs">): string {
  if (item.subjectRefs.length === 0) {
    return "No subject refs";
  }
  return item.subjectRefs.map((subject) => `${subject.kind}:${subject.id}`).join(" · ");
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

function DetailField({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border bg-muted/20 p-3">
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd className="mt-1 break-words text-sm">{value}</dd>
    </div>
  );
}

function MemoryContextContract() {
  return (
    <Card className="gap-0" data-testid="memory-contract-notice">
      <div className="flex min-w-0 flex-col gap-2 px-3 py-2.5 sm:px-4">
        <div className="flex min-w-0 flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h2 className="inline-flex min-w-0 items-center gap-2 text-base font-semibold tracking-tight">
              <Database className="size-4 shrink-0" />
              <span className="min-w-0 truncate">Canonical Memory</span>
            </h2>
            <Badge className="w-fit shrink-0" variant="secondary">
              <ShieldCheck className="size-3.5" /> Explicit private scopes
            </Badge>
          </div>
          <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-[0.7rem] text-muted-foreground">
            <Badge className="border-border/70 bg-muted/30 text-muted-foreground" variant="outline">
              Package key required
            </Badge>
            <span aria-hidden="true" className="text-muted-foreground/60">•</span>
            <Badge className="border-border/70 bg-muted/30 text-muted-foreground" variant="outline">
              Private scope required
            </Badge>
            <span aria-hidden="true" className="text-muted-foreground/60">•</span>
            <Badge className="border-border/70 bg-muted/30 text-muted-foreground" variant="outline">
              Namespace grants server-owned only
            </Badge>
          </div>
        </div>
        <p className="min-w-0 text-xs leading-5 text-muted-foreground">
          /api/memory lists explicit private scopes only: a package access context and concrete private scope are required, visibility is fixed to explicit-scope, namespace grants are server-owned so browser-authored JSON is not accepted, and finance report history remains in Reports.
        </p>
      </div>
    </Card>
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
  const id = `memory-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;

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

function MemoryAccessState({ error }: { error: unknown }) {
  if (isAccessDenied(error)) {
    return (
      <Alert data-testid="memory-access-denied" variant="destructive">
        <TriangleAlert />
        <AlertTitle>Memory access denied</AlertTitle>
        <AlertDescription>
          The backend denied this package context for the requested memory scope.
          Browser-authored namespace declarations or grants cannot authorize access.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <Alert data-testid="memory-load-error" variant="destructive">
      <TriangleAlert />
      <AlertTitle>Unable to load canonical memory</AlertTitle>
      <AlertDescription>
        {error instanceof Error ? error.message : "The memory API request failed."}
      </AlertDescription>
    </Alert>
  );
}

function GatedState({
  description,
  testId,
  title,
  tone = "neutral",
}: {
  description: string;
  testId: string;
  title: string;
  tone?: "neutral" | "warning" | "danger";
}) {
  const icon = tone === "warning" ? <TriangleAlert className="size-4" /> : <ShieldCheck className="size-4" />;

  return (
    <div data-testid={testId}>
      <EmptyStatePanel description={description} icon={icon} title={title} tone={tone} />
    </div>
  );
}

function MemoryListCard({
  item,
  onSelect,
  selected,
}: {
  item: MemoryApiListItemRead;
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
          <Badge variant="secondary">{formatScope(item.scope)}</Badge>
        </>
      }
      description={<span className="line-clamp-2">{item.content}</span>}
      density="compactPlus"
      metadata={`${subjectRefSummary(item)} · ${formatDateTime(item.createdAt)}`}
      selected={selected}
      testId={`memory-row-${item.memoryId}`}
      title={item.summary}
    />
  );
}

function MemoryAccessFilterControls({
  accessContext,
  agentKey,
  explicitScope,
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
}: {
  accessContext: MemoryApiAccessContext | null;
  agentKey: string;
  explicitScope: MemoryScope | null;
  kind: string;
  packageKey: string;
  query: string;
  runId: string;
  scopeType: PrivateMemoryScopeType;
  setAgentKey: (value: string) => void;
  setKind: (value: string) => void;
  setPackageKey: (value: string) => void;
  setQuery: (value: string) => void;
  setRunId: (value: string) => void;
  setScopeType: (value: PrivateMemoryScopeType) => void;
  setStatus: (value: string) => void;
  setWorkflowKey: (value: string) => void;
  status: string;
  workflowKey: string;
}) {
  return (
    <Card data-testid="memory-access-filter-controls">
      <CardHeader className="px-4 pt-4">
        <div className="flex min-w-0 flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <CardTitle className="text-base">Access context and filters</CardTitle>
            <p className="mt-1 text-xs leading-5 text-muted-foreground">
              Package context, private scope, and scoped filters stay pinned above
              the split inspector; reads remain disabled until both gates pass.
            </p>
          </div>
          <ResourceStatusStrip items={contextStatusItems(accessContext, explicitScope)} />
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 px-4 pb-4">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4" data-testid="memory-access-context-card">
          <TextField label="Package key" onChange={setPackageKey} placeholder="pkg_alpha" value={packageKey} />
          <TextField label="Workflow key" onChange={setWorkflowKey} placeholder="optional workflow" value={workflowKey} />
          <TextField label="Agent key" onChange={setAgentKey} placeholder="optional agent" value={agentKey} />
          <TextField label="Run id" onChange={setRunId} placeholder="optional run id" value={runId} />
        </div>
        <div className="grid gap-3 lg:grid-cols-[minmax(14rem,18rem)_minmax(0,1fr)]" data-testid="memory-filter-card">
          <div className="flex min-w-0 flex-col gap-2">
            <Label className="text-sm" htmlFor="memory-private-scope">Private scope</Label>
            <Select onValueChange={(value) => setScopeType(value as PrivateMemoryScopeType)} value={scopeType}>
              <SelectTrigger id="memory-private-scope" size="sm">
                <SelectValue placeholder="Select private scope" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem value="run">Run</SelectItem>
                  <SelectItem value="package">Package</SelectItem>
                  <SelectItem value="workflow">Workflow</SelectItem>
                  <SelectItem value="agent">Agent</SelectItem>
                </SelectGroup>
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              Namespace grants are server-owned only.
            </p>
          </div>
          <div className="grid min-w-0 gap-3 md:grid-cols-[minmax(0,1fr)_12rem_12rem]">
            <div className="relative" role="search">
              <Search className="pointer-events-none absolute left-2.5 top-2 size-4 text-muted-foreground" />
              <Input
                aria-label="Search canonical memory"
                className="h-8 pl-8 text-xs"
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Scoped lexical search..."
                value={query}
              />
            </div>
            <Input aria-label="Filter memory kind" className="h-8 text-xs" onChange={(event) => setKind(event.target.value)} placeholder="kind" value={kind} />
            <Input aria-label="Filter memory status" className="h-8 text-xs" onChange={(event) => setStatus(event.target.value)} placeholder="resolved" value={status} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function DetailInspection({ detail }: { detail: MemoryApiEntryRead }) {
  return (
    <div className="flex min-w-0 flex-col gap-5" data-testid="memory-detail-panel">
      <ResourceStatusStrip
        items={[
          { label: "Status", value: detail.status, tone: detail.status === "resolved" ? "success" : "neutral" },
          { label: "Kind", value: detail.kind },
          { label: "Scope", value: formatScope(detail.scope), tone: "muted" },
        ]}
      />
      <div className="rounded-md border bg-muted/20 p-3 text-sm">
        <p className="whitespace-pre-wrap break-words">{detail.content}</p>
      </div>
      <dl className="grid gap-3 text-sm md:grid-cols-2">
        <DetailField label="Memory id" value={detail.memoryId} />
        <DetailField label="Revision id" value={detail.revisionId} />
        <DetailField label="Created" value={formatDateTime(detail.createdAt)} />
        <DetailField
          label="Provenance"
          value={`${detail.provenance.agentKey}@${detail.provenance.agentVersion} · run #${detail.provenance.runId}`}
        />
      </dl>
      <JsonBlock label="Attributes" value={detail.attributes} />
    </div>
  );
}

function RevisionCard({ revision }: { revision: MemoryRevisionRead }) {
  return (
    <article className="flex min-w-0 flex-col gap-2 rounded-md border bg-background/70 p-3 text-sm">
      <div className="flex flex-wrap gap-2">
        <Badge variant="outline">v{revision.version}</Badge>
        <Badge variant="secondary">{revision.revisionAction}</Badge>
        <Badge variant="outline">{revision.status}</Badge>
      </div>
      <p className="break-words font-medium">{revision.summary}</p>
      <p className="break-words text-muted-foreground">{revision.content}</p>
      <p className="break-words text-xs text-muted-foreground">
        {formatDateTime(revision.createdAt)} · {revision.sourceAgentKey} · run #{revision.sourceRunId}
      </p>
    </article>
  );
}

function RevisionsInspection({ revisions }: { revisions: readonly MemoryRevisionRead[] }) {
  if (revisions.length === 0) {
    return <EmptyStatePanel description="This memory has no visible revision history for the current access context." title="No revisions returned" />;
  }

  return (
    <section className="flex min-w-0 flex-col gap-3" data-testid="memory-revisions-panel">
      {revisions.map((revision) => <RevisionCard key={revision.revisionId} revision={revision} />)}
    </section>
  );
}

function EventCard({ event }: { event: MemoryApiEventRead }) {
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

function EventsInspection({ events }: { events: readonly MemoryApiEventRead[] }) {
  if (events.length === 0) {
    return <EmptyStatePanel description="No memory events are visible for this memory and package context." title="No events returned" />;
  }

  return (
    <section className="flex min-w-0 flex-col gap-3" data-testid="memory-events-panel">
      {events.map((event) => <EventCard event={event} key={event.eventId} />)}
    </section>
  );
}

function QueryStateCard({ label }: { label: string }) {
  return (
    <Card>
      <CardContent className="py-8 text-sm text-muted-foreground">{label}</CardContent>
    </Card>
  );
}

function MemoryListPane({
  accessContext,
  canQuery,
  explicitScope,
  isError,
  isPending,
  items,
  listError,
  onSelect,
  selectedMemoryId,
}: {
  accessContext: MemoryApiAccessContext | null;
  canQuery: boolean;
  explicitScope: MemoryScope | null;
  isError: boolean;
  isPending: boolean;
  items: readonly MemoryApiListItemRead[];
  listError: unknown;
  onSelect: (memoryId: string) => void;
  selectedMemoryId: string | null;
}) {
  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b bg-card/80 px-4 py-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold tracking-tight">Scoped inventory</h2>
          <p className="break-words text-xs text-muted-foreground">
            {explicitScope ? formatScope(explicitScope) : "Package key plus a concrete private scope unlocks reads."}
          </p>
        </div>
        <Badge variant="outline">{items.length} shown</Badge>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3">
        <div className="grid gap-3" data-testid="memory-results-list">
          {!accessContext ? (
            <GatedState
              description="Enter a package key before the frontend calls /api/memory. The route is intentionally not exposed as a global memory browser."
              testId="memory-access-required"
              title="Access context required"
            />
          ) : null}
          {accessContext && !explicitScope ? (
            <GatedState
              description="Provide the context field required by the selected private scope before any scoped memory query runs."
              testId="memory-explicit-scope-required"
              title="Private scope required"
              tone="warning"
            />
          ) : null}
          {canQuery && isPending ? <QueryStateCard label="Loading scoped memory..." /> : null}
          {canQuery && isError ? <MemoryAccessState error={listError} /> : null}
          {canQuery && !isPending && !isError && items.length === 0 ? (
            <div data-testid="memory-empty-state">
              <EmptyStatePanel
                description="No canonical memory entries are visible for this access context and private scope."
                title="No scoped memory entries"
              />
            </div>
          ) : null}
          {canQuery && items.map((item) => (
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
  revisions,
  revisionsError,
  revisionsPending,
}: {
  detail: MemoryApiEntryRead | undefined;
  detailError: unknown;
  detailPending: boolean;
  events: readonly MemoryApiEventRead[] | undefined;
  eventsError: unknown;
  eventsPending: boolean;
  revisions: readonly MemoryRevisionRead[] | undefined;
  revisionsError: unknown;
  revisionsPending: boolean;
}): SplitInspectorLayoutTab<MemoryInspectorTab>[] {
  return [
    {
      content: detailPending ? <QueryStateCard label="Loading memory detail..." /> : detail ? <DetailInspection detail={detail} /> : <MemoryAccessState error={detailError} />,
      label: "Detail",
      value: "detail",
    },
    {
      content: revisionsPending ? <QueryStateCard label="Loading revisions..." /> : revisionsError ? <MemoryAccessState error={revisionsError} /> : <RevisionsInspection revisions={revisions ?? []} />,
      label: "Revisions",
      value: "revisions",
    },
    {
      content: eventsPending ? <QueryStateCard label="Loading events..." /> : eventsError ? <MemoryAccessState error={eventsError} /> : <EventsInspection events={events ?? []} />,
      label: "Events",
      value: "events",
    },
  ];
}

function contextStatusItems(
  accessContext: MemoryApiAccessContext | null,
  explicitScope: MemoryScope | null,
): ResourceStatusStripItem[] {
  return [
    {
      label: "Package",
      tone: accessContext ? "success" : "warning",
      value: accessContext?.packageKey ?? "required",
    },
    {
      label: "Private scope",
      tone: explicitScope ? "success" : "warning",
      value: explicitScope ? formatScope(explicitScope) : "required",
    },
    { label: "Visibility", tone: "muted", value: "explicit-scope" },
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
  const [scopeType, setScopeType] = useState<PrivateMemoryScopeType>("run");
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("");
  const inspector = useSplitInspectorState<string, MemoryInspectorTab>({
    initialOpen: Boolean(selectedMemoryId),
    initialSelection: selectedMemoryId,
    initialTab: "detail",
  });

  const accessContext = useMemo<MemoryApiAccessContext | null>(() => {
    const normalizedPackageKey = optionalText(packageKey);
    if (!normalizedPackageKey) {
      return null;
    }
    return {
      agentKey: optionalText(agentKey),
      packageKey: normalizedPackageKey,
      runId: optionalRunId(runId),
      workflowKey: optionalText(workflowKey),
    };
  }, [agentKey, packageKey, runId, workflowKey]);
  const explicitScope = useMemo(
    () => (accessContext ? privateScopeFromContext(scopeType, accessContext) : null),
    [accessContext, scopeType],
  );
  const accessRequest = useMemo<MemoryApiAccessRequest>(
    () => ({ accessContext: accessContext ?? { packageKey: "missing" } }),
    [accessContext],
  );
  const listPayload = useMemo<MemoryApiListRequest>(() => ({
    ...accessRequest,
    kind: optionalText(kind),
    limit: DEFAULT_LIMIT,
    maxCharacters: DEFAULT_MAX_CHARACTERS,
    query: optionalText(query),
    scope: explicitScope ?? { scopeKey: "missing", scopeType: "package" },
    status: optionalText(status) as MemoryApiListRequest["status"],
    visibility: "explicit-scope",
  }), [accessRequest, explicitScope, kind, query, status]);
  const canQuery = Boolean(accessContext) && explicitScope !== null;
  const canInspect = canQuery && Boolean(selectedMemoryId);
  const listQuery = useMemoryList(listPayload, { enabled: canQuery });
  const detailQuery = useMemoryDetail(selectedMemoryId ?? undefined, accessRequest, { enabled: canInspect });
  const revisionsQuery = useMemoryRevisions(selectedMemoryId ?? undefined, accessRequest, { enabled: canInspect });
  const eventsQuery = useMemoryEvents(selectedMemoryId ?? undefined, accessRequest, { enabled: canInspect });

  const selectMemory = (memoryId: string) => {
    inspector.select(memoryId, { tab: "detail" });
    const next = new URLSearchParams(searchParams);
    next.set("memoryId", memoryId);
    if (accessContext) {
      next.set("packageKey", accessContext.packageKey);
      if (accessContext.workflowKey) next.set("workflowKey", accessContext.workflowKey);
      if (accessContext.agentKey) next.set("agentKey", accessContext.agentKey);
      if (accessContext.runId) next.set("runId", String(accessContext.runId));
    }
    setSearchParams(next);
  };

  const closeInspector = () => {
    inspector.clearSelection();
    const next = new URLSearchParams(searchParams);
    next.delete("memoryId");
    setSearchParams(next);
  };

  const items = listQuery.data?.items ?? [];
  const inspectorTabs = buildInspectorTabs({
    detail: detailQuery.data,
    detailError: detailQuery.error,
    detailPending: detailQuery.isPending,
    events: eventsQuery.data?.items,
    eventsError: eventsQuery.error,
    eventsPending: eventsQuery.isPending,
    revisions: revisionsQuery.data?.items,
    revisionsError: revisionsQuery.error,
    revisionsPending: revisionsQuery.isPending,
  });
  const inspectorOpen = Boolean(selectedMemoryId) && inspector.isInspectorOpen;
  const memoryListPane = (
    <MemoryListPane
      accessContext={accessContext}
      canQuery={canQuery}
      explicitScope={explicitScope}
      isError={listQuery.isError}
      isPending={listQuery.isPending}
      items={items}
      listError={listQuery.error}
      onSelect={selectMemory}
      selectedMemoryId={selectedMemoryId}
    />
  );
  const memoryEmptyInspector = (
    <EmptyStatePanel
      description="Open a memory entry from the scoped inventory to inspect detail, revisions, and events without leaving /memory."
      icon={<FileText className="size-4" />}
      title="Select memory to inspect"
    />
  );
  const memoryInspectorActions = selectedMemoryId ? (
    <Button onClick={closeInspector} size="sm" type="button" variant="outline">
      <X data-icon="inline-start" />
      Close
    </Button>
  ) : null;

  return (
    <WorkspacePageShell
      bodyAriaLabel="Memory inspection workspace"
      bodyClassName="gap-3"
      contextBar={<MemoryContextContract />}
      testId="memory-list-page"
    >
      <MemoryAccessFilterControls
        accessContext={accessContext}
        agentKey={agentKey}
        explicitScope={explicitScope}
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
        workflowKey={workflowKey}
      />
      {isMobileInspector ? (
        <SheetInspectorLayout<MemoryInspectorTab>
          activeTab={inspector.activeTab}
          className="min-h-[34rem] flex-1"
          emptyInspector={memoryEmptyInspector}
          inspectorActions={memoryInspectorActions}
          inspectorAriaLabel="Memory inspection sheet"
          inspectorOpen={inspectorOpen}
          inspectorTitle={selectedMemoryId ? `Memory ${selectedMemoryId}` : "Memory inspector"}
          leftPane={memoryListPane}
          leftPaneAriaLabel="Scoped memory inventory"
          onActiveTabChange={inspector.setActiveTab}
          onInspectorOpenChange={(open) => {
            if (!open) closeInspector();
          }}
          sheetDescription="Inspect memory detail, revisions, and events without stacking a second panel in the mobile workspace."
          tabs={selectedMemoryId ? inspectorTabs : undefined}
          testId="memory-sheet-inspector"
        />
      ) : (
        <SplitInspectorLayout<MemoryInspectorTab>
          activeTab={inspector.activeTab}
          className="min-h-[34rem] flex-1"
          emptyInspector={memoryEmptyInspector}
          inspectorActions={memoryInspectorActions}
          inspectorAriaLabel="Memory inspection panel"
          inspectorOpen={inspectorOpen}
          inspectorTitle={selectedMemoryId ? `Memory ${selectedMemoryId}` : "Memory inspector"}
          leftPane={memoryListPane}
          leftPaneAriaLabel="Scoped memory inventory"
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
