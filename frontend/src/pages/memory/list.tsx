import {
  Activity,
  Database,
  FileText,
  History,
  Search,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useMemoryDetail, useMemoryEvents, useMemoryList, useMemoryRevisions } from "@/hooks/use-memory";
import { ApiRequestError } from "@/lib/api-client";
import { formatDateTime } from "@/lib/format";
import type {
  MemoryApiAccessContext,
  MemoryApiAccessRequest,
  MemoryApiListItemRead,
  MemoryApiListRequest,
  MemoryScope,
} from "@/lib/types/memory";

const DEFAULT_LIMIT = 20;
const DEFAULT_MAX_CHARACTERS = 6_000;
const MEMORY_ACCESS_DENIED_CODE = "memory_namespace_access_denied";

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

type PrivateMemoryScopeType = "run" | "package" | "workflow" | "agent";

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

function subjectRefSummary(item: MemoryApiListItemRead): string {
  if (item.subjectRefs.length === 0) {
    return "No subject refs";
  }
  return item.subjectRefs
    .map((subject) => `${subject.kind}:${subject.id}`)
    .join(" · ");
}

function MemoryHeader() {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold tracking-tight">Canonical Memory</h1>
        <p className="max-w-3xl text-sm text-muted-foreground">
          Platform memory from /api/memory. This workspace shows explicit private
          scopes only until namespace grants have a trusted server-owned source;
          finance report history remains in Reports.
        </p>
      </div>
      <Badge className="w-fit" variant="secondary">
        <ShieldCheck className="size-3.5" /> Explicit private scopes
      </Badge>
    </div>
  );
}

function ContractNotice() {
  return (
    <Alert data-testid="memory-contract-notice">
      <Database />
      <AlertTitle>Stable platform memory contract</AlertTitle>
      <AlertDescription>
        Lists require a package access context and a concrete private scope.
        Shared namespace grants are not accepted from browser-authored JSON;
        there is no global wildcard search, and this page does not create,
        edit, delete, or browse report history.
      </AlertDescription>
    </Alert>
  );
}

function TextField(props: {
  label: string;
  onChange: (value: string) => void;
  placeholder?: string;
  value: string;
}) {
  const { label, onChange, placeholder, value } = props;
  const id = `memory-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;

  return (
    <div className="space-y-2">
      <Label className="text-sm" htmlFor={id}>{label}</Label>
      <Input
        id={id}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        value={value}
      />
    </div>
  );
}

function MemoryListCard(props: {
  item: MemoryApiListItemRead;
  onSelect: (memoryId: string) => void;
  selected: boolean;
}) {
  const { item, onSelect, selected } = props;

  return (
    <article
      className="rounded-xl border bg-card p-4 text-card-foreground"
      data-testid={`memory-row-${item.memoryId}`}
      data-state={selected ? "selected" : undefined}
    >
      <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{item.kind}</Badge>
            <Badge variant="secondary">{formatScope(item.scope)}</Badge>
          </div>
          <h2 className="break-words text-sm font-medium text-foreground">
            {item.summary}
          </h2>
          <p className="line-clamp-2 text-sm text-muted-foreground">
            {item.content}
          </p>
          <p className="break-words text-xs text-muted-foreground">
            {subjectRefSummary(item)} · {formatDateTime(item.createdAt)}
          </p>
        </div>
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
      </div>
    </article>
  );
}

function MemoryAccessState(props: { error: unknown }) {
  const { error } = props;
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

function MemoryDetailPanel(props: {
  accessRequest: MemoryApiAccessRequest;
  enabled: boolean;
  memoryId: string | null;
}) {
  const { accessRequest, enabled, memoryId } = props;
  const detailQuery = useMemoryDetail(memoryId ?? undefined, accessRequest, { enabled });
  const revisionsQuery = useMemoryRevisions(memoryId ?? undefined, accessRequest, { enabled });
  const eventsQuery = useMemoryEvents(memoryId ?? undefined, accessRequest, { enabled });

  if (!memoryId) {
    return (
      <Card data-testid="memory-detail-empty">
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          Select a memory entry to inspect detail, revisions, and events.
        </CardContent>
      </Card>
    );
  }

  if (!enabled) {
    return null;
  }

  if (detailQuery.isPending) {
    return <Card><CardContent className="py-8 text-sm text-muted-foreground">Loading memory detail...</CardContent></Card>;
  }

  if (detailQuery.isError || !detailQuery.data) {
    return <MemoryAccessState error={detailQuery.error} />;
  }

  const detail = detailQuery.data;

  return (
    <Card data-testid="memory-detail-panel">
      <CardHeader>
        <CardTitle className="text-base">{detail.summary}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="flex flex-wrap gap-2">
          <Badge variant="secondary">{detail.status}</Badge>
          <Badge variant="outline">{detail.kind}</Badge>
          <Badge variant="outline">{formatScope(detail.scope)}</Badge>
        </div>
        <div className="rounded-md border bg-muted/20 p-3 text-sm">
          <p className="whitespace-pre-wrap break-words">{detail.content}</p>
        </div>
        <dl className="grid gap-3 text-sm md:grid-cols-2">
          <div className="rounded-md border bg-muted/20 p-3">
            <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Memory id</dt>
            <dd className="mt-1 break-all font-mono text-xs">{detail.memoryId}</dd>
          </div>
          <div className="rounded-md border bg-muted/20 p-3">
            <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Provenance</dt>
            <dd className="mt-1 break-words">
              {detail.provenance.agentKey}@{detail.provenance.agentVersion} · run #{detail.provenance.runId}
            </dd>
          </div>
        </dl>
        <section className="space-y-2" data-testid="memory-revisions-panel">
          <h3 className="flex items-center gap-2 text-base font-medium leading-none">
            <History className="size-4" /> Revisions
          </h3>
          <div className="grid gap-2">
            {(revisionsQuery.data?.items ?? []).map((revision) => (
              <div className="rounded-md border bg-background/70 p-3 text-sm" key={revision.revisionId}>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">v{revision.version}</Badge>
                  <Badge variant="secondary">{revision.revisionAction}</Badge>
                </div>
                <p className="mt-2 break-words text-muted-foreground">{revision.summary}</p>
              </div>
            ))}
          </div>
        </section>
        <section className="space-y-2" data-testid="memory-events-panel">
          <h3 className="flex items-center gap-2 text-base font-medium leading-none">
            <Activity className="size-4" /> Events
          </h3>
          <div className="grid gap-2">
            {(eventsQuery.data?.items ?? []).map((event) => (
              <div className="rounded-md border bg-background/70 p-3 text-sm" key={event.eventId}>
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">event #{event.eventId}</Badge>
                  <Badge variant="secondary">{event.eventType}</Badge>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">
                  {formatDateTime(event.createdAt)} · run #{event.runId}
                </p>
              </div>
            ))}
          </div>
        </section>
      </CardContent>
    </Card>
  );
}

export function MemoryListPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedMemoryId = searchParams.get("memoryId");
  const [packageKey, setPackageKey] = useState(searchParams.get("packageKey") ?? "");
  const [workflowKey, setWorkflowKey] = useState(searchParams.get("workflowKey") ?? "");
  const [agentKey, setAgentKey] = useState(searchParams.get("agentKey") ?? "");
  const [runId, setRunId] = useState(searchParams.get("runId") ?? "");
  const [scopeType, setScopeType] = useState<PrivateMemoryScopeType>("run");
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("");

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
  const listQuery = useMemoryList(listPayload, { enabled: canQuery });

  const selectMemory = (memoryId: string) => {
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

  return (
    <div className="space-y-4 p-4" data-testid="memory-list-page">
      <MemoryHeader />
      <ContractNotice />
      <Card data-testid="memory-access-context-card">
        <CardHeader><CardTitle className="text-base">Access context</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <TextField label="Package key" onChange={setPackageKey} placeholder="pkg_alpha" value={packageKey} />
            <TextField label="Workflow key" onChange={setWorkflowKey} placeholder="optional workflow" value={workflowKey} />
            <TextField label="Agent key" onChange={setAgentKey} placeholder="optional agent" value={agentKey} />
            <TextField label="Run id" onChange={setRunId} placeholder="optional run id" value={runId} />
          </div>
          <div className="space-y-2">
            <Label className="text-sm" htmlFor="memory-private-scope">Private scope</Label>
            <select
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
              id="memory-private-scope"
              onChange={(event) => setScopeType(event.target.value as PrivateMemoryScopeType)}
              value={scopeType}
            >
              <option value="run">Run</option>
              <option value="package">Package</option>
              <option value="workflow">Workflow</option>
              <option value="agent">Agent</option>
            </select>
            <p className="text-xs text-muted-foreground">
              Shared namespace declarations and grants are intentionally not accepted here;
              API access stays private-scope-only until grants come from trusted package metadata.
            </p>
          </div>
        </CardContent>
      </Card>
      <Card data-testid="memory-filter-card">
        <CardContent className="grid gap-3 p-4 md:grid-cols-[minmax(0,1fr)_12rem_12rem]">
          <div className="relative" role="search">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
            <Input aria-label="Search canonical memory" className="pl-8" onChange={(event) => setQuery(event.target.value)} placeholder="Scoped lexical search..." value={query} />
          </div>
          <Input aria-label="Filter memory kind" onChange={(event) => setKind(event.target.value)} placeholder="kind" value={kind} />
          <Input aria-label="Filter memory status" onChange={(event) => setStatus(event.target.value)} placeholder="resolved" value={status} />
        </CardContent>
      </Card>

      {!accessContext ? (
        <Alert data-testid="memory-access-required">
          <ShieldCheck />
          <AlertTitle>Access context required</AlertTitle>
          <AlertDescription>
            Enter a package key before the frontend calls /api/memory. The route
            is intentionally not exposed as a global memory browser.
          </AlertDescription>
        </Alert>
      ) : null}
      {accessContext && !explicitScope ? (
        <Alert data-testid="memory-explicit-scope-required">
          <TriangleAlert />
          <AlertTitle>Private scope required</AlertTitle>
          <AlertDescription>Provide the context field required by the selected private scope.</AlertDescription>
        </Alert>
      ) : null}
      {canQuery && listQuery.isPending ? (
        <Card><CardContent className="py-8 text-sm text-muted-foreground">Loading scoped memory...</CardContent></Card>
      ) : null}
      {canQuery && listQuery.isError ? <MemoryAccessState error={listQuery.error} /> : null}
      {canQuery && listQuery.data?.items.length === 0 ? (
        <Card data-testid="memory-empty-state">
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No canonical memory entries are visible for this access context and private scope.
          </CardContent>
        </Card>
      ) : null}
      {canQuery && listQuery.data && listQuery.data.items.length > 0 ? (
        <div className="grid gap-3" data-testid="memory-results-list">
          {listQuery.data.items.map((item) => (
            <MemoryListCard
              item={item}
              key={item.memoryId}
              onSelect={selectMemory}
              selected={item.memoryId === selectedMemoryId}
            />
          ))}
        </div>
      ) : null}
      <MemoryDetailPanel
        accessRequest={accessRequest}
        enabled={canQuery && Boolean(selectedMemoryId)}
        memoryId={selectedMemoryId}
      />
    </div>
  );
}
