import { useEffect, useState } from "react";
import { Archive, Check, FilePlus2, Save, Slash } from "lucide-react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import {
  useActivateStudioPersona,
  useArchiveStudioPersona,
  useCreateStudioPersona,
  useDeprecateStudioPersona,
  useStudioPersonaByKey,
  useStudioPersonaVersions,
  useUpdateStudioPersona,
} from "@/hooks/use-studio";
import type {
  PersonaProfileDraftCreateInput,
  PersonaProfileDraftUpdateInput,
} from "@/lib/types/studio";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

import { StudioReadOnlyBanner, StudioResourceBadges } from "../shared";
import { formatKindLabel, toLineList, parseLineList } from "../shared-utils";

type PersonaEditorValues = {
  defaultCapabilityBundleKeys: string;
  displayName: string;
  enabled: boolean;
  handle: string;
  key: string;
  promptAppendFragment: string;
  systemPromptFragment: string;
};

const initialValues: PersonaEditorValues = {
  defaultCapabilityBundleKeys: "",
  displayName: "",
  enabled: true,
  handle: "",
  key: "",
  promptAppendFragment: "",
  systemPromptFragment: "",
};

export function StudioPersonaEditorPage() {
  const { personaKey } = useParams<{ personaKey: string }>();
  const navigate = useNavigate();
  const isEditing = Boolean(personaKey);
  const { detailQuery, isMissing } = useStudioPersonaByKey(personaKey);
  const versionsQuery = useStudioPersonaVersions(personaKey);
  const createMutation = useCreateStudioPersona();
  const updateMutation = useUpdateStudioPersona();
  const activateMutation = useActivateStudioPersona();
  const deprecateMutation = useDeprecateStudioPersona();
  const archiveMutation = useArchiveStudioPersona();
  const [values, setValues] = useState<PersonaEditorValues>(initialValues);
  const persona = detailQuery.data;
  const isManaged = persona?.origin === "managed";
  const isDraft = persona?.status === "DRAFT";
  const isEditableDraft = !isEditing || Boolean(isManaged && isDraft);
  const isReadOnly = Boolean(isEditing && !isEditableDraft);
  const isBusy =
    createMutation.isPending ||
    updateMutation.isPending ||
    activateMutation.isPending ||
    deprecateMutation.isPending ||
    archiveMutation.isPending;
  const canCreateDraft = Boolean(isEditing && isManaged && persona && persona.status !== "DRAFT");
  const canActivate = Boolean(persona && isManaged && persona.status === "DRAFT");
  const canDeprecate = Boolean(persona && isManaged && persona.status === "ACTIVE");
  const canArchive = Boolean(
    persona && isManaged && (persona.status === "DRAFT" || persona.status === "DEPRECATED"),
  );

  useEffect(() => {
    if (!persona) {
      return;
    }

    const nextValues = {
      defaultCapabilityBundleKeys: toLineList(persona.defaultCapabilityBundleKeys),
      displayName: persona.displayName,
      enabled: persona.enabled,
      handle: persona.handle ?? "",
      key: persona.key,
      promptAppendFragment: persona.promptAppendFragment,
      systemPromptFragment: persona.systemPromptFragment,
    };

    setValues((current) => {
      if (
        current.defaultCapabilityBundleKeys === nextValues.defaultCapabilityBundleKeys &&
        current.displayName === nextValues.displayName &&
        current.enabled === nextValues.enabled &&
        current.handle === nextValues.handle &&
        current.key === nextValues.key &&
        current.promptAppendFragment === nextValues.promptAppendFragment &&
        current.systemPromptFragment === nextValues.systemPromptFragment
      ) {
        return current;
      }

      return nextValues;
    });
  }, [persona]);

  const updateValue = <Key extends keyof PersonaEditorValues>(
    key: Key,
    value: PersonaEditorValues[Key],
  ) => {
    setValues((current) => ({ ...current, [key]: value }));
  };

  const buildCreatePayload = (): PersonaProfileDraftCreateInput => {
    const key = values.key.trim().toLowerCase();
    const displayName = values.displayName.trim();

    if (!key || !displayName) {
      throw new Error("Key and display name are required.");
    }

    return {
      defaultCapabilityBundleKeys: parseLineList(values.defaultCapabilityBundleKeys),
      displayName,
      enabled: values.enabled,
      handle: values.handle.trim() || null,
      key,
      promptAppendFragment: values.promptAppendFragment,
      systemPromptFragment: values.systemPromptFragment,
    };
  };

  const buildUpdatePayload = (): PersonaProfileDraftUpdateInput => ({
    defaultCapabilityBundleKeys: parseLineList(values.defaultCapabilityBundleKeys),
    displayName: values.displayName.trim(),
    enabled: values.enabled,
    handle: values.handle.trim() || null,
    promptAppendFragment: values.promptAppendFragment,
    systemPromptFragment: values.systemPromptFragment,
  });

  const handleSave = async () => {
    try {
      if (isEditing && persona) {
        await updateMutation.mutateAsync({
          payload: buildUpdatePayload(),
          personaKey: persona.key,
          version: persona.version,
        });
        toast.success("Studio persona updated");
        return;
      }

      const created = await createMutation.mutateAsync(buildCreatePayload());
      toast.success("Studio persona draft created");
      navigate(`/studio/personas/${created.key}/edit`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to save Studio persona");
    }
  };

  const handleCreateDraft = async () => {
    try {
      const created = await createMutation.mutateAsync(buildCreatePayload());
      toast.success(`Created draft v${created.version} for ${created.key}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to create persona draft");
    }
  };

  const handleActivate = async () => {
    if (!persona) {
      return;
    }

    try {
      await activateMutation.mutateAsync({ personaKey: persona.key, version: persona.version });
      toast.success(`Activated ${persona.key} v${persona.version}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to activate Studio persona");
    }
  };

  const handleDeprecate = async () => {
    if (!persona) {
      return;
    }

    try {
      await deprecateMutation.mutateAsync({ personaKey: persona.key, version: persona.version });
      toast.success(`Deprecated ${persona.key} v${persona.version}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to deprecate Studio persona");
    }
  };

  const handleArchive = async () => {
    if (!persona) {
      return;
    }

    try {
      await archiveMutation.mutateAsync({ personaKey: persona.key, version: persona.version });
      toast.success(`Archived ${persona.key} v${persona.version}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to archive Studio persona");
    }
  };

  if (isEditing && (detailQuery.isPending || (!isMissing && !persona && !detailQuery.isError))) {
    return <div className="p-4 text-sm text-muted-foreground">Loading Studio persona...</div>;
  }

  if (isMissing || detailQuery.isError) {
    return (
      <div className="space-y-4 p-4">
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            {detailQuery.error instanceof Error ? detailQuery.error.message : "Studio persona not found."}
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-4 p-4" data-testid="studio-personas-editor">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">
            {isEditing ? (isEditableDraft ? "Edit Persona Draft" : "Inspect Persona") : "Create Persona"}
          </h1>
          <p className="text-sm text-muted-foreground">
            Managed personas can be drafted, updated, and promoted in Studio. Imported and seeded
            personas remain read-only historical projections.
          </p>
          {persona ? (
            <StudioResourceBadges
              origin={persona.origin}
              status={persona.status}
              version={persona.version}
              extra={<Badge variant="outline">{formatKindLabel(persona.kind)}</Badge>}
            />
          ) : null}
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          {canCreateDraft ? (
            <Button
              data-testid="studio-personas-create-draft"
              disabled={isBusy}
              onClick={handleCreateDraft}
              size="sm"
              variant="outline"
            >
              <FilePlus2 className="mr-1 size-3.5" />
              Create Draft
            </Button>
          ) : null}
          {isEditableDraft ? (
            <Button
              data-testid="studio-personas-save"
              disabled={isBusy}
              onClick={handleSave}
              size="sm"
            >
              <Save className="mr-1 size-3.5" />
              Save Persona
            </Button>
          ) : null}
          {canActivate ? (
            <Button
              data-testid="studio-personas-activate"
              disabled={isBusy}
              onClick={handleActivate}
              size="sm"
              variant="secondary"
            >
              <Check className="mr-1 size-3.5" />
              Activate
            </Button>
          ) : null}
          {canDeprecate ? (
            <Button
              data-testid="studio-personas-deprecate"
              disabled={isBusy}
              onClick={handleDeprecate}
              size="sm"
              variant="secondary"
            >
              <Slash className="mr-1 size-3.5" />
              Deprecate
            </Button>
          ) : null}
          {canArchive ? (
            <Button
              data-testid="studio-personas-archive"
              disabled={isBusy}
              onClick={handleArchive}
              size="sm"
              variant="outline"
            >
              <Archive className="mr-1 size-3.5" />
              Archive
            </Button>
          ) : null}
        </div>
      </div>

      {isReadOnly ? (
        <StudioReadOnlyBanner
          reason={
            persona?.origin !== "managed"
              ? "Imported and seeded personas are inspectable but remain read-only in Studio."
              : "Only draft managed personas are editable. Create a new draft to make changes to this managed persona."
          }
          testId="studio-personas-readonly-banner"
        />
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Persona details</CardTitle>
          <CardDescription>
            Managed persona prompts and bundle hints live here. Canonical targets stay stable and
            are derived from the persona key.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="studio-persona-key">Key</Label>
              <Input
                aria-label="Persona Key"
                disabled={isEditing || isReadOnly || isBusy}
                id="studio-persona-key"
                onChange={(event) => updateValue("key", event.target.value)}
                value={values.key}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="studio-persona-display-name">Display Name</Label>
              <Input
                aria-label="Persona Display Name"
                disabled={isReadOnly || isBusy}
                id="studio-persona-display-name"
                onChange={(event) => updateValue("displayName", event.target.value)}
                value={values.displayName}
              />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="studio-persona-handle">Handle</Label>
              <Input
                aria-label="Persona Handle"
                disabled={isReadOnly || isBusy}
                id="studio-persona-handle"
                onChange={(event) => updateValue("handle", event.target.value)}
                value={values.handle}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="studio-persona-canonical-target">Canonical Target</Label>
              <Input
                aria-label="Canonical Target"
                disabled
                id="studio-persona-canonical-target"
                value={persona?.canonicalTargetId ?? (values.key ? `persona:${values.key.trim().toLowerCase()}` : "")}
              />
            </div>
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              checked={values.enabled}
              disabled={isReadOnly || isBusy}
              onChange={(event) => updateValue("enabled", event.target.checked)}
              type="checkbox"
            />
            <span>Enabled</span>
          </label>

          <div className="space-y-2">
            <Label htmlFor="studio-persona-default-capability-bundle-keys">
              Default Capability Bundle Keys
            </Label>
            <Textarea
              aria-label="Default Capability Bundle Keys"
              disabled={isReadOnly || isBusy}
              id="studio-persona-default-capability-bundle-keys"
              onChange={(event) => updateValue("defaultCapabilityBundleKeys", event.target.value)}
              rows={4}
              value={values.defaultCapabilityBundleKeys}
            />
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="studio-persona-system-prompt-fragment">System Prompt Fragment</Label>
              <Textarea
                aria-label="System Prompt Fragment"
                disabled={isReadOnly || isBusy}
                id="studio-persona-system-prompt-fragment"
                onChange={(event) => updateValue("systemPromptFragment", event.target.value)}
                rows={8}
                value={values.systemPromptFragment}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="studio-persona-prompt-append-fragment">Prompt Append Fragment</Label>
              <Textarea
                aria-label="Prompt Append Fragment"
                disabled={isReadOnly || isBusy}
                id="studio-persona-prompt-append-fragment"
                onChange={(event) => updateValue("promptAppendFragment", event.target.value)}
                rows={8}
                value={values.promptAppendFragment}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {isEditing ? (
        <Card>
          <CardHeader>
            <CardTitle>Version history</CardTitle>
            <CardDescription>
              Latest persona versions are listed here so managed lifecycle changes stay visible.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2" data-testid="studio-personas-versions">
            {versionsQuery.isPending ? (
              <p className="text-sm text-muted-foreground">Loading version history...</p>
            ) : versionsQuery.data?.items.length ? (
              versionsQuery.data.items.map((item) => (
                <div className="flex items-center justify-between rounded-md border px-3 py-2" key={item.version}>
                  <span className="text-sm font-medium">v{item.version}</span>
                  <StudioResourceBadges origin={item.origin} status={item.status} version={item.version} />
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">No persona versions found.</p>
            )}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
