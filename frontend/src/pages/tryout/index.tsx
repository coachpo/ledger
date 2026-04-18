import { useCallback, useEffect, useMemo, useState } from "react";
import { FlaskConical, Loader2, Play, Save, ShieldAlert, X } from "lucide-react";
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
import { Separator } from "@/components/ui/separator";
import {
  useRuntimeRun,
  useRuntimeRunArtifact,
  useRuntimeRunTrace,
} from "@/hooks/use-runtime";
import {
  useStudioAgentSpecs,
  useStudioPersonas,
  useStudioWorkflowSpecs,
} from "@/hooks/use-studio";
import { useCreateTryout, usePersistTryout, useTryout } from "@/hooks/use-tryouts";
import type { RuntimeTraceEventRead } from "@/lib/types/runtime";

import { TryoutApprovalCard } from "./approval-card";
import {
  buildRuntimeInputMap,
  buildValidationMessages,
  formatDateTimeOrFallback,
  getTargetSummary,
  sortByKey,
  stringifyJson,
  toPersonaRef,
} from "./shared";
import { useTryoutDraftState } from "./use-tryout-draft";

export function TryoutPage() {
  const [activeRunId, setActiveRunId] = useState<number | undefined>();
  const [messages, setMessages] = useState<string[]>([]);
  const {
    addRuntimeInputRow,
    draft,
    removeRuntimeInputRow,
    setDraft,
    togglePersonaProfile,
    updateDraft,
    updateRuntimeInputRow,
  } = useTryoutDraftState(() => setMessages([]));

  const createTryoutMutation = useCreateTryout();
  const persistTryoutMutation = usePersistTryout(activeRunId);

  const workflowsQuery = useStudioWorkflowSpecs({ status: "ACTIVE" });
  const agentsQuery = useStudioAgentSpecs({ status: "ACTIVE" });
  const personasQuery = useStudioPersonas({ enabled: true, status: "ACTIVE" });

  const tryoutQuery = useTryout(activeRunId);
  const runtimeRunQuery = useRuntimeRun(activeRunId);
  const artifactQuery = useRuntimeRunArtifact(activeRunId);
  const traceQuery = useRuntimeRunTrace(activeRunId);

  const workflowSpecs = useMemo(
    () => sortByKey(workflowsQuery.data?.items ?? []),
    [workflowsQuery.data?.items],
  );
  const agentSpecs = useMemo(
    () => sortByKey(agentsQuery.data?.items ?? []),
    [agentsQuery.data?.items],
  );
  const personaProfiles = useMemo(
    () => [...(personasQuery.data?.items ?? [])].sort((left, right) =>
      left.displayName.localeCompare(right.displayName),
    ),
    [personasQuery.data?.items],
  );

  useEffect(() => {
    setDraft((current) => {
      const nextWorkflowSpecId =
        current.workflowSpecId &&
        workflowSpecs.some((workflow) => String(workflow.id) === current.workflowSpecId)
          ? current.workflowSpecId
          : (workflowSpecs[0] ? String(workflowSpecs[0].id) : "");

      return nextWorkflowSpecId === current.workflowSpecId
        ? current
        : { ...current, workflowSpecId: nextWorkflowSpecId };
    });
  }, [setDraft, workflowSpecs]);

  useEffect(() => {
    setDraft((current) => {
      const nextAgentSpecId =
        current.agentSpecId &&
        agentSpecs.some((agent) => String(agent.id) === current.agentSpecId)
          ? current.agentSpecId
          : (agentSpecs[0] ? String(agentSpecs[0].id) : "");

      return nextAgentSpecId === current.agentSpecId
        ? current
        : { ...current, agentSpecId: nextAgentSpecId };
    });
  }, [agentSpecs, setDraft]);

  const selectedWorkflowSpec = useMemo(
    () => workflowSpecs.find((workflow) => String(workflow.id) === draft.workflowSpecId),
    [draft.workflowSpecId, workflowSpecs],
  );
  const selectedAgentSpec = useMemo(
    () => agentSpecs.find((agent) => String(agent.id) === draft.agentSpecId),
    [agentSpecs, draft.agentSpecId],
  );
  const selectedPersonaRefs = useMemo(
    () =>
      personaProfiles
        .filter((persona) => draft.personaProfileKeys.includes(persona.key))
        .map(toPersonaRef),
    [draft.personaProfileKeys, personaProfiles],
  );
  const runtimeInputs = useMemo(() => buildRuntimeInputMap(draft), [draft]);
  const traceEvents = useMemo(
    () => [...(traceQuery.data?.items ?? [])].slice(-10).reverse(),
    [traceQuery.data?.items],
  );
  const activeRun = runtimeRunQuery.data;
  const activeTryout = tryoutQuery.data;
  const activeArtifact = artifactQuery.data;
  const activeFinalOutput = activeTryout?.finalOutput ?? activeArtifact?.finalOutput ?? null;

  const refreshActiveRun = useCallback(async () => {
    if (!activeRunId) {
      return;
    }

    await Promise.all([
      tryoutQuery.refetch(),
      runtimeRunQuery.refetch(),
      artifactQuery.refetch(),
      traceQuery.refetch(),
    ]);
  }, [activeRunId, artifactQuery, runtimeRunQuery, traceQuery, tryoutQuery]);

  const handleExecute = async () => {
    const validationMessages = buildValidationMessages({
      agentSpec: selectedAgentSpec,
      selectedTargetKind: draft.targetKind,
      workflowSpec: selectedWorkflowSpec,
    });

    if (validationMessages.length > 0) {
      setMessages(validationMessages);
      return;
    }

    try {
      const created = await createTryoutMutation.mutateAsync({
        agentSpecKey:
          draft.targetKind === "single_agent" ? (selectedAgentSpec?.key ?? null) : null,
        agentSpecVersion:
          draft.targetKind === "single_agent" ? (selectedAgentSpec?.version ?? null) : null,
        inputs: Object.keys(runtimeInputs).length > 0 ? runtimeInputs : undefined,
        personaProfileRefs: selectedPersonaRefs.length > 0 ? selectedPersonaRefs : undefined,
        workflowSpecKey:
          draft.targetKind === "workflow" ? (selectedWorkflowSpec?.key ?? null) : null,
        workflowSpecVersion:
          draft.targetKind === "workflow" ? (selectedWorkflowSpec?.version ?? null) : null,
      });

      setActiveRunId(created.runId);
      setMessages([]);
      toast.success(`Tryout execution started as run #${created.runId}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to execute Tryout");
    }
  };

  const handlePersist = async () => {
    if (!activeRunId) {
      return;
    }

    try {
      const persisted = await persistTryoutMutation.mutateAsync();

      if (persisted.runId !== activeRunId) {
        toast.error("Persist returned a different run id. Keeping the active Tryout run unchanged.");
      } else {
        toast.success(`Run #${persisted.runId} persisted`);
      }

      await refreshActiveRun();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to persist Tryout run");
    }
  };

  return (
    <div className="flex flex-col gap-4 p-4" data-testid="tryout-page">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold tracking-tight">Tryout</h1>
        <p className="text-sm text-muted-foreground">
          Execute one workflow spec or one single-agent spec, inspect the persisted runtime result,
          and resolve approval gates without leaving the main shell.
        </p>
      </div>

      {messages.length > 0 ? (
        <Alert variant="destructive">
          <ShieldAlert />
          <AlertTitle>Tryout action blocked</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-5">
              {messages.map((message) => (
                <li key={message}>{message}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Tryout request</CardTitle>
            <CardDescription>
              Form draft stays local until you execute. After a run exists, inspect, persist, and
              approval actions all stay pinned to the active run id.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-6">
            <section className="flex flex-col gap-3">
              <p className="text-sm font-medium">Execution target</p>
              <div className="flex flex-wrap gap-4">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    checked={draft.targetKind === "workflow"}
                    name="tryout-target-kind"
                    onChange={() => updateDraft("targetKind", "workflow")}
                    type="radio"
                  />
                  <span>Workflow spec</span>
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input
                    checked={draft.targetKind === "single_agent"}
                    name="tryout-target-kind"
                    onChange={() => updateDraft("targetKind", "single_agent")}
                    type="radio"
                  />
                  <span>Single-agent spec</span>
                </label>
              </div>
              {draft.targetKind === "workflow" ? (
                <div className="flex flex-col gap-2">
                  <Label htmlFor="tryout-workflow-spec">Workflow spec</Label>
                  <select
                    aria-label="Workflow spec"
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                    data-testid="tryout-workflow-select"
                    id="tryout-workflow-spec"
                    onChange={(event) => updateDraft("workflowSpecId", event.target.value)}
                    value={draft.workflowSpecId}
                  >
                    <option value="">
                      {workflowsQuery.isPending
                        ? "Loading workflow specs..."
                        : "Select a workflow spec"}
                    </option>
                    {workflowSpecs.map((workflow) => (
                      <option key={workflow.id} value={String(workflow.id)}>
                        {workflow.name} ({workflow.key} · v{workflow.version})
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-muted-foreground">
                    Workflow Tryout runs pin the selected workflow key and version at execution
                    time.
                  </p>
                </div>
              ) : (
                <div className="flex flex-col gap-2">
                  <Label htmlFor="tryout-agent-spec">Single-agent spec</Label>
                  <select
                    aria-label="Single-agent spec"
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 text-sm"
                    data-testid="tryout-agent-select"
                    id="tryout-agent-spec"
                    onChange={(event) => updateDraft("agentSpecId", event.target.value)}
                    value={draft.agentSpecId}
                  >
                    <option value="">
                      {agentsQuery.isPending ? "Loading agent specs..." : "Select an agent spec"}
                    </option>
                    {agentSpecs.map((agent) => (
                      <option key={agent.id} value={String(agent.id)}>
                        {agent.name} ({agent.key} · v{agent.version})
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-muted-foreground">
                    Single-agent Tryout runs pin the selected agent key and version at execution
                    time.
                  </p>
                </div>
              )}
            </section>

            <Separator />

            <section className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <p className="text-sm font-medium">Inputs</p>
                <Button
                  onClick={() =>
                    updateDraft("runtimeInputsOpen", !draft.runtimeInputsOpen)
                  }
                  size="sm"
                  type="button"
                  variant="ghost"
                >
                  {draft.runtimeInputsOpen ? "Hide" : "Show"}
                </Button>
                <Button onClick={addRuntimeInputRow} size="sm" type="button" variant="outline">
                  Add input
                </Button>
              </div>
              {draft.runtimeInputsOpen || draft.runtimeInputRows.length > 0 ? (
                <div className="flex flex-col gap-2 rounded-lg border bg-muted/20 p-4">
                  <p className="text-xs text-muted-foreground">
                    Inputs are trimmed into a flat map before execute, so unfinished rows stay local
                    until both key and value are filled.
                  </p>
                  {draft.runtimeInputRows.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No Tryout inputs added yet.</p>
                  ) : null}
                  {draft.runtimeInputRows.map((row) => (
                    <div className="flex flex-wrap items-center gap-2" key={row.id}>
                      <Input
                        onChange={(event) =>
                          updateRuntimeInputRow(row.id, "key", event.target.value)
                        }
                        placeholder="ticker"
                        value={row.key}
                      />
                      <Input
                        onChange={(event) =>
                          updateRuntimeInputRow(row.id, "value", event.target.value)
                        }
                        placeholder="AAPL"
                        value={row.value}
                      />
                      <Button
                        aria-label={`Remove input ${row.key || row.id}`}
                        onClick={() => removeRuntimeInputRow(row.id)}
                        size="icon"
                        type="button"
                        variant="ghost"
                      >
                        <X />
                      </Button>
                    </div>
                  ))}
                </div>
              ) : null}
            </section>

            <Separator />

            <section className="flex flex-col gap-3">
              <div className="flex flex-col gap-1">
                <p className="text-sm font-medium">Optional personas</p>
                <p className="text-xs text-muted-foreground">
                  Persona refs are passed with the pinned key and version for this execution only.
                </p>
              </div>
              {personasQuery.isPending ? (
                <p className="text-sm text-muted-foreground">Loading persona profiles...</p>
              ) : personaProfiles.length === 0 ? (
                <p className="text-sm text-muted-foreground">No enabled persona profiles available.</p>
              ) : (
                <div className="grid gap-2 md:grid-cols-2">
                  {personaProfiles.map((persona) => (
                    <label
                      className="flex items-start gap-2 rounded-lg border bg-muted/20 p-3 text-sm"
                      key={`${persona.key}-${persona.version}`}
                    >
                      <input
                        checked={draft.personaProfileKeys.includes(persona.key)}
                        onChange={() => togglePersonaProfile(persona.key)}
                        type="checkbox"
                      />
                      <span className="flex flex-col gap-1">
                        <span className="font-medium">{persona.displayName}</span>
                        <span className="text-xs text-muted-foreground">
                          {persona.key} · v{persona.version} · {persona.kind}
                        </span>
                      </span>
                    </label>
                  ))}
                </div>
              )}
            </section>

            <div className="flex flex-wrap items-center gap-3">
              <Button
                data-testid="tryout-execute-button"
                disabled={createTryoutMutation.isPending}
                onClick={handleExecute}
              >
                {createTryoutMutation.isPending ? <Loader2 className="animate-spin" /> : <Play />}
                Execute Tryout
              </Button>
              <Button
                data-testid="tryout-persist-button"
                disabled={!activeRunId || persistTryoutMutation.isPending}
                onClick={handlePersist}
                variant="secondary"
              >
                {persistTryoutMutation.isPending ? <Loader2 className="animate-spin" /> : <Save />}
                Persist Active Run
              </Button>
              <Badge variant="outline">
                {activeRunId ? `Active run #${activeRunId}` : "No active run"}
              </Badge>
            </div>
          </CardContent>
        </Card>

        <div className="flex flex-col gap-4">
          <Card data-testid="tryout-status-panel">
            <CardHeader>
              <CardTitle className="text-base">Persisted run status</CardTitle>
              <CardDescription>
                Status, target metadata, and summary counters all come from the persisted active run.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3 text-sm">
              {!activeRunId ? (
                <p className="text-muted-foreground">Execute a Tryout to inspect a persisted run.</p>
              ) : tryoutQuery.isPending || runtimeRunQuery.isPending ? (
                <p className="text-muted-foreground">Loading run #{activeRunId}...</p>
              ) : tryoutQuery.isError || runtimeRunQuery.isError || !activeTryout || !activeRun ? (
                <p className="text-muted-foreground">
                  {tryoutQuery.error instanceof Error
                    ? tryoutQuery.error.message
                    : runtimeRunQuery.error instanceof Error
                      ? runtimeRunQuery.error.message
                      : "Tryout run not found."}
                </p>
              ) : (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-base font-medium">Run #{activeTryout.runId}</p>
                    <Badge variant="secondary">{activeTryout.status}</Badge>
                    <Badge variant="outline">{activeRun.executionKind}</Badge>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    <p>Target: {getTargetSummary(activeRun)}</p>
                    <p>Created: {formatDateTimeOrFallback(activeRun.createdAt)}</p>
                    <p>Updated: {formatDateTimeOrFallback(activeRun.updatedAt)}</p>
                    <p>Expires: {formatDateTimeOrFallback(activeTryout.expiresAt, "Not scheduled")}</p>
                    <p>Events: {activeTryout.traceSummary.eventCount}</p>
                    <p>Pending approvals: {activeRun.pendingApprovalIds.length}</p>
                    <p>Tool calls: {activeTryout.traceSummary.toolCallCount}</p>
                    <p>Warnings: {activeTryout.traceSummary.warningCount}</p>
                  </div>
                  {activeTryout.terminalError ? (
                    <Alert variant="destructive">
                      <ShieldAlert />
                      <AlertTitle>{activeTryout.terminalError.code}</AlertTitle>
                      <AlertDescription>{activeTryout.terminalError.message}</AlertDescription>
                    </Alert>
                  ) : null}
                </>
              )}
            </CardContent>
          </Card>

          <Card data-testid="tryout-approval-panel">
            <CardHeader>
              <CardTitle className="text-base">Approvals</CardTitle>
              <CardDescription>
                Pending runtime approvals stay attached to the active run id and refresh after each
                resolution.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              {!activeRunId ? (
                <p className="text-sm text-muted-foreground">No active Tryout run yet.</p>
              ) : runtimeRunQuery.isPending ? (
                <p className="text-sm text-muted-foreground">Loading approval state...</p>
              ) : activeRun?.status !== "WAITING_APPROVAL" || activeRun.pendingApprovalIds.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  This run is not waiting on approvals.
                </p>
              ) : (
                activeRun.pendingApprovalIds.map((approvalId) => (
                  <TryoutApprovalCard
                    approvalId={approvalId}
                    key={approvalId}
                    onResolved={refreshActiveRun}
                  />
                ))
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Final output</CardTitle>
            <CardDescription>
              The Tryout read stays authoritative for final output while the artifact panel fills in
              the richer persisted context.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {!activeRunId ? <p className="text-sm text-muted-foreground">No output yet.</p> : null}
            <pre
              className="overflow-x-auto rounded-lg border bg-muted/30 p-4 text-xs"
              data-testid="tryout-final-output"
            >
              {stringifyJson(activeFinalOutput)}
            </pre>
            {activeRunId ? (
              <>
                {activeArtifact?.reportMarkdown ? (
                  <>
                    <Separator />
                    <div className="flex flex-col gap-2">
                      <p className="text-sm font-medium">Report markdown</p>
                      <pre className="overflow-x-auto rounded-lg border bg-muted/30 p-4 text-xs">
                        {activeArtifact.reportMarkdown}
                      </pre>
                    </div>
                  </>
                ) : null}
              </>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Trace</CardTitle>
            <CardDescription>
              Recent persisted trace rows help inspect execution progress and approval checkpoints.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {!activeRunId ? (
              <p className="text-sm text-muted-foreground">Execute a Tryout to inspect trace rows.</p>
            ) : traceQuery.isPending ? (
              <p className="text-sm text-muted-foreground">Loading trace rows...</p>
            ) : traceEvents.length === 0 ? (
              <p className="text-sm text-muted-foreground">No trace rows recorded yet.</p>
            ) : (
              traceEvents.map((event: RuntimeTraceEventRead) => (
                <div
                  className="flex flex-col gap-2 rounded-lg border p-4"
                  data-testid={`tryout-trace-row-${event.eventIndex}`}
                  key={event.eventIndex}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium">{event.eventType}</p>
                    <Badge variant="outline">#{event.eventIndex}</Badge>
                    {event.stepKey ? <Badge variant="secondary">{event.stepKey}</Badge> : null}
                    {event.capabilityKey ? (
                      <Badge variant="secondary">{event.capabilityKey}</Badge>
                    ) : null}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {formatDateTimeOrFallback(event.createdAt)}
                  </p>
                  <pre className="overflow-x-auto rounded-lg bg-muted/30 p-3 text-xs">
                    {stringifyJson(event.payload)}
                  </pre>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Artifact snapshot</CardTitle>
          <CardDescription>
            Persisted artifact details confirm the frozen persona refs, capability resolution, and
            authored prompt context for the active run.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-3">
          <div className="rounded-lg border bg-muted/20 p-4 text-sm">
            <div className="flex items-center gap-2 font-medium">
              <FlaskConical className="size-4" />
              Resolved personas
            </div>
            <p className="mt-2 text-muted-foreground">
              {activeArtifact?.resolvedPersonaProfileRefs.length ?? 0}
            </p>
          </div>
          <div className="rounded-lg border bg-muted/20 p-4 text-sm">
            <p className="font-medium">Resolved capabilities</p>
            <p className="mt-2 text-muted-foreground">
              {activeArtifact?.resolvedCapabilities.length ?? 0}
            </p>
          </div>
          <div className="rounded-lg border bg-muted/20 p-4 text-sm">
            <p className="font-medium">Prompt report slug</p>
            <p className="mt-2 text-muted-foreground">
              {activeArtifact?.promptReportSlug ?? "No prompt report"}
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
