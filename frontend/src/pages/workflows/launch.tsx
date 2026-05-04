import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Loader2, PlayCircle } from "lucide-react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { ExactJsonPreview } from "@/components/platform-authoring/inspectors/exact-json-preview";
import { SchemaForm } from "@/components/platform-authoring/generated-form/schema-form";
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
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useCreateWorkflowLaunch,
  useWorkflowLaunch,
  useWorkflowVersions,
} from "@/hooks/use-workflows";
import { ApiRequestError } from "@/lib/api-client";
import { stringifyJson } from "@/lib/platform-authoring/common/serialization";
import { parseSchemaJsonText } from "@/lib/platform-authoring/schema/codec";
import { createDefaultSchemaNode } from "@/lib/platform-authoring/schema/factories";
import type { ValueEntry } from "@/lib/platform-authoring/values/types";

import { PlatformResourceBadges } from "../platform-resource-shared";
import { createDefaultRunInputValue, decodeRunInputValue } from "./run-input";

export function WorkflowLaunchPage() {
  const { workflowId } = useParams<{ workflowId: string }>();
  const navigate = useNavigate();
  const versionsQuery = useWorkflowVersions(workflowId);
  const [selectedVersion, setSelectedVersion] = useState<number | undefined>(undefined);
  const launchQuery = useWorkflowLaunch(workflowId, selectedVersion);
  const createLaunch = useCreateWorkflowLaunch();
  const [runInput, setRunInput] = useState<ValueEntry>(() =>
    createDefaultRunInputValue(createDefaultSchemaNode("object")),
  );

  useEffect(() => {
    if (selectedVersion !== undefined || !versionsQuery.data?.items.length) {
      return;
    }

    setSelectedVersion(versionsQuery.data.items[0].version);
  }, [selectedVersion, versionsQuery.data?.items]);

  const launch = launchQuery.data;
  const activeVersion = launch?.version ?? selectedVersion;
  const inputSchemaJson = useMemo(
    () => stringifyJson(launch?.inputSchema ?? { additionalProperties: false, properties: {}, type: "object" }),
    [launch?.inputSchema],
  );
  const inputSchemaBuilder = useMemo(() => {
    const parsedSchema = parseSchemaJsonText(inputSchemaJson);
    return parsedSchema.builder ?? createDefaultSchemaNode("object");
  }, [inputSchemaJson]);
  const runInputPayload = useMemo(() => decodeRunInputValue(runInput), [runInput]);
  const rawRunInputJson = useMemo(() => stringifyJson(runInputPayload), [runInputPayload]);

  useEffect(() => {
    setRunInput(createDefaultRunInputValue(inputSchemaBuilder));
  }, [inputSchemaBuilder]);

  const handleSubmit = async () => {
    if (!workflowId || activeVersion === undefined) {
      return;
    }

    try {
      const run = await createLaunch.mutateAsync({
        payload: { parameters: runInputPayload, version: activeVersion },
        workflowId,
      });
      toast.success("Workflow run queued");
      navigate(`/runs/${run.id}`);
    } catch (error) {
      const message = error instanceof ApiRequestError || error instanceof Error
        ? error.message
        : "Failed to launch workflow run";
      toast.error(message);
    }
  };

  if (versionsQuery.isPending || launchQuery.isPending) {
    return <div className="p-4 text-sm text-muted-foreground">Loading workflow launch details...</div>;
  }

  if (versionsQuery.isError || launchQuery.isError || !launch || activeVersion === undefined) {
    const error = versionsQuery.error ?? launchQuery.error;
    return (
      <div className="p-4 text-sm text-muted-foreground">
        {error instanceof Error ? error.message : "Workflow launch details could not be loaded."}
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4 p-4" data-testid="workflow-launch-page">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex flex-col gap-2">
          <div className="flex flex-col gap-1">
            <h1 className="text-xl font-semibold tracking-tight">Run {launch.name}</h1>
            <p className="text-sm text-muted-foreground">
              {launch.description || "Fill the workflow parameters and queue a new run."}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{launch.key}</Badge>
            <Badge variant="secondary">v{launch.version}</Badge>
          </div>
        </div>
        <Button data-testid="workflow-launch-back" size="sm" variant="outline" onClick={() => navigate(`/workflows/${launch.workflowId}`)}>
          <ArrowLeft data-icon="inline-start" />
          Workflow Detail
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Launch Settings</CardTitle>
          <CardDescription>Select the workflow version to queue.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <div className="flex flex-col gap-2">
            <Label>Version</Label>
            <Select value={String(activeVersion)} onValueChange={(value) => setSelectedVersion(Number(value))}>
              <SelectTrigger aria-label="Workflow version" data-testid="workflow-launch-version-select">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {(versionsQuery.data?.items ?? []).map((version) => (
                    <SelectItem key={version.version} value={String(version.version)}>
                      v{version.version} · {version.status}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <Label>Selected workflow</Label>
            <div className="flex min-h-9 items-center rounded-md border border-border bg-muted/20 px-3 py-2">
              <PlatformResourceBadges status={versionsQuery.data?.items.find((item) => item.version === activeVersion)?.status ?? "published"} version={activeVersion} />
            </div>
          </div>
        </CardContent>
      </Card>

      {launchQuery.isFetching ? (
        <Alert>
          <Loader2 className="animate-spin" />
          <AlertTitle>Refreshing launch metadata</AlertTitle>
          <AlertDescription>The parameter form will update when the selected version metadata arrives.</AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(22rem,0.45fr)]">
        <div data-testid="workflow-launch-input-form">
          <SchemaForm
            description="Fill the workflow parameters through the shared schema-driven form. The submitted request uses the strict launch envelope."
            disabled={createLaunch.isPending || launchQuery.isFetching}
            label="Workflow parameters"
            schema={inputSchemaBuilder}
            value={runInput}
            onChange={setRunInput}
          />
        </div>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Launch Preview</CardTitle>
            <CardDescription>Read-only parameters that will be submitted.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <ExactJsonPreview
              ariaLabel="Exact raw workflow launch parameters JSON"
              data-testid="workflow-launch-parameters-json"
              textareaClassName="min-h-48"
              value={rawRunInputJson}
            />
            <Button data-testid="workflow-launch-submit" disabled={createLaunch.isPending || launchQuery.isFetching} onClick={() => void handleSubmit()}>
              {createLaunch.isPending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : <PlayCircle data-icon="inline-start" />}
              Queue Run
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
