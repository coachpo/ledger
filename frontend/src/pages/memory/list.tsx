import { useMemo, useState } from "react";
import { toast } from "sonner";

import { EmptyStatePanel } from "@/components/shared/empty-state-panel";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import {
  ResourceStatusBadge,
  type ResourceStatusTone,
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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import {
  useApproveWorkflowMemoryProposal,
  useRejectWorkflowMemoryProposal,
  useWorkflowMemoryAuditEvents,
  useWorkflowMemoryProposals,
  useWorkflowMemoryQuarantine,
} from "@/hooks/use-memory";
import { formatDateTime } from "@/lib/format";
import type {
  WorkflowMemoryAuditEventRead,
  WorkflowMemoryPolicyStatus,
  WorkflowMemoryProposalRead,
  WorkflowMemoryProposalStatusFilter,
  WorkflowMemoryQuarantineRead,
} from "@/lib/types/memory";

const DEFAULT_PROPOSAL_STATUS: WorkflowMemoryProposalStatusFilter =
  "review_pending";

const PROPOSAL_STATUS_OPTIONS: readonly {
  label: string;
  value: WorkflowMemoryProposalStatusFilter;
}[] = [
  { label: "Review pending", value: "review_pending" },
  { label: "Proposed", value: "proposed" },
  { label: "Committed", value: "committed" },
  { label: "Rejected", value: "rejected" },
  { label: "Quarantined", value: "quarantined" },
  { label: "All", value: "all" },
];

const WORKFLOW_MEMORY_STATUS_TONES: Record<
  WorkflowMemoryPolicyStatus,
  ResourceStatusTone
> = {
  committed: "success",
  proposed: "neutral",
  quarantined: "danger",
  rejected: "danger",
  review_pending: "warning",
};

function titleCase(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (match) => match.toUpperCase());
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function getProposalStatusLabel(status: WorkflowMemoryProposalStatusFilter) {
  return (
    PROPOSAL_STATUS_OPTIONS.find((option) => option.value === status)?.label ??
    titleCase(status)
  );
}

function WorkflowMemoryStatusBadge({
  status,
}: {
  status: WorkflowMemoryPolicyStatus;
}) {
  return (
    <ResourceStatusBadge
      label={titleCase(status)}
      tone={WORKFLOW_MEMORY_STATUS_TONES[status]}
    />
  );
}

function ProposalStatusFilterControl({
  status,
  onStatusChange,
}: {
  status: WorkflowMemoryProposalStatusFilter;
  onStatusChange: (status: WorkflowMemoryProposalStatusFilter) => void;
}) {
  return (
    <div className="flex min-w-52 flex-col gap-1.5 sm:w-56">
      <Label className="text-xs font-medium" htmlFor="memory-proposal-status">
        Proposal status
      </Label>
      <Select
        onValueChange={(value) =>
          onStatusChange(value as WorkflowMemoryProposalStatusFilter)
        }
        value={status}
      >
        <SelectTrigger id="memory-proposal-status">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectGroup>
            {PROPOSAL_STATUS_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectGroup>
        </SelectContent>
      </Select>
    </div>
  );
}

function JsonBlock({ label, value }: { label: string; value: unknown }) {
  return (
    <section className="flex min-w-0 flex-col gap-2">
      <h4 className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </h4>
      <pre className="max-h-56 overflow-auto rounded-lg border border-border/70 bg-ui-surface-grouped/70 px-3 py-2 text-xs leading-5 shadow-inner">
        {JSON.stringify(value, null, 2)}
      </pre>
    </section>
  );
}

function ProposalCard({ proposal }: { proposal: WorkflowMemoryProposalRead }) {
  const [reason, setReason] = useState("");
  const approveMutation = useApproveWorkflowMemoryProposal();
  const rejectMutation = useRejectWorkflowMemoryProposal();
  const reasonId = `memory-review-reason-${proposal.proposalId}`;
  const canReview = proposal.status === "review_pending";

  const review = async (action: "approve" | "reject") => {
    const mutation = action === "approve" ? approveMutation : rejectMutation;
    try {
      await mutation.mutateAsync({
        proposalId: proposal.proposalId,
        payload: { reason: reason.trim() || null },
      });
      toast.success(
        action === "approve"
          ? "Memory proposal approved"
          : "Memory proposal rejected",
      );
      setReason("");
    } catch (error) {
      toast.error(errorMessage(error, "Memory proposal review failed."));
    }
  };

  const reviewPending = approveMutation.isPending || rejectMutation.isPending;

  return (
    <Card data-testid={`memory-proposal-${proposal.proposalId}`}>
      <CardHeader className="gap-3">
        <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex min-w-0 flex-col gap-1">
            <CardTitle className="break-words text-base font-semibold">
              {proposal.kind} in {proposal.namespace}
            </CardTitle>
            <CardDescription className="break-words">
              {proposal.packageKey} / {proposal.workflowKey} / {proposal.agentKey} / {proposal.stepId}
            </CardDescription>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <WorkflowMemoryStatusBadge status={proposal.status} />
            <Badge variant="outline">Proposal {proposal.proposalId}</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <Detail label="Run" value={proposal.runId ? `#${proposal.runId}` : "No run"} />
          <Detail label="Invocation" value={proposal.invocationId ?? "No invocation"} />
          <Detail label="Source output" value={proposal.sourceOutputPath ?? "Not recorded"} />
          <Detail label="Updated" value={formatDateTime(proposal.updatedAt)} />
        </div>
        {proposal.reason ? (
          <p className="rounded-lg border border-border/70 bg-ui-surface-grouped/60 px-3 py-2 text-sm text-muted-foreground">
            {proposal.reason}
          </p>
        ) : null}
        <div className="grid gap-3 lg:grid-cols-2">
          <JsonBlock label="Proposed memory content" value={proposal.content} />
          <JsonBlock label="Policy detectors" value={proposal.detectors} />
        </div>
        {canReview ? (
          <div className="flex flex-col gap-2 rounded-xl border border-border/70 bg-ui-surface-elevated/50 p-3">
            <Label htmlFor={reasonId}>Review reason</Label>
            <Textarea
              id={reasonId}
              onChange={(event) => setReason(event.target.value)}
              placeholder="Optional reason recorded with this approve or reject action."
              rows={3}
              value={reason}
            />
            <div className="flex flex-wrap gap-2">
              <Button
                disabled={reviewPending}
                onClick={() => void review("approve")}
                type="button"
              >
                Approve proposal
              </Button>
              <Button
                disabled={reviewPending}
                onClick={() => void review("reject")}
                type="button"
                variant="outline"
              >
                Reject proposal
              </Button>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-border/60 bg-ui-surface-grouped/50 px-3 py-2">
      <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd className="mt-1 break-words text-sm text-foreground">{value}</dd>
    </div>
  );
}

function AuditEventCard({ event }: { event: WorkflowMemoryAuditEventRead }) {
  return (
    <Card data-testid={`memory-audit-event-${event.eventId}`}>
      <CardHeader className="gap-2">
        <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <CardTitle className="break-words text-base font-semibold">
              {titleCase(event.eventType)}
            </CardTitle>
            <CardDescription className="break-words">
              {event.targetType} {event.targetId} / {event.packageKey} / {event.workflowKey}
            </CardDescription>
          </div>
          <Badge variant="outline">{formatDateTime(event.createdAt)}</Badge>
        </div>
      </CardHeader>
      <CardContent>
        <JsonBlock label="Audit event" value={event.event} />
      </CardContent>
    </Card>
  );
}

function QuarantineCard({ item }: { item: WorkflowMemoryQuarantineRead }) {
  const quarantineStatus = item.resolvedAt
    ? ({ label: "Resolved", tone: "success" } as const)
    : ({ label: "Unresolved", tone: "danger" } as const);

  return (
    <Card data-testid={`memory-quarantine-${item.quarantineId}`}>
      <CardHeader className="gap-2">
        <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <CardTitle className="break-words text-base font-semibold">
              {item.reasonCode}
            </CardTitle>
            <CardDescription className="break-words">
              {item.packageKey ?? "No package"} / {item.workflowKey ?? "No workflow"} / {item.agentKey ?? "No agent"}
            </CardDescription>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <ResourceStatusBadge
              label={quarantineStatus.label}
              tone={quarantineStatus.tone}
            />
            <Badge variant="outline">Quarantine {item.quarantineId}</Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {item.reason ? (
          <p className="rounded-lg border border-border/70 bg-ui-surface-grouped/60 px-3 py-2 text-sm text-muted-foreground">
            {item.reason}
          </p>
        ) : null}
        <div className="grid gap-3 lg:grid-cols-2">
          <JsonBlock label="Quarantine evidence" value={item.evidence} />
          <JsonBlock label="Detectors" value={item.detectors} />
        </div>
      </CardContent>
    </Card>
  );
}

function SectionState({
  isError,
  isPending,
  emptyDescription,
  emptyTitle,
  error,
}: {
  emptyDescription: string;
  emptyTitle: string;
  error: unknown;
  isError: boolean;
  isPending: boolean;
}) {
  if (isPending) {
    return <InventoryStatePanel title="Loading workflow memory review data" />;
  }
  if (isError) {
    return (
      <InventoryStatePanel
        description={errorMessage(error, "Workflow memory review data failed to load.")}
        title="Workflow memory review data could not be loaded"
        tone="danger"
      />
    );
  }
  return <EmptyStatePanel description={emptyDescription} title={emptyTitle} />;
}

export function MemoryListPage() {
  const [status, setStatus] = useState<WorkflowMemoryProposalStatusFilter>(
    DEFAULT_PROPOSAL_STATUS,
  );
  const proposalParams = useMemo(() => ({ status }), [status]);
  const proposalsQuery = useWorkflowMemoryProposals(proposalParams);
  const auditEventsQuery = useWorkflowMemoryAuditEvents();
  const quarantineQuery = useWorkflowMemoryQuarantine();
  const proposals = proposalsQuery.data?.items ?? [];
  const auditEvents = auditEventsQuery.data?.items ?? [];
  const quarantineItems = quarantineQuery.data?.items ?? [];
  const proposalTotal = proposalsQuery.data?.total ?? proposals.length;
  const hasActiveStatusFilter = status !== DEFAULT_PROPOSAL_STATUS;

  return (
    <InventoryPageShell
      contentClassName="flex flex-col gap-4"
      filterBar={
        hasActiveStatusFilter
          ? {
              items: [
                {
                  active: true,
                  clearLabel: "Reset proposal status filter",
                  id: "proposal-status",
                  label: "Status",
                  value: getProposalStatusLabel(status),
                  onClear: () => setStatus(DEFAULT_PROPOSAL_STATUS),
                },
              ],
              onClearAll: () => setStatus(DEFAULT_PROPOSAL_STATUS),
              testId: "memory-review-active-filters",
            }
          : null
      }
      pageContext={{
        description:
          "Review workflow-generated memory proposals, inspect audit events, and monitor quarantined memory evidence.",
        title: "Workflow Memory Review",
      }}
      testId="memory-list-page"
      toolbar={{
        filters: (
          <ProposalStatusFilterControl
            status={status}
            onStatusChange={setStatus}
          />
        ),
        resultSummary: `${proposalTotal} ${proposalTotal === 1 ? "proposal" : "proposals"} shown`,
      }}
    >
      <Tabs defaultValue="proposals" className="flex min-h-0 flex-col gap-3">
        <TabsList aria-label="Workflow memory review sections">
          <TabsTrigger value="proposals">Proposals</TabsTrigger>
          <TabsTrigger value="audit">Audit events</TabsTrigger>
          <TabsTrigger value="quarantine">Quarantine</TabsTrigger>
        </TabsList>
        <TabsContent className="flex flex-col gap-4" value="proposals">
          {proposals.length > 0 ? (
            proposals.map((proposal) => (
              <ProposalCard key={proposal.proposalId} proposal={proposal} />
            ))
          ) : (
            <SectionState
              emptyDescription="No workflow memory proposals match this status."
              emptyTitle="No proposals to review"
              error={proposalsQuery.error}
              isError={proposalsQuery.isError}
              isPending={proposalsQuery.isPending}
            />
          )}
        </TabsContent>
        <TabsContent className="flex flex-col gap-4" value="audit">
          {auditEvents.length > 0 ? (
            auditEvents.map((event) => (
              <AuditEventCard event={event} key={event.eventId} />
            ))
          ) : (
            <SectionState
              emptyDescription="No memory proposal or review events have been recorded yet."
              emptyTitle="No audit events"
              error={auditEventsQuery.error}
              isError={auditEventsQuery.isError}
              isPending={auditEventsQuery.isPending}
            />
          )}
        </TabsContent>
        <TabsContent className="flex flex-col gap-4" value="quarantine">
          {quarantineItems.length > 0 ? (
            quarantineItems.map((item) => (
              <QuarantineCard item={item} key={item.quarantineId} />
            ))
          ) : (
            <SectionState
              emptyDescription="No unresolved workflow memory quarantine records are present."
              emptyTitle="No quarantined memory"
              error={quarantineQuery.error}
              isError={quarantineQuery.isError}
              isPending={quarantineQuery.isPending}
            />
          )}
        </TabsContent>
      </Tabs>
    </InventoryPageShell>
  );
}
