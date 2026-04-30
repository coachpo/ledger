import { useEffect, useMemo, useState } from "react";
import { Save } from "lucide-react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { ExactJsonPreview } from "@/components/platform-authoring/inspectors/exact-json-preview";
import { useActivateCapability, useCapability, useCreateCapability, useUpdateCapability } from "@/hooks/use-capabilities";
import type { CapabilityCreateInput, CapabilityUpdateInput } from "@/lib/types/capability";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

import { parseLineList, parseRequiredText, PlatformResourceBadges, stringifyJson } from "../platform-resource-shared";

type CapabilityEditorValues = {
  description: string;
  key: string;
  name: string;
  toolGrants: string;
};

const initialValues: CapabilityEditorValues = {
  description: "",
  key: "",
  name: "",
  toolGrants: "",
};

export function CapabilitiesEditorPage() {
  const { capabilityId } = useParams<{ capabilityId: string }>();
  const navigate = useNavigate();
  const isEditing = Boolean(capabilityId);
  const capabilityQuery = useCapability(capabilityId);
  const createMutation = useCreateCapability();
  const updateMutation = useUpdateCapability();
  const activateMutation = useActivateCapability();
  const [values, setValues] = useState<CapabilityEditorValues>(initialValues);

  useEffect(() => {
    if (!capabilityQuery.data) {
      return;
    }

    setValues({
      description: capabilityQuery.data.description ?? "",
      key: capabilityQuery.data.key,
      name: capabilityQuery.data.name,
      toolGrants: capabilityQuery.data.toolGrants.map((grant) => grant.tool).join("\n"),
    });
  }, [capabilityQuery.data]);

  const isSaving = createMutation.isPending || updateMutation.isPending;
  const isBusy = isSaving || activateMutation.isPending;
  const canActivate = Boolean(isEditing && capabilityQuery.data?.status === "draft");
  const serializedToolGrants = useMemo(
    () =>
      stringifyJson(
        parseLineList(values.toolGrants).map((tool) => ({ tool })),
      ),
    [values.toolGrants],
  );

  const updateValue = <Key extends keyof CapabilityEditorValues>(key: Key, value: CapabilityEditorValues[Key]) => {
    setValues((current) => ({ ...current, [key]: value }));
  };

  const buildPayload = (): CapabilityCreateInput | CapabilityUpdateInput => {
    const tools = parseLineList(values.toolGrants);
    if (tools.length === 0) {
      throw new Error("At least one tool grant is required.");
    }

    return {
      description: values.description.trim() || undefined,
      key: parseRequiredText("Key", values.key).toLowerCase(),
      name: parseRequiredText("Name", values.name),
      toolGrants: tools.map((tool) => ({ tool })),
    };
  };

  const handleSave = async () => {
    try {
      const payload = buildPayload();

      if (isEditing && capabilityId) {
        const { key: _ignored, ...updatePayload } = payload as CapabilityCreateInput;
        const updated = await updateMutation.mutateAsync({ payload: updatePayload, capabilityId });
        toast.success("Capability updated");
        navigate(`/capabilities/${updated.id}/edit`);
        return;
      }

      const created = await createMutation.mutateAsync(payload as CapabilityCreateInput);
      toast.success("Capability created");
      navigate(`/capabilities/${created.id}/edit`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to save capability");
    }
  };

  const handleActivate = async () => {
    if (!capabilityId) {
      return;
    }

    try {
      await activateMutation.mutateAsync(capabilityId);
      toast.success("Capability activated");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to activate capability");
    }
  };

  if (isEditing && capabilityQuery.isPending) {
    return <div className="p-4 text-sm text-muted-foreground">Loading capability details...</div>;
  }

  if (isEditing && capabilityQuery.isError) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        {capabilityQuery.error instanceof Error ? capabilityQuery.error.message : "Capability not found."}
      </div>
    );
  }

  return (
    <div className="space-y-4 p-4" data-testid="capabilities-editor">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">
            {isEditing ? "Edit Capability" : "Create Capability"}
          </h1>
          <p className="text-sm text-muted-foreground">
            Define a reusable capability and the tool identifiers it grants to agents.
          </p>
          {capabilityQuery.data ? (
            <PlatformResourceBadges status={capabilityQuery.data.status} version={capabilityQuery.data.version} />
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          {canActivate ? (
            <Button data-testid="capabilities-activate" disabled={isBusy} size="sm" variant="outline" onClick={() => void handleActivate()}>
              Activate Capability
            </Button>
          ) : null}
          <Button disabled={isSaving} size="sm" onClick={handleSave}>
            <Save data-icon="inline-start" />
            Save Capability
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Capability details</CardTitle>
          <CardDescription>
            Keys are immutable after creation. Tool grants accept one tool id per line.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="capability-key">Key</Label>
              <Input
                id="capability-key"
                aria-label="Key"
                disabled={isEditing || isSaving}
                value={values.key}
                onChange={(event) => updateValue("key", event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="capability-name">Name</Label>
              <Input
                id="capability-name"
                aria-label="Name"
                disabled={isSaving}
                value={values.name}
                onChange={(event) => updateValue("name", event.target.value)}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="capability-description">Description</Label>
            <Textarea
              id="capability-description"
              aria-label="Description"
              disabled={isSaving}
              rows={4}
              value={values.description}
              onChange={(event) => updateValue("description", event.target.value)}
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="capability-tool-grants">Tool Grants</Label>
              <Textarea
                id="capability-tool-grants"
                aria-label="Tool Grants"
                disabled={isSaving}
                rows={8}
                value={values.toolGrants}
                onChange={(event) => updateValue("toolGrants", event.target.value)}
              />
              <p className="text-sm text-muted-foreground">Add one tool id per line.</p>
            </div>
            <div className="space-y-2">
              <Label>Exact Tool Grants JSON</Label>
              <ExactJsonPreview
                ariaLabel="Exact tool grants JSON"
                data-testid="capabilities-tool-grants-json-preview"
                value={serializedToolGrants}
              />
              <p className="text-sm text-muted-foreground">
                Read-only preview of the exact JSON array saved from the current tool-grant lines.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
