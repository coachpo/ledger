import { ArrowLeft } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  useAdminMemoryEntry,
  useAdminMemoryEvents,
  useAdminMemoryRevisions,
  useCreateAdminMemoryRevision,
  useDeleteAdminMemoryEntry,
  useUpdateAdminMemoryWorkflowVisibility,
} from "@/hooks/use-memory";

import {
  DetailInspection,
  EventsInspection,
  MemoryDeleteDialog,
  MemoryDetailContext,
  MemoryLoadState,
  QueryStateCard,
  RevisionDialog,
  RevisionsInspection,
} from "./admin-components";
import type {
  AdminRevisionVariables,
  AdminWorkflowVisibilityVariables,
} from "./admin-helpers";

function DetailPageMessage({
  description,
  memoryId,
  testId,
  title,
}: {
  description: string;
  memoryId: string;
  testId: string;
  title: string;
}) {
  return (
    <WorkspacePageShell
      bodyAriaLabel="Memory admin detail message workspace"
      bodyClassName="gap-4"
      className="min-h-full"
      contextBar={<MemoryDetailContext memoryId={memoryId} />}
      testId="memory-detail-page"
    >
      <Card
        className="min-w-0 border-destructive/30 bg-destructive/5 shadow-sm"
        data-testid={testId}
      >
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild size="sm" variant="outline">
            <Link to="/memory">
              <ArrowLeft data-icon="inline-start" />
              Back to Memory Admin
            </Link>
          </Button>
        </CardContent>
      </Card>
    </WorkspacePageShell>
  );
}

export function MemoryDetailPage() {
  const navigate = useNavigate();
  const { memoryId } = useParams<{ memoryId: string }>();
  const resolvedMemoryId = memoryId ?? "";
  const canReadMemory = Boolean(resolvedMemoryId);
  const detailQuery = useAdminMemoryEntry(resolvedMemoryId || undefined, {
    enabled: canReadMemory,
  });
  const revisionsQuery = useAdminMemoryRevisions(
    resolvedMemoryId || undefined,
    {},
    { enabled: canReadMemory },
  );
  const eventsQuery = useAdminMemoryEvents(
    resolvedMemoryId || undefined,
    {},
    { enabled: canReadMemory },
  );
  const revisionMutation = useCreateAdminMemoryRevision();
  const workflowVisibilityMutation = useUpdateAdminMemoryWorkflowVisibility();
  const deleteMutation = useDeleteAdminMemoryEntry();

  const reviseMemory = async (variables: AdminRevisionVariables) => {
    await revisionMutation.mutateAsync(variables);
    toast.success("Memory revision created");
  };

  const updateWorkflowVisibility = async (
    variables: AdminWorkflowVisibilityVariables,
  ) => {
    await workflowVisibilityMutation.mutateAsync(variables);
  };

  const deleteMemory = async () => {
    await deleteMutation.mutateAsync(resolvedMemoryId);
    toast.success("Memory deleted");
    navigate("/memory", { replace: true });
  };

  if (!resolvedMemoryId) {
    return (
      <DetailPageMessage
        description="Open a memory entry from the Memory Admin list to inspect detail, revisions, and audit events."
        memoryId="missing"
        testId="memory-detail-missing-id"
        title="Memory id is required"
      />
    );
  }

  const detail = detailQuery.data;
  const actions = (
    <div className="flex min-w-0 flex-wrap items-center gap-2 sm:justify-end">
      <Button asChild size="sm" variant="ghost">
        <Link to="/memory">
          <ArrowLeft data-icon="inline-start" />
          Memory Admin
        </Link>
      </Button>
      <RevisionDialog
        detail={detail}
        onRevise={reviseMemory}
        pending={revisionMutation.isPending}
      />
      <MemoryDeleteDialog
        disabled={!detail}
        isPending={deleteMutation.isPending}
        onDelete={deleteMemory}
      />
    </div>
  );

  const detailError =
    detailQuery.error ?? new Error("Memory detail is unavailable.");

  if (detailQuery.isError && !detail) {
    return (
      <DetailPageMessage
        description={
          detailQuery.error instanceof Error
            ? detailQuery.error.message
            : "The selected memory entry could not be loaded."
        }
        memoryId={resolvedMemoryId}
        testId="memory-detail-error"
        title="Unable to load memory detail"
      />
    );
  }

  return (
    <WorkspacePageShell
      bodyAriaLabel="Memory admin detail workspace"
      bodyClassName="gap-4"
      className="min-h-full"
      contextBar={
        <MemoryDetailContext
          actions={actions}
          detail={detail}
          memoryId={resolvedMemoryId}
        />
      }
      testId="memory-detail-page"
    >
      <Tabs className="min-w-0" defaultValue="detail">
        <TabsList className="h-8" data-testid="memory-detail-tabs">
          <TabsTrigger className="text-xs" value="detail">
            Detail
          </TabsTrigger>
          <TabsTrigger className="text-xs" value="revisions">
            Revisions
          </TabsTrigger>
          <TabsTrigger className="text-xs" value="events">
            Audit events
          </TabsTrigger>
        </TabsList>
        <TabsContent className="mt-0 min-w-0" value="detail">
          {detailQuery.isPending ? (
            <QueryStateCard label="Loading admin detail..." />
          ) : detail ? (
            <DetailInspection
              detail={detail}
              onUpdateWorkflowVisibility={updateWorkflowVisibility}
              workflowVisibilityPending={workflowVisibilityMutation.isPending}
            />
          ) : (
            <MemoryLoadState error={detailError} />
          )}
        </TabsContent>
        <TabsContent className="mt-0 min-w-0" value="revisions">
          {revisionsQuery.isPending ? (
            <QueryStateCard label="Loading revision history..." />
          ) : revisionsQuery.isError ? (
            <MemoryLoadState error={revisionsQuery.error} />
          ) : (
            <RevisionsInspection revisions={revisionsQuery.data?.items ?? []} />
          )}
        </TabsContent>
        <TabsContent className="mt-0 min-w-0" value="events">
          {eventsQuery.isPending ? (
            <QueryStateCard label="Loading audit events..." />
          ) : eventsQuery.isError ? (
            <MemoryLoadState error={eventsQuery.error} />
          ) : (
            <EventsInspection events={eventsQuery.data?.items ?? []} />
          )}
        </TabsContent>
      </Tabs>
    </WorkspacePageShell>
  );
}
