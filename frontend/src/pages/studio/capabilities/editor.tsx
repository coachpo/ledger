import { useEffect, useState } from "react";
import { Save } from "lucide-react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import {
  useCreateStudioCapability,
  useStudioCapabilityByKey,
  useUpdateStudioCapability,
} from "@/hooks/use-studio";
import type {
  CapabilityRegistryEntryDraftCreateInput,
  CapabilityRegistryEntryDraftUpdateInput,
} from "@/lib/types/studio";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

import { StudioReadOnlyBanner, StudioResourceBadges } from "../shared";
import { parseJsonValue, stringifyJson } from "../shared-utils";

type CapabilityEditorValues = {
  key: string;
  type: "tool" | "connector" | "bundle";
  displayName: string;
  description: string;
  approvalMode: "not_required" | "required";
  adapterKey: string;
  configSchema: string;
  bundleMembers: string;
  transport: string;
  lifecycle: string;
};

const initialValues: CapabilityEditorValues = {
  key: "",
  type: "tool",
  displayName: "",
  description: "",
  approvalMode: "not_required",
  adapterKey: "",
  configSchema: "",
  bundleMembers: "",
  transport: "",
  lifecycle: "",
};

export function StudioCapabilityEditorPage() {
  const { capabilityKey } = useParams<{ capabilityKey: string }>();
  const navigate = useNavigate();
  const isEditing = Boolean(capabilityKey);
  const { detailQuery, isMissing, matchedItem } = useStudioCapabilityByKey(capabilityKey);
  const createMutation = useCreateStudioCapability();
  const updateMutation = useUpdateStudioCapability();
  const capability = detailQuery.data;
  const isReadOnly = isEditing && capability?.origin !== "managed";
  const isSaving = createMutation.isPending || updateMutation.isPending;
  const [values, setValues] = useState<CapabilityEditorValues>(initialValues);

  useEffect(() => {
    if (!capability) {
      return;
    }

    const nextValues = {
      key: capability.key,
      type: capability.type,
      displayName: capability.displayName,
      description: capability.description,
      approvalMode: capability.approvalMode,
      adapterKey: capability.adapterKey ?? "",
      configSchema: stringifyJson(capability.configSchema),
      bundleMembers: stringifyJson(capability.bundleMembers),
      transport: capability.transport ?? "",
      lifecycle: capability.lifecycle ?? "",
    };

    setValues((current) => {
      if (
        current.key === nextValues.key &&
        current.type === nextValues.type &&
        current.displayName === nextValues.displayName &&
        current.description === nextValues.description &&
        current.approvalMode === nextValues.approvalMode &&
        current.adapterKey === nextValues.adapterKey &&
        current.configSchema === nextValues.configSchema &&
        current.bundleMembers === nextValues.bundleMembers &&
        current.transport === nextValues.transport &&
        current.lifecycle === nextValues.lifecycle
      ) {
        return current;
      }

      return nextValues;
    });
  }, [capability]);

  const updateValue = <Key extends keyof CapabilityEditorValues>(key: Key, value: CapabilityEditorValues[Key]) => {
    setValues((current) => ({ ...current, [key]: value }));
  };

  const buildPayload = (): CapabilityRegistryEntryDraftCreateInput | CapabilityRegistryEntryDraftUpdateInput => {
    const key = values.key.trim().toLowerCase();
    const displayName = values.displayName.trim();
    const description = values.description.trim();

    if (!isEditing && (!key || !displayName || !description)) {
      throw new Error("Key, display name, and description are required.");
    }

    return {
      key,
      type: values.type,
      displayName,
      description,
      approvalMode: values.approvalMode,
      adapterKey: values.adapterKey.trim() || null,
      configSchema: parseJsonValue("Config schema", values.configSchema, null),
      bundleMembers: parseJsonValue("Bundle members", values.bundleMembers, null),
      transport: values.transport.trim() || null,
      lifecycle: values.lifecycle.trim() || null,
    };
  };

  const handleSave = async () => {
    if (isReadOnly) {
      return;
    }

    try {
      const payload = buildPayload();
      if (isEditing && matchedItem) {
        await updateMutation.mutateAsync({ payload: payload as CapabilityRegistryEntryDraftUpdateInput, specId: matchedItem.id });
        toast.success("Studio capability updated");
        return;
      }

      const created = await createMutation.mutateAsync(payload as CapabilityRegistryEntryDraftCreateInput);
      toast.success("Studio capability created");
      navigate(`/studio/capabilities/${created.key}/edit`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to save Studio capability");
    }
  };

  if (isEditing && (detailQuery.isPending || (!isMissing && !capability && !detailQuery.isError))) {
    return <div className="p-4 text-sm text-muted-foreground">Loading Studio capability...</div>;
  }

  if (isMissing || detailQuery.isError) {
    return <div className="p-4 text-sm text-muted-foreground">{detailQuery.error instanceof Error ? detailQuery.error.message : "Studio capability not found."}</div>;
  }

  return (
    <div className="space-y-4 p-4" data-testid="studio-capabilities-editor">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">{isEditing ? "Edit Capability" : "Create Capability"}</h1>
          {capability ? <StudioResourceBadges origin={capability.origin} status={capability.status} version={capability.version} /> : null}
        </div>
        {!isReadOnly ? (
          <Button disabled={isSaving} size="sm" onClick={handleSave}>
            <Save className="mr-1 size-3.5" />
            Save Capability
          </Button>
        ) : null}
      </div>

      {isReadOnly ? <StudioReadOnlyBanner reason="Seeded capabilities are inspectable but cannot be edited here." testId="studio-capabilities-readonly-banner" /> : null}

      <Card>
        <CardHeader>
          <CardTitle>Capability details</CardTitle>
          <CardDescription>Capability transport, bundle members, and approval configuration for Studio execution.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="studio-capability-key">Key</Label>
              <Input id="studio-capability-key" aria-label="Capability Key" disabled={isEditing || isReadOnly || isSaving} value={values.key} onChange={(event) => updateValue("key", event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="studio-capability-display-name">Display Name</Label>
              <Input id="studio-capability-display-name" aria-label="Capability Display Name" disabled={isReadOnly || isSaving} value={values.displayName} onChange={(event) => updateValue("displayName", event.target.value)} />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="studio-capability-type">Type</Label>
              <select id="studio-capability-type" aria-label="Capability Type" className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm" disabled={isReadOnly || isSaving} value={values.type} onChange={(event) => updateValue("type", event.target.value as CapabilityEditorValues["type"])}>
                <option value="tool">Tool</option>
                <option value="connector">Connector</option>
                <option value="bundle">Bundle</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="studio-capability-approval-mode">Approval Mode</Label>
              <select id="studio-capability-approval-mode" aria-label="Approval Mode" className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm" disabled={isReadOnly || isSaving} value={values.approvalMode} onChange={(event) => updateValue("approvalMode", event.target.value as CapabilityEditorValues["approvalMode"])}>
                <option value="not_required">Not required</option>
                <option value="required">Required</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="studio-capability-adapter-key">Adapter Key</Label>
              <Input id="studio-capability-adapter-key" aria-label="Adapter Key" disabled={isReadOnly || isSaving} value={values.adapterKey} onChange={(event) => updateValue("adapterKey", event.target.value)} />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="studio-capability-description">Description</Label>
            <Textarea id="studio-capability-description" aria-label="Capability Description" disabled={isReadOnly || isSaving} rows={5} value={values.description} onChange={(event) => updateValue("description", event.target.value)} />
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="studio-capability-config-schema">Config Schema JSON</Label>
              <Textarea id="studio-capability-config-schema" aria-label="Config Schema JSON" disabled={isReadOnly || isSaving} rows={10} value={values.configSchema} onChange={(event) => updateValue("configSchema", event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="studio-capability-bundle-members">Bundle Members JSON</Label>
              <Textarea id="studio-capability-bundle-members" aria-label="Bundle Members JSON" disabled={isReadOnly || isSaving} rows={10} value={values.bundleMembers} onChange={(event) => updateValue("bundleMembers", event.target.value)} />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="studio-capability-transport">Transport</Label>
              <Input id="studio-capability-transport" aria-label="Transport" disabled={isReadOnly || isSaving} value={values.transport} onChange={(event) => updateValue("transport", event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="studio-capability-lifecycle">Lifecycle</Label>
              <Input id="studio-capability-lifecycle" aria-label="Lifecycle" disabled={isReadOnly || isSaving} value={values.lifecycle} onChange={(event) => updateValue("lifecycle", event.target.value)} />
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
