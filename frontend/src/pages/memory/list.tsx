import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { toast } from "sonner";

import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
import {
  useAdminMemoryEntries,
  useCreateAdminMemoryEntry,
  useDeleteAdminMemoryEntry,
} from "@/hooks/use-memory";
import type { MemoryAdminCreateRequest } from "@/lib/types/memory";

import {
  MemoryAdminFilterControls,
  MemoryContextContract,
  MemoryCreateDialog,
  MemoryListPane,
} from "./admin-components";
import {
  ALL_SCOPES_FILTER,
  ALL_WORKFLOW_VISIBILITY_FILTER,
  buildAdminListParams,
} from "./admin-helpers";

const FILTER_PARAM_KEYS = [
  "packageKey",
  "workflowKey",
  "agentKey",
  "runId",
  "scopeType",
  "query",
  "kind",
  "visibleToWorkflow",
] as const;

export function MemoryListPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [packageKey, setPackageKey] = useState(
    searchParams.get("packageKey") ?? "",
  );
  const [workflowKey, setWorkflowKey] = useState(
    searchParams.get("workflowKey") ?? "",
  );
  const [agentKey, setAgentKey] = useState(searchParams.get("agentKey") ?? "");
  const [runId, setRunId] = useState(searchParams.get("runId") ?? "");
  const [scopeType, setScopeType] = useState(
    searchParams.get("scopeType") ?? ALL_SCOPES_FILTER,
  );
  const [query, setQuery] = useState(searchParams.get("query") ?? "");
  const [kind, setKind] = useState(searchParams.get("kind") ?? "");
  const [workflowVisibility, setWorkflowVisibility] = useState(
    searchParams.get("visibleToWorkflow") ?? ALL_WORKFLOW_VISIBILITY_FILTER,
  );

  const listParams = useMemo(
    () =>
      buildAdminListParams({
        agentKey,
        kind,
        packageKey,
        query,
        runId,
        scopeType,
        workflowKey,
        workflowVisibility,
      }),
    [
      agentKey,
      kind,
      packageKey,
      query,
      runId,
      scopeType,
      workflowKey,
      workflowVisibility,
    ],
  );

  const listQuery = useAdminMemoryEntries(listParams, { enabled: true });
  const createMutation = useCreateAdminMemoryEntry();
  const deleteMutation = useDeleteAdminMemoryEntry();

  const resetFilters = () => {
    setPackageKey("");
    setWorkflowKey("");
    setAgentKey("");
    setRunId("");
    setScopeType(ALL_SCOPES_FILTER);
    setQuery("");
    setKind("");
    setWorkflowVisibility(ALL_WORKFLOW_VISIBILITY_FILTER);
    const next = new URLSearchParams(searchParams);
    FILTER_PARAM_KEYS.forEach((key) => next.delete(key));
    setSearchParams(next);
  };

  const createMemory = async (payload: MemoryAdminCreateRequest) => {
    const created = await createMutation.mutateAsync(payload);
    toast.success("Memory created");
    navigate(`/memory/${created.memoryId}`);
  };

  const deleteMemory = async (memoryId: string) => {
    await deleteMutation.mutateAsync(memoryId);
    toast.success("Memory deleted");
  };

  const items = listQuery.data?.items ?? [];
  const total = listQuery.data?.total ?? items.length;
  const hasActiveFilters = Object.keys(listParams).length > 0;

  return (
    <WorkspacePageShell
      bodyAriaLabel="Memory admin browse workspace"
      bodyClassName="gap-3"
      className="min-h-full"
      contextBar={
        <MemoryContextContract
          createAction={
            <MemoryCreateDialog
              onCreate={createMemory}
              pending={createMutation.isPending}
            />
          }
          onReset={resetFilters}
        />
      }
      testId="memory-list-page"
    >
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
        setWorkflowKey={setWorkflowKey}
        setWorkflowVisibility={setWorkflowVisibility}
        workflowKey={workflowKey}
        workflowVisibility={workflowVisibility}
      />
      <MemoryListPane
        deletePending={deleteMutation.isPending}
        hasActiveFilters={hasActiveFilters}
        isError={listQuery.isError}
        isPending={listQuery.isPending}
        items={items}
        listError={listQuery.error}
        onDeleteMemory={deleteMemory}
        total={total}
      />
    </WorkspacePageShell>
  );
}
