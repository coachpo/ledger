import { useEffect, useState } from "react";
import { Save } from "lucide-react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import * as orchestrationHooks from "@/hooks/use-orchestration";
import {
  orchestrationRoleCreateFormSchema,
  orchestrationRoleUpdateFormSchema,
  type OrchestrationRoleCreateFormValues,
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
  description?: string | null;
  systemPrompt?: string;
  enabled?: boolean;
};

function getAvailableHook<K extends keyof typeof orchestrationHooks>(name: K) {
  if (!Object.prototype.hasOwnProperty.call(orchestrationHooks, name)) {
    return undefined;
  }

  return orchestrationHooks[name];
}

const initialValues: OrchestrationRoleCreateFormValues = {
  key: "",
  name: "",
  description: "",
  systemPrompt: "",
  enabled: true,
};

function getRoleKey(role: LooseRole | undefined) {
  if (!role) {
    return "";
  }

  return role.key ?? "";
}

function getRoleName(role: LooseRole | undefined) {
  return role?.name ?? "";
}

function getRoleDescription(role: LooseRole | undefined) {
  return role?.description ?? "";
}

function getRoleSystemPrompt(role: LooseRole | undefined) {
  return role?.systemPrompt ?? "";
}

function getRoleEnabled(role: LooseRole | undefined) {
  return role?.enabled ?? true;
}

export function OrchestrationRoleEditorPage() {
  const { roleId } = useParams<{ roleId: string }>();
  const navigate = useNavigate();
  const isEditing = Boolean(roleId);

  const useRoleHook = getAvailableHook("useOrchestrationRole");
  const useCreateRoleHook = getAvailableHook("useCreateOrchestrationRole");
  const useUpdateRoleHook = getAvailableHook("useUpdateOrchestrationRole");

  const roleQuery = useRoleHook?.(roleId) ?? {
    data: undefined,
    error: null,
    isError: false,
    isPending: false,
  };
  const createMutation = useCreateRoleHook?.();
  const updateMutation = useUpdateRoleHook?.();
  const [values, setValues] = useState<OrchestrationRoleCreateFormValues>(initialValues);

  useEffect(() => {
    const role = roleQuery.data as LooseRole | undefined;

    if (!role) {
      return;
    }

    const nextValues = {
      key: getRoleKey(role),
      name: getRoleName(role),
      description: getRoleDescription(role),
      systemPrompt: getRoleSystemPrompt(role),
      enabled: getRoleEnabled(role),
    };

    setValues((current) => {
      if (
        current.key === nextValues.key &&
        current.name === nextValues.name &&
        current.description === nextValues.description &&
        current.systemPrompt === nextValues.systemPrompt &&
        current.enabled === nextValues.enabled
      ) {
        return current;
      }

      return nextValues;
    });
  }, [roleQuery.data]);

  const isSaving = Boolean(createMutation?.isPending || updateMutation?.isPending);

  const updateValue = <Key extends keyof OrchestrationRoleCreateFormValues>(
    key: Key,
    value: OrchestrationRoleCreateFormValues[Key],
  ) => {
    setValues((current) => ({ ...current, [key]: value }));
  };

  const handleSave = async () => {
    const parsed = isEditing
        ? orchestrationRoleUpdateFormSchema.safeParse({
          description: values.description,
          enabled: values.enabled,
          name: values.name,
          systemPrompt: values.systemPrompt,
        })
      : orchestrationRoleCreateFormSchema.safeParse(values);

    if (!parsed.success) {
      toast.error(parsed.error.issues[0]?.message ?? "Role details are incomplete.");
      return;
    }

    try {
      if (isEditing && roleId && updateMutation?.mutateAsync) {
        await updateMutation.mutateAsync({
          roleId,
          data: {
            description: parsed.data.description.trim() || null,
            name: parsed.data.name.trim(),
            systemPrompt: parsed.data.systemPrompt.trim(),
            enabled: parsed.data.enabled,
          },
        });
        toast.success("Role updated");
        return;
      }

      if (createMutation?.mutateAsync) {
        const created = await createMutation.mutateAsync({
          key: values.key.trim(),
          name: values.name.trim(),
          description: values.description.trim() || null,
          systemPrompt: values.systemPrompt.trim(),
          enabled: values.enabled,
        });
        toast.success("Role created");
        navigate(`/orchestration/roles/${created.id}/edit`);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to save role");
    }
  };

  return (
    <div className="max-w-4xl p-4">
      <div className="flex flex-col gap-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-1">
            <h1 className="text-xl font-semibold tracking-tight">
              {isEditing ? "Edit Role" : "Create Role"}
            </h1>
            <p className="text-sm text-muted-foreground">
              Shared system prompts define what each orchestration role is responsible for.
            </p>
          </div>
          <Button size="sm" onClick={handleSave} disabled={isSaving}>
            <Save data-icon="inline-start" />
            Save Role
          </Button>
        </div>

        {isEditing && roleQuery.isPending ? (
          <Card>
            <CardContent className="py-8 text-center text-sm text-muted-foreground">
              Loading role details...
            </CardContent>
          </Card>
        ) : null}

        {isEditing && roleQuery.isError ? (
          <Card>
            <CardContent className="py-8 text-center text-sm text-muted-foreground">
              {roleQuery.error instanceof Error
                ? roleQuery.error.message
                : "Failed to load role details."}
            </CardContent>
          </Card>
        ) : null}

        {(!isEditing || (!roleQuery.isPending && !roleQuery.isError)) ? (
          <Card>
            <CardHeader>
              <CardTitle>Role details</CardTitle>
              <CardDescription>
                Keys are immutable after creation, while the shared system prompt stays editable.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="role-key">Key</Label>
                <Input
                  id="role-key"
                  aria-label="Key"
                  autoCapitalize="off"
                  autoCorrect="off"
                  disabled={isEditing || isSaving}
                  onChange={(event) => updateValue("key", event.target.value.toLowerCase())}
                  placeholder="macro_research_role"
                  value={values.key}
                />
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="role-name">Name</Label>
                <Input
                  id="role-name"
                  aria-label="Name"
                  disabled={isSaving}
                  onChange={(event) => updateValue("name", event.target.value)}
                  placeholder="Librarian"
                  value={values.name}
                />
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="role-description">Description</Label>
                <Textarea
                  id="role-description"
                  aria-label="Description"
                  disabled={isSaving}
                  onChange={(event) => updateValue("description", event.target.value)}
                  placeholder="Describe when this shared role should be used."
                  rows={4}
                  value={values.description}
                />
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="role-system-prompt">System Prompt</Label>
                <Textarea
                  id="role-system-prompt"
                  aria-label="System Prompt"
                  disabled={isSaving}
                  onChange={(event) => updateValue("systemPrompt", event.target.value)}
                  placeholder="Define the shared orchestration instructions for this role."
                  rows={12}
                  value={values.systemPrompt}
                />
              </div>

              <div className="flex items-center justify-between rounded-md border p-4">
                <div className="flex flex-col gap-1">
                  <Label htmlFor="role-enabled">Enabled</Label>
                  <p className="text-sm text-muted-foreground">
                    Disabled roles stay out of mention-driven execution.
                  </p>
                </div>
                <Switch
                  id="role-enabled"
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
