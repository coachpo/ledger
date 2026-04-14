import { useEffect, useState } from "react";
import { Save } from "lucide-react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import {
  useCreateStudioAgentSpec,
  useStudioAgentSpecByKey,
  useUpdateStudioAgentSpec,
} from "@/hooks/use-studio";
import type { AgentSpecDraftCreateInput, AgentSpecDraftUpdateInput } from "@/lib/types/studio";
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
import { Textarea } from "@/components/ui/textarea";

import { StudioReadOnlyBanner, StudioResourceBadges } from "../shared";
import {
  parseJsonValue,
  parseLineList,
  stringifyJson,
  toLineList,
} from "../shared-utils";

type AgentEditorValues = {
  key: string;
  name: string;
  instructions: string;
  modelPolicy: string;
  finalOutputContract: string;
  defaultCapabilityBundleKeys: string;
  defaultPersonaProfileKeys: string;
};

const initialValues: AgentEditorValues = {
  key: "",
  name: "",
  instructions: "",
  modelPolicy: "{}",
  finalOutputContract: "",
  defaultCapabilityBundleKeys: "",
  defaultPersonaProfileKeys: "",
};

export function StudioAgentEditorPage() {
  const { agentKey } = useParams<{ agentKey: string }>();
  const navigate = useNavigate();
  const isEditing = Boolean(agentKey);
  const { detailQuery, isMissing, matchedItem } = useStudioAgentSpecByKey(agentKey);
  const createMutation = useCreateStudioAgentSpec();
  const updateMutation = useUpdateStudioAgentSpec();
  const [values, setValues] = useState<AgentEditorValues>(initialValues);
  const agent = detailQuery.data;
  const isReadOnly = isEditing && agent?.origin !== "managed";
  const isSaving = createMutation.isPending || updateMutation.isPending;

  useEffect(() => {
    if (!agent) {
      return;
    }

    const nextValues = {
      key: agent.key,
      name: agent.name,
      instructions: agent.instructions,
      modelPolicy: stringifyJson(agent.modelPolicy ?? {}),
      finalOutputContract: stringifyJson(agent.finalOutputContract),
      defaultCapabilityBundleKeys: toLineList(agent.defaultCapabilityBundleKeys),
      defaultPersonaProfileKeys: toLineList(agent.defaultPersonaProfileKeys),
    };

    setValues((current) => {
      if (
        current.key === nextValues.key &&
        current.name === nextValues.name &&
        current.instructions === nextValues.instructions &&
        current.modelPolicy === nextValues.modelPolicy &&
        current.finalOutputContract === nextValues.finalOutputContract &&
        current.defaultCapabilityBundleKeys === nextValues.defaultCapabilityBundleKeys &&
        current.defaultPersonaProfileKeys === nextValues.defaultPersonaProfileKeys
      ) {
        return current;
      }

      return nextValues;
    });
  }, [agent]);

  const updateValue = <Key extends keyof AgentEditorValues>(key: Key, value: AgentEditorValues[Key]) => {
    setValues((current) => ({ ...current, [key]: value }));
  };

  const buildPayload = (): AgentSpecDraftCreateInput | AgentSpecDraftUpdateInput => {
    const trimmedKey = values.key.trim().toLowerCase();
    const trimmedName = values.name.trim();
    const trimmedInstructions = values.instructions.trim();

    if (!isEditing && (!trimmedKey || !trimmedName || !trimmedInstructions)) {
      throw new Error("Key, name, and instructions are required.");
    }

    return {
      key: trimmedKey,
      name: trimmedName,
      instructions: trimmedInstructions,
      modelPolicy: parseJsonValue("Model policy", values.modelPolicy, {}),
      finalOutputContract: parseJsonValue("Final output contract", values.finalOutputContract, null),
      defaultCapabilityBundleKeys: parseLineList(values.defaultCapabilityBundleKeys),
      defaultPersonaProfileKeys: parseLineList(values.defaultPersonaProfileKeys),
    };
  };

  const handleSave = async () => {
    if (isReadOnly) {
      return;
    }

    try {
      const payload = buildPayload();

      if (isEditing && matchedItem) {
        await updateMutation.mutateAsync({
          payload: payload as AgentSpecDraftUpdateInput,
          specId: matchedItem.id,
        });
        toast.success("Studio agent updated");
        return;
      }

      const created = await createMutation.mutateAsync(payload as AgentSpecDraftCreateInput);
      toast.success("Studio agent created");
      navigate(`/studio/agents/${created.key}/edit`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to save Studio agent");
    }
  };

  if (isEditing && (detailQuery.isPending || (!isMissing && !agent && !detailQuery.isError))) {
    return <div className="p-4 text-sm text-muted-foreground">Loading Studio agent...</div>;
  }

  if (isMissing || detailQuery.isError) {
    return (
      <div className="space-y-4 p-4">
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            {detailQuery.error instanceof Error ? detailQuery.error.message : "Studio agent not found."}
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-4 p-4" data-testid="studio-agents-editor">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">{isEditing ? "Edit Agent" : "Create Agent"}</h1>
          <p className="text-sm text-muted-foreground">
            Key-based Studio routes resolve through the existing agent catalog while keeping managed resources editable.
          </p>
          {agent ? <StudioResourceBadges origin={agent.origin} status={agent.status} version={agent.version} /> : null}
        </div>
        {!isReadOnly ? (
          <Button data-testid="studio-agents-save" disabled={isSaving} size="sm" onClick={handleSave}>
            <Save className="mr-1 size-3.5" />
            Save Agent
          </Button>
        ) : null}
      </div>

      {isReadOnly ? (
        <StudioReadOnlyBanner
          reason="Seeded Studio agents are inspectable but cannot be edited here."
          testId="studio-agents-readonly-banner"
        />
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Agent details</CardTitle>
          <CardDescription>Instructions, default bundle references, and JSON policy settings for this Studio agent.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="studio-agent-key">Key</Label>
              <Input
                id="studio-agent-key"
                aria-label="Agent Key"
                disabled={isEditing || isReadOnly || isSaving}
                onChange={(event) => updateValue("key", event.target.value)}
                value={values.key}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="studio-agent-name">Name</Label>
              <Input
                id="studio-agent-name"
                aria-label="Agent Name"
                disabled={isReadOnly || isSaving}
                onChange={(event) => updateValue("name", event.target.value)}
                value={values.name}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="studio-agent-instructions">Instructions</Label>
            <Textarea
              id="studio-agent-instructions"
              aria-label="Agent Instructions"
              disabled={isReadOnly || isSaving}
              onChange={(event) => updateValue("instructions", event.target.value)}
              rows={10}
              value={values.instructions}
            />
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="studio-agent-default-capability-bundle-keys">Default Capability Bundle Keys</Label>
              <Textarea
                id="studio-agent-default-capability-bundle-keys"
                aria-label="Default Capability Bundle Keys"
                disabled={isReadOnly || isSaving}
                onChange={(event) => updateValue("defaultCapabilityBundleKeys", event.target.value)}
                rows={4}
                value={values.defaultCapabilityBundleKeys}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="studio-agent-default-persona-profile-keys">Default Persona Profile Keys</Label>
              <Textarea
                id="studio-agent-default-persona-profile-keys"
                aria-label="Default Persona Profile Keys"
                disabled={isReadOnly || isSaving}
                onChange={(event) => updateValue("defaultPersonaProfileKeys", event.target.value)}
                rows={4}
                value={values.defaultPersonaProfileKeys}
              />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="studio-agent-model-policy">Model Policy JSON</Label>
              <Textarea
                id="studio-agent-model-policy"
                aria-label="Model Policy JSON"
                disabled={isReadOnly || isSaving}
                onChange={(event) => updateValue("modelPolicy", event.target.value)}
                rows={10}
                value={values.modelPolicy}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="studio-agent-final-output-contract">Final Output Contract JSON</Label>
              <Textarea
                id="studio-agent-final-output-contract"
                aria-label="Final Output Contract JSON"
                disabled={isReadOnly || isSaving}
                onChange={(event) => updateValue("finalOutputContract", event.target.value)}
                rows={10}
                value={values.finalOutputContract}
              />
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
