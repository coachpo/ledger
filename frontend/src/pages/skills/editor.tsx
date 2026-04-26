import { useEffect, useMemo, useState } from "react";
import { Save } from "lucide-react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { ExactJsonPreview } from "@/components/platform-authoring/inspectors/exact-json-preview";
import { useActivateSkill, useCreateSkill, useSkill, useUpdateSkill } from "@/hooks/use-skills";
import type { SkillCreateInput, SkillUpdateInput } from "@/lib/types/skill";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

import { parseLineList, parseRequiredText, PlatformResourceBadges, stringifyJson } from "../platform-resource-shared";

type SkillEditorValues = {
  description: string;
  key: string;
  name: string;
  toolDefinitions: string;
};

const initialValues: SkillEditorValues = {
  description: "",
  key: "",
  name: "",
  toolDefinitions: "",
};

export function SkillsEditorPage() {
  const { skillId } = useParams<{ skillId: string }>();
  const navigate = useNavigate();
  const isEditing = Boolean(skillId);
  const skillQuery = useSkill(skillId);
  const createMutation = useCreateSkill();
  const updateMutation = useUpdateSkill();
  const activateMutation = useActivateSkill();
  const [values, setValues] = useState<SkillEditorValues>(initialValues);

  useEffect(() => {
    if (!skillQuery.data) {
      return;
    }

    setValues({
      description: skillQuery.data.description ?? "",
      key: skillQuery.data.key,
      name: skillQuery.data.name,
      toolDefinitions: skillQuery.data.toolDefinitions.map((definition) => definition.tool).join("\n"),
    });
  }, [skillQuery.data]);

  const isSaving = createMutation.isPending || updateMutation.isPending;
  const isBusy = isSaving || activateMutation.isPending;
  const canActivate = Boolean(isEditing && skillQuery.data?.status === "draft");
  const serializedToolDefinitions = useMemo(
    () =>
      stringifyJson(
        parseLineList(values.toolDefinitions).map((tool) => ({ tool })),
      ),
    [values.toolDefinitions],
  );

  const updateValue = <Key extends keyof SkillEditorValues>(key: Key, value: SkillEditorValues[Key]) => {
    setValues((current) => ({ ...current, [key]: value }));
  };

  const buildPayload = (): SkillCreateInput | SkillUpdateInput => {
    const tools = parseLineList(values.toolDefinitions);
    if (tools.length === 0) {
      throw new Error("At least one tool definition is required.");
    }

    return {
      description: values.description.trim() || undefined,
      key: parseRequiredText("Key", values.key).toLowerCase(),
      name: parseRequiredText("Name", values.name),
      toolDefinitions: tools.map((tool) => ({ tool })),
    };
  };

  const handleSave = async () => {
    try {
      const payload = buildPayload();

      if (isEditing && skillId) {
        const { key: _ignored, ...updatePayload } = payload as SkillCreateInput;
        const updated = await updateMutation.mutateAsync({ payload: updatePayload, skillId });
        toast.success("Skill updated");
        navigate(`/skills/${updated.id}/edit`);
        return;
      }

      const created = await createMutation.mutateAsync(payload as SkillCreateInput);
      toast.success("Skill created");
      navigate(`/skills/${created.id}/edit`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to save skill");
    }
  };

  const handleActivate = async () => {
    if (!skillId) {
      return;
    }

    try {
      await activateMutation.mutateAsync(skillId);
      toast.success("Skill activated");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to activate skill");
    }
  };

  if (isEditing && skillQuery.isPending) {
    return <div className="p-4 text-sm text-muted-foreground">Loading skill details...</div>;
  }

  if (isEditing && skillQuery.isError) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        {skillQuery.error instanceof Error ? skillQuery.error.message : "Skill not found."}
      </div>
    );
  }

  return (
    <div className="space-y-4 p-4" data-testid="skills-editor">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">
            {isEditing ? "Edit Skill" : "Create Skill"}
          </h1>
          <p className="text-sm text-muted-foreground">
            Define a reusable skill and the tool identifiers it contributes to agents.
          </p>
          {skillQuery.data ? (
            <PlatformResourceBadges status={skillQuery.data.status} version={skillQuery.data.version} />
          ) : null}
        </div>
        <div className="flex flex-wrap gap-2">
          {canActivate ? (
            <Button data-testid="skills-activate" disabled={isBusy} size="sm" variant="outline" onClick={() => void handleActivate()}>
              Activate Skill
            </Button>
          ) : null}
          <Button disabled={isSaving} size="sm" onClick={handleSave}>
            <Save data-icon="inline-start" />
            Save Skill
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Skill details</CardTitle>
          <CardDescription>
            Keys are immutable after creation. Tool definitions accept one tool id per line.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="skill-key">Key</Label>
              <Input
                id="skill-key"
                aria-label="Key"
                disabled={isEditing || isSaving}
                value={values.key}
                onChange={(event) => updateValue("key", event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="skill-name">Name</Label>
              <Input
                id="skill-name"
                aria-label="Name"
                disabled={isSaving}
                value={values.name}
                onChange={(event) => updateValue("name", event.target.value)}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="skill-description">Description</Label>
            <Textarea
              id="skill-description"
              aria-label="Description"
              disabled={isSaving}
              rows={4}
              value={values.description}
              onChange={(event) => updateValue("description", event.target.value)}
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="skill-tool-definitions">Tool Definitions</Label>
              <Textarea
                id="skill-tool-definitions"
                aria-label="Tool Definitions"
                disabled={isSaving}
                rows={8}
                value={values.toolDefinitions}
                onChange={(event) => updateValue("toolDefinitions", event.target.value)}
              />
              <p className="text-sm text-muted-foreground">Add one tool id per line.</p>
            </div>
            <div className="space-y-2">
              <Label>Exact Tool Definitions JSON</Label>
              <ExactJsonPreview
                ariaLabel="Exact tool definitions JSON"
                data-testid="skills-tool-definitions-json-preview"
                value={serializedToolDefinitions}
              />
              <p className="text-sm text-muted-foreground">
                Read-only preview of the exact JSON array saved from the current tool-definition lines.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
