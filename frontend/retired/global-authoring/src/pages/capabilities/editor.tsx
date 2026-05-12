import { useEffect, useMemo, useState } from "react";
import { AlertCircle, Save } from "lucide-react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { ExactJsonPreview } from "@/components/platform-authoring/inspectors/exact-json-preview";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  useActivateCapability,
  useCapability,
  useCapabilityTools,
  useCreateCapability,
  useUpdateCapability,
} from "@/hooks/use-capabilities";
import type { CapabilityCreateInput, CapabilityToolRead, CapabilityUpdateInput } from "@/lib/types/capability";

import { parseRequiredText, stringifyJson } from "@/pages/platform-resource-helpers";

import { PlatformResourceBadges } from "../platform-resource-shared";

type CapabilityEditorValues = {
  description: string;
  key: string;
  name: string;
};

const initialValues: CapabilityEditorValues = {
  description: "",
  key: "",
  name: "",
};

const EMPTY_CAPABILITY_TOOLS: CapabilityToolRead[] = [];

function filterCatalogTools(tools: CapabilityToolRead[], searchTerm: string) {
  const normalizedSearchTerm = searchTerm.trim().toLowerCase();

  if (!normalizedSearchTerm) {
    return tools;
  }

  return tools.filter((tool) => {
    const searchableText = `${tool.displayName} ${tool.key} ${tool.description}`.toLowerCase();

    return searchableText.includes(normalizedSearchTerm);
  });
}

export function CapabilitiesEditorPage() {
  const { capabilityId } = useParams<{ capabilityId: string }>();
  const navigate = useNavigate();
  const isEditing = Boolean(capabilityId);
  const capabilityQuery = useCapability(capabilityId);
  const toolsQuery = useCapabilityTools();
  const createMutation = useCreateCapability();
  const updateMutation = useUpdateCapability();
  const activateMutation = useActivateCapability();
  const [values, setValues] = useState<CapabilityEditorValues>(initialValues);
  const [selectedToolKeys, setSelectedToolKeys] = useState<string[]>([]);
  const [toolSearch, setToolSearch] = useState("");

  useEffect(() => {
    if (!capabilityQuery.data) {
      return;
    }

    setValues({
      description: capabilityQuery.data.description ?? "",
      key: capabilityQuery.data.key,
      name: capabilityQuery.data.name,
    });
    setSelectedToolKeys(capabilityQuery.data.toolKeys);
  }, [capabilityQuery.data]);
  const catalogTools = toolsQuery.data?.items ?? EMPTY_CAPABILITY_TOOLS;
  const catalogToolKeys = useMemo(() => new Set(catalogTools.map((tool) => tool.key)), [catalogTools]);
  const filteredCatalogTools = useMemo(() => filterCatalogTools(catalogTools, toolSearch), [catalogTools, toolSearch]);
  const missingSelectedToolKeys = useMemo(
    () => selectedToolKeys.filter((toolKey) => !catalogToolKeys.has(toolKey)),
    [catalogToolKeys, selectedToolKeys],
  );
  const selectedCatalogToolKeys = useMemo(
    () => catalogTools.filter((tool) => selectedToolKeys.includes(tool.key)).map((tool) => tool.key),
    [catalogTools, selectedToolKeys],
  );
  const previewPayload = useMemo(
    () =>
      stringifyJson({
        description: values.description.trim() || undefined,
        key: values.key.trim().toLowerCase(),
        name: values.name.trim(),
        toolKeys: selectedCatalogToolKeys,
      }),
    [selectedCatalogToolKeys, values.description, values.key, values.name],
  );

  const isSaving = createMutation.isPending || updateMutation.isPending;
  const isBusy = isSaving || activateMutation.isPending;
  const hasMissingSelectedTools = missingSelectedToolKeys.length > 0;
  const hasNoSelectedCatalogTools = !toolsQuery.isPending && !toolsQuery.isError && selectedCatalogToolKeys.length === 0;
  const canActivate = Boolean(isEditing && capabilityQuery.data?.status === "draft");
  const isSaveDisabled = isSaving || toolsQuery.isPending || toolsQuery.isError || hasMissingSelectedTools || hasNoSelectedCatalogTools;

  const updateValue = <Key extends keyof CapabilityEditorValues>(key: Key, value: CapabilityEditorValues[Key]) => {
    setValues((current) => ({ ...current, [key]: value }));
  };

  const updateSelectedToolKey = (toolKey: string, checked: boolean) => {
    setSelectedToolKeys((current) => (checked ? [...current, toolKey] : current.filter((selectedKey) => selectedKey !== toolKey)));
  };
  const buildPayload = (): CapabilityCreateInput | CapabilityUpdateInput => {
    if (toolsQuery.isError) {
      throw new Error("Capability tool catalog failed to load. Refresh and try again.");
    }

    if (hasMissingSelectedTools) {
      throw new Error(`Selected tool keys are no longer in the catalog: ${missingSelectedToolKeys.join(", ")}.`);
    }

    if (selectedCatalogToolKeys.length === 0) {
      throw new Error("Select at least one catalog tool.");
    }

    return {
      description: values.description.trim() || undefined,
      key: parseRequiredText("Key", values.key).toLowerCase(),
      name: parseRequiredText("Name", values.name),
      toolKeys: selectedCatalogToolKeys,
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
            Define a reusable capability by selecting the catalog tools it grants to agents.
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
          <Button disabled={isSaveDisabled} size="sm" onClick={handleSave}>
            <Save data-icon="inline-start" />
            Save Capability
          </Button>
        </div>
      </div>

      {toolsQuery.isError ? (
        <Alert data-testid="capability-tool-catalog-error" variant="destructive">
          <AlertCircle />
          <AlertTitle>Tool catalog unavailable</AlertTitle>
          <AlertDescription>
            {toolsQuery.error instanceof Error ? toolsQuery.error.message : "Capability tool catalog failed to load. Refresh and try again."}
          </AlertDescription>
        </Alert>
      ) : null}

      {hasMissingSelectedTools ? (
        <Alert data-testid="capability-stale-tool-keys" variant="destructive">
          <AlertCircle />
          <AlertTitle>Selected tools are no longer available</AlertTitle>
          <AlertDescription>{`Missing catalog key(s): ${missingSelectedToolKeys.join(", ")}.`}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Capability details</CardTitle>
          <CardDescription>
            Keys are immutable after creation. Tool access is limited to the fetched server catalog.
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
            <div className="space-y-3">
              <div className="space-y-2">
                <Label htmlFor="capability-tool-search">Catalog tools</Label>
                <Input
                  id="capability-tool-search"
                  aria-label="Search catalog tools"
                  disabled={toolsQuery.isPending || toolsQuery.isError}
                  placeholder="Search by tool name, key, or description"
                  value={toolSearch}
                  onChange={(event) => setToolSearch(event.target.value)}
                />
                <p className="text-sm text-muted-foreground">
                  Select one or more server-declared tools. Arbitrary tool ids cannot be typed or saved.
                </p>
              </div>

              {toolsQuery.isPending ? (
                <div className="rounded-md border bg-muted/30 p-4 text-sm text-muted-foreground">Loading catalog tools...</div>
              ) : null}

              {!toolsQuery.isPending && !toolsQuery.isError && filteredCatalogTools.length === 0 ? (
                <div className="rounded-md border bg-muted/30 p-4 text-sm text-muted-foreground">No catalog tools match the current search.</div>
              ) : null}

              {!toolsQuery.isPending && !toolsQuery.isError && filteredCatalogTools.length > 0 ? (
                <div className="grid gap-2" data-testid="capability-tool-catalog">
                  {filteredCatalogTools.map((tool) => (
                    <label
                      key={tool.key}
                      className="flex cursor-pointer items-start gap-3 rounded-md border bg-card p-3 transition-colors hover:bg-accent/50"
                    >
                      <Checkbox
                        aria-label={`Select ${tool.displayName}`}
                        checked={selectedToolKeys.includes(tool.key)}
                        disabled={isSaving}
                        onCheckedChange={(checked) => updateSelectedToolKey(tool.key, checked === true)}
                      />
                      <span className="grid min-w-0 gap-1">
                        <span className="text-sm font-medium leading-5 text-foreground">{tool.displayName}</span>
                        <span className="break-all text-xs text-muted-foreground">{tool.key}</span>
                        <span className="text-sm text-muted-foreground">{tool.description}</span>
                      </span>
                    </label>
                  ))}
                </div>
              ) : null}

              {hasNoSelectedCatalogTools ? (
                <div className="rounded-md border border-destructive bg-card p-3 text-sm text-destructive" data-testid="capability-empty-tool-selection">
                  Select at least one catalog tool before saving.
                </div>
              ) : null}

              {missingSelectedToolKeys.length > 0 ? (
                <div className="rounded-md border border-destructive bg-card p-3 text-sm text-destructive">
                  Missing catalog key(s): {missingSelectedToolKeys.join(", ")}
                </div>
              ) : null}
            </div>

            <div className="space-y-2">
              <Label>Exact Capability Payload JSON</Label>
              <ExactJsonPreview
                ariaLabel="Exact capability payload JSON"
                data-testid="capabilities-payload-json-preview"
                value={previewPayload}
              />
              <p className="text-sm text-muted-foreground">
                Read-only preview of the exact outgoing payload shape. Saved tools are sent as <code>toolKeys</code> only.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
