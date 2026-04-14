import { useEffect, useState } from "react";
import { Save } from "lucide-react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import {
  useCreateStudioWorkflowSpec,
  useStudioWorkflowSpecByKey,
  useUpdateStudioWorkflowSpec,
} from "@/hooks/use-studio";
import type { WorkflowSpecDraftCreateInput, WorkflowSpecDraftUpdateInput } from "@/lib/types/studio";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

import { StudioReadOnlyBanner, StudioResourceBadges } from "../shared";
import {
  parseJsonValue,
  parseLineList,
  stringifyJson,
  toLineList,
} from "../shared-utils";

type WorkflowEditorValues = {
  key: string;
  name: string;
  graphDefinition: string;
  finalOutputContract: string;
  mentionPolicy: string;
  executionMode: string;
  defaultToolIds: string;
  allowedCapabilityBundleKeys: string;
  connectorIds: string;
  reviewMode: string;
  approvalPolicyOverrides: string;
};

const initialValues: WorkflowEditorValues = {
  key: "",
  name: "",
  graphDefinition: "{}",
  finalOutputContract: JSON.stringify({ description: "Workflow output", kind: "markdown", schema: null }, null, 2),
  mentionPolicy: JSON.stringify({ version: 1, allowCharacterPersonas: true, allowedBuiltinHandles: [] }, null, 2),
  executionMode: "",
  defaultToolIds: "",
  allowedCapabilityBundleKeys: "",
  connectorIds: "",
  reviewMode: "",
  approvalPolicyOverrides: "[]",
};

export function StudioWorkflowEditorPage() {
  const { workflowKey } = useParams<{ workflowKey: string }>();
  const navigate = useNavigate();
  const isEditing = Boolean(workflowKey);
  const { detailQuery, isMissing, matchedItem } = useStudioWorkflowSpecByKey(workflowKey);
  const createMutation = useCreateStudioWorkflowSpec();
  const updateMutation = useUpdateStudioWorkflowSpec();
  const workflow = detailQuery.data;
  const isReadOnly = isEditing && workflow?.origin !== "managed";
  const isSaving = createMutation.isPending || updateMutation.isPending;
  const [values, setValues] = useState<WorkflowEditorValues>(initialValues);

  useEffect(() => {
    if (!workflow) {
      return;
    }

    const nextValues = {
      key: workflow.key,
      name: workflow.name,
      graphDefinition: stringifyJson(workflow.graphDefinition),
      finalOutputContract: stringifyJson(workflow.finalOutputContract),
      mentionPolicy: stringifyJson(workflow.mentionPolicy),
      executionMode: workflow.executionMode ?? "",
      defaultToolIds: toLineList(workflow.defaultToolIds),
      allowedCapabilityBundleKeys: toLineList(workflow.allowedCapabilityBundleKeys),
      connectorIds: toLineList(workflow.connectorIds),
      reviewMode: workflow.reviewMode ?? "",
      approvalPolicyOverrides: stringifyJson(workflow.approvalPolicyOverrides),
    };

    setValues((current) => {
      if (
        current.key === nextValues.key &&
        current.name === nextValues.name &&
        current.graphDefinition === nextValues.graphDefinition &&
        current.finalOutputContract === nextValues.finalOutputContract &&
        current.mentionPolicy === nextValues.mentionPolicy &&
        current.executionMode === nextValues.executionMode &&
        current.defaultToolIds === nextValues.defaultToolIds &&
        current.allowedCapabilityBundleKeys === nextValues.allowedCapabilityBundleKeys &&
        current.connectorIds === nextValues.connectorIds &&
        current.reviewMode === nextValues.reviewMode &&
        current.approvalPolicyOverrides === nextValues.approvalPolicyOverrides
      ) {
        return current;
      }

      return nextValues;
    });
  }, [workflow]);

  const updateValue = <Key extends keyof WorkflowEditorValues>(key: Key, value: WorkflowEditorValues[Key]) => {
    setValues((current) => ({ ...current, [key]: value }));
  };

  const buildPayload = (): WorkflowSpecDraftCreateInput | WorkflowSpecDraftUpdateInput => {
    const key = values.key.trim().toLowerCase();
    const name = values.name.trim();

    if (!isEditing && (!key || !name)) {
      throw new Error("Key and name are required.");
    }

    return {
      key,
      name,
      graphDefinition: parseJsonValue("Graph definition", values.graphDefinition, {}),
      finalOutputContract: parseJsonValue("Final output contract", values.finalOutputContract, {
        description: "Workflow output",
        kind: "markdown",
        schema: null,
      }),
      mentionPolicy: parseJsonValue("Mention policy", values.mentionPolicy, {
        allowCharacterPersonas: true,
        allowedBuiltinHandles: [],
        version: 1,
      }),
      executionMode: values.executionMode.trim() || null,
      defaultToolIds: parseLineList(values.defaultToolIds),
      allowedCapabilityBundleKeys: parseLineList(values.allowedCapabilityBundleKeys),
      connectorIds: parseLineList(values.connectorIds),
      reviewMode: values.reviewMode.trim() || null,
      approvalPolicyOverrides: parseJsonValue("Approval policy overrides", values.approvalPolicyOverrides, []),
    };
  };

  const handleSave = async () => {
    if (isReadOnly) {
      return;
    }

    try {
      const payload = buildPayload();
      if (isEditing && matchedItem) {
        await updateMutation.mutateAsync({ payload: payload as WorkflowSpecDraftUpdateInput, specId: matchedItem.id });
        toast.success("Studio workflow updated");
        return;
      }

      const created = await createMutation.mutateAsync(payload as WorkflowSpecDraftCreateInput);
      toast.success("Studio workflow created");
      navigate(`/studio/workflows/${created.key}/edit`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to save Studio workflow");
    }
  };

  if (isEditing && (detailQuery.isPending || (!isMissing && !workflow && !detailQuery.isError))) {
    return <div className="p-4 text-sm text-muted-foreground">Loading Studio workflow...</div>;
  }

  if (isMissing || detailQuery.isError) {
    return <div className="p-4 text-sm text-muted-foreground">{detailQuery.error instanceof Error ? detailQuery.error.message : "Studio workflow not found."}</div>;
  }

  return (
    <div className="space-y-4 p-4" data-testid="studio-workflows-editor">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">{isEditing ? "Edit Workflow" : "Create Workflow"}</h1>
          {workflow ? <StudioResourceBadges origin={workflow.origin} status={workflow.status} version={workflow.version} /> : null}
        </div>
        {!isReadOnly ? (
          <Button disabled={isSaving} size="sm" onClick={handleSave}>
            <Save className="mr-1 size-3.5" />
            Save Workflow
          </Button>
        ) : null}
      </div>

      {isReadOnly ? <StudioReadOnlyBanner reason="Seeded workflows are inspectable but cannot be edited here." testId="studio-workflows-readonly-banner" /> : null}

      <Card>
        <CardHeader>
          <CardTitle>Workflow details</CardTitle>
          <CardDescription>Graph definition, mention policy, and capability allowances for this Studio workflow.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="studio-workflow-key">Key</Label>
              <Input id="studio-workflow-key" aria-label="Workflow Key" disabled={isEditing || isReadOnly || isSaving} value={values.key} onChange={(event) => updateValue("key", event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="studio-workflow-name">Name</Label>
              <Input id="studio-workflow-name" aria-label="Workflow Name" disabled={isReadOnly || isSaving} value={values.name} onChange={(event) => updateValue("name", event.target.value)} />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="studio-workflow-execution-mode">Execution Mode</Label>
              <Input id="studio-workflow-execution-mode" aria-label="Execution Mode" disabled={isReadOnly || isSaving} value={values.executionMode} onChange={(event) => updateValue("executionMode", event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="studio-workflow-review-mode">Review Mode</Label>
              <Input id="studio-workflow-review-mode" aria-label="Review Mode" disabled={isReadOnly || isSaving} value={values.reviewMode} onChange={(event) => updateValue("reviewMode", event.target.value)} />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="studio-workflow-graph-definition">Graph Definition JSON</Label>
            <Textarea id="studio-workflow-graph-definition" aria-label="Graph Definition JSON" disabled={isReadOnly || isSaving} rows={10} value={values.graphDefinition} onChange={(event) => updateValue("graphDefinition", event.target.value)} />
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="studio-workflow-final-output-contract">Final Output Contract JSON</Label>
              <Textarea id="studio-workflow-final-output-contract" aria-label="Final Output Contract JSON" disabled={isReadOnly || isSaving} rows={10} value={values.finalOutputContract} onChange={(event) => updateValue("finalOutputContract", event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="studio-workflow-mention-policy">Mention Policy JSON</Label>
              <Textarea id="studio-workflow-mention-policy" aria-label="Mention Policy JSON" disabled={isReadOnly || isSaving} rows={10} value={values.mentionPolicy} onChange={(event) => updateValue("mentionPolicy", event.target.value)} />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="studio-workflow-default-tool-ids">Default Tool Ids</Label>
              <Textarea id="studio-workflow-default-tool-ids" aria-label="Default Tool Ids" disabled={isReadOnly || isSaving} rows={4} value={values.defaultToolIds} onChange={(event) => updateValue("defaultToolIds", event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="studio-workflow-allowed-capability-bundle-keys">Allowed Capability Bundle Keys</Label>
              <Textarea id="studio-workflow-allowed-capability-bundle-keys" aria-label="Allowed Capability Bundle Keys" disabled={isReadOnly || isSaving} rows={4} value={values.allowedCapabilityBundleKeys} onChange={(event) => updateValue("allowedCapabilityBundleKeys", event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="studio-workflow-connector-ids">Connector Ids</Label>
              <Textarea id="studio-workflow-connector-ids" aria-label="Connector Ids" disabled={isReadOnly || isSaving} rows={4} value={values.connectorIds} onChange={(event) => updateValue("connectorIds", event.target.value)} />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="studio-workflow-approval-policy-overrides">Approval Policy Overrides JSON</Label>
            <Textarea id="studio-workflow-approval-policy-overrides" aria-label="Approval Policy Overrides JSON" disabled={isReadOnly || isSaving} rows={8} value={values.approvalPolicyOverrides} onChange={(event) => updateValue("approvalPolicyOverrides", event.target.value)} />
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
