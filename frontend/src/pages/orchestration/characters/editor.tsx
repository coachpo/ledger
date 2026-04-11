import { useEffect, useMemo, useState } from "react";
import { Save } from "lucide-react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import * as orchestrationHooks from "@/hooks/use-orchestration";
import {
  orchestrationCharacterCreateFormSchema,
  orchestrationCharacterUpdateFormSchema,
  type OrchestrationCharacterCreateFormValues,
} from "@/components/shared/form-schemas";

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
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

type LooseRole = {
  id: number;
  key?: string;
  name?: string;
};

type LooseCharacter = {
  id: number;
  handle?: string;
  displayName?: string;
  name?: string;
  description?: string | null;
  promptAppend?: string | null;
  roleId?: number;
  roleKey?: string;
  enabled?: boolean;
};

function getAvailableHook<K extends keyof typeof orchestrationHooks>(name: K) {
  if (!Object.prototype.hasOwnProperty.call(orchestrationHooks, name)) {
    return undefined;
  }

  return orchestrationHooks[name];
}

const initialValues: OrchestrationCharacterCreateFormValues = {
  handle: "",
  name: "",
  description: "",
  role: "",
  promptAppend: "",
  enabled: true,
};

function getCharacterEnabled(character: LooseCharacter | undefined) {
  return character?.enabled ?? true;
}

function getRoleKey(role: LooseRole) {
  return role.key ?? String(role.id);
}

function resolveCharacterRoleValue(character: LooseCharacter | undefined, roles: LooseRole[]) {
  if (!character) {
    return "";
  }

  if (character.roleKey) {
    const matchedRole = roles.find((role) => getRoleKey(role) === character.roleKey);
    if (matchedRole) {
      return String(matchedRole.id);
    }
    return character.roleKey;
  }

  if (typeof character.roleId === "number") {
    return String(character.roleId);
  }

  return "";
}

function resolveRoleId(roleValue: string, roles: LooseRole[]) {
  const directRoleId = Number(roleValue);

  if (Number.isFinite(directRoleId) && roleValue.trim() !== "") {
    return directRoleId;
  }

  const matchedRole = roles.find((role) => getRoleKey(role) === roleValue);
  return matchedRole?.id ?? null;
}

export function OrchestrationCharacterEditorPage() {
  const { characterId } = useParams<{ characterId: string }>();
  const navigate = useNavigate();
  const isEditing = Boolean(characterId);

  const useCharacterHook = getAvailableHook("useOrchestrationCharacter");
  const useRolesHook = getAvailableHook("useOrchestrationRoles");
  const useCreateCharacterHook = getAvailableHook("useCreateOrchestrationCharacter");
  const useUpdateCharacterHook = getAvailableHook("useUpdateOrchestrationCharacter");

  const characterQuery = useCharacterHook?.(characterId) ?? {
    data: undefined,
    error: null,
    isError: false,
    isPending: false,
  };
  const rolesQuery = useRolesHook?.() ?? {
    data: [],
    error: null,
    isError: false,
    isPending: false,
  };
  const createMutation = useCreateCharacterHook?.();
  const updateMutation = useUpdateCharacterHook?.();
  const [values, setValues] = useState<OrchestrationCharacterCreateFormValues>(initialValues);
  const roles = useMemo(() => (rolesQuery.data ?? []) as LooseRole[], [rolesQuery.data]);

  useEffect(() => {
    const character = characterQuery.data as LooseCharacter | undefined;

    if (!character) {
      return;
    }

    const nextValues = {
      handle: character.handle ?? "",
      name: character.displayName ?? character.name ?? "",
      description: character.description ?? "",
      role: resolveCharacterRoleValue(character, roles),
      promptAppend: character.promptAppend ?? "",
      enabled: getCharacterEnabled(character),
    };

    setValues((current) => {
      if (
        current.handle === nextValues.handle &&
        current.name === nextValues.name &&
        current.description === nextValues.description &&
        current.role === nextValues.role &&
        current.promptAppend === nextValues.promptAppend &&
        current.enabled === nextValues.enabled
      ) {
        return current;
      }

      return nextValues;
    });
  }, [characterQuery.data, roles]);

  const hasRoleOptions = roles.length > 0;
  const isSaving = Boolean(createMutation?.isPending || updateMutation?.isPending);

  const updateValue = <Key extends keyof OrchestrationCharacterCreateFormValues>(
    key: Key,
    value: OrchestrationCharacterCreateFormValues[Key],
  ) => {
    setValues((current) => ({ ...current, [key]: value }));
  };

  const handleSave = async () => {
    const parsed = isEditing
        ? orchestrationCharacterUpdateFormSchema.safeParse({
          description: values.description,
          enabled: values.enabled,
          name: values.name,
          promptAppend: values.promptAppend,
          role: values.role,
        })
      : orchestrationCharacterCreateFormSchema.safeParse(values);

    if (!parsed.success) {
      toast.error(parsed.error.issues[0]?.message ?? "Character details are incomplete.");
      return;
    }

    const resolvedRoleId = resolveRoleId(values.role.trim(), roles);
    if (resolvedRoleId == null) {
      toast.error("Select a role from the orchestration catalog.");
      return;
    }

    try {
      if (isEditing && characterId && updateMutation?.mutateAsync) {
        await updateMutation.mutateAsync({
          characterId,
          data: {
            displayName: values.name.trim(),
            description: values.description.trim() || null,
            promptAppend: values.promptAppend.trim() || null,
            roleId: resolvedRoleId,
            enabled: parsed.data.enabled,
          },
        });
        toast.success("Character updated");
        return;
      }

      if (createMutation?.mutateAsync) {
        const created = await createMutation.mutateAsync({
          handle: values.handle.trim(),
          displayName: values.name.trim(),
          description: values.description.trim() || null,
          promptAppend: values.promptAppend.trim() || null,
          roleId: resolvedRoleId,
          enabled: values.enabled,
        });
        toast.success("Character created");
        navigate(`/orchestration/characters/${created.id}/edit`);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to save character");
    }
  };

  return (
    <div className="max-w-4xl p-4">
      <div className="flex flex-col gap-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-1">
            <h1 className="text-xl font-semibold tracking-tight">
              {isEditing ? "Edit Character" : "Create Character"}
            </h1>
            <p className="text-sm text-muted-foreground">
              Characters layer concrete personas on top of shared orchestration roles.
            </p>
          </div>
          <Button size="sm" onClick={handleSave} disabled={isSaving}>
            <Save data-icon="inline-start" />
            Save Character
          </Button>
        </div>

        {isEditing && characterQuery.isPending ? (
          <Card>
            <CardContent className="py-8 text-center text-sm text-muted-foreground">
              Loading character details...
            </CardContent>
          </Card>
        ) : null}

        {isEditing && characterQuery.isError ? (
          <Card>
            <CardContent className="py-8 text-center text-sm text-muted-foreground">
              {characterQuery.error instanceof Error
                ? characterQuery.error.message
                : "Failed to load character details."}
            </CardContent>
          </Card>
        ) : null}

        {(!isEditing || (!characterQuery.isPending && !characterQuery.isError)) ? (
          <Card>
            <CardHeader>
              <CardTitle>Character details</CardTitle>
              <CardDescription>
                Handles lock after creation, while role assignment and prompt append stay editable.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="character-handle">Handle</Label>
                <Input
                  id="character-handle"
                  aria-label="Handle"
                  autoCapitalize="off"
                  autoCorrect="off"
                  disabled={isEditing || isSaving}
                  onChange={(event) => updateValue("handle", event.target.value.toLowerCase())}
                  placeholder="market_researcher"
                  value={values.handle}
                />
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="character-name">Name</Label>
                <Input
                  id="character-name"
                  aria-label="Name"
                  disabled={isSaving}
                  onChange={(event) => updateValue("name", event.target.value)}
                  placeholder="Market Researcher"
                  value={values.name}
                />
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="character-role">Role</Label>
                {hasRoleOptions ? (
                  <select
                    id="character-role"
                    aria-label="Role"
                    className="flex h-9 w-full rounded-md border border-input bg-input-background px-3 text-sm"
                    disabled={isSaving}
                    onChange={(event) => updateValue("role", event.target.value)}
                    value={values.role}
                  >
                    <option value="">Select role</option>
                    {roles.map((role) => (
                      <option key={role.id} value={String(role.id)}>
                        {role.name ?? getRoleKey(role)}
                      </option>
                    ))}
                  </select>
                ) : (
                  <Input
                    id="character-role"
                    aria-label="Role"
                    disabled={isSaving}
                    onChange={(event) => updateValue("role", event.target.value)}
                    placeholder="librarian"
                    value={values.role}
                  />
                )}
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="character-description">Description</Label>
                <Textarea
                  id="character-description"
                  aria-label="Description"
                  disabled={isSaving}
                  onChange={(event) => updateValue("description", event.target.value)}
                  placeholder="Describe the persona this character should embody."
                  rows={4}
                  value={values.description}
                />
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="character-prompt-append">Prompt Append</Label>
                <Textarea
                  id="character-prompt-append"
                  aria-label="Prompt Append"
                  disabled={isSaving}
                  onChange={(event) => updateValue("promptAppend", event.target.value)}
                  placeholder="Add character-specific instructions that extend the shared role prompt."
                  rows={8}
                  value={values.promptAppend}
                />
              </div>

              <div className="flex items-center justify-between rounded-md border p-4">
                <div className="flex flex-col gap-1">
                  <Label htmlFor="character-enabled">Enabled</Label>
                  <p className="text-sm text-muted-foreground">
                    Disabled characters cannot be dispatched from mentions.
                  </p>
                </div>
                <Switch
                  id="character-enabled"
                  aria-label="Enabled"
                  checked={values.enabled}
                  disabled={isSaving}
                  onCheckedChange={(checked) => updateValue("enabled", checked)}
                />
              </div>
            </CardContent>
          </Card>
        ) : null}
      </div>
    </div>
  );
}
