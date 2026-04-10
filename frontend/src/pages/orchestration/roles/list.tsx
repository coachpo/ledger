import { useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import * as orchestrationHooks from "@/hooks/use-orchestration";
import { ConfirmDeleteDialog } from "@/components/portfolios/confirm-delete-dialog";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";

type LooseRole = {
  id: number;
  key?: string;
  handle?: string;
  name?: string;
  description?: string | null;
  systemPrompt?: string;
};

function getRoleHandle(role: LooseRole) {
  return role.handle ?? role.key ?? "unknown_role";
}

function getRoleName(role: LooseRole) {
  return role.name ?? getRoleHandle(role);
}

export function OrchestrationRolesListPage() {
  const navigate = useNavigate();
  const rolesQuery = orchestrationHooks.useOrchestrationRoles();
  const deleteMutation = orchestrationHooks.useDeleteOrchestrationRole();
  const roles = (rolesQuery.data ?? []) as LooseRole[];
  const [deleting, setDeleting] = useState<LooseRole | null>(null);

  return (
    <div className="max-w-5xl p-4">
      <div className="flex flex-col gap-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-1">
            <h1 className="text-xl font-semibold tracking-tight">Orchestration Roles</h1>
            <p className="text-sm text-muted-foreground">
              Shared system prompts define the reusable role catalog for orchestration.
            </p>
          </div>
          <Button size="sm" onClick={() => navigate("/orchestration/roles/new") }>
            <Plus data-icon="inline-start" />
            Create Role
          </Button>
        </div>

        {rolesQuery.isPending ? (
          <Card>
            <CardContent className="py-8 text-center text-sm text-muted-foreground">
              Loading role catalog...
            </CardContent>
          </Card>
        ) : null}

        {rolesQuery.isError ? (
          <Card>
            <CardContent className="py-8 text-center text-sm text-muted-foreground">
              {rolesQuery.error instanceof Error
                ? rolesQuery.error.message
                : "Failed to load orchestration roles."}
            </CardContent>
          </Card>
        ) : null}

        {!rolesQuery.isPending && !rolesQuery.isError && roles.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-sm text-muted-foreground">
              No orchestration roles yet.
            </CardContent>
          </Card>
        ) : null}

        {!rolesQuery.isPending && !rolesQuery.isError ? (
          <div className="flex flex-col gap-3">
            {roles.map((role) => (
              <Card key={role.id}>
                <CardHeader className="gap-2">
                  <CardTitle className="text-base font-semibold">{getRoleName(role)}</CardTitle>
                  <CardDescription>Reusable orchestration role</CardDescription>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  <p className="text-sm text-muted-foreground">
                    {role.description?.trim() || "Recurring orchestration responsibilities stay consistent across runs."}
                  </p>
                  <div className="rounded-lg border bg-muted/30 px-3 py-2 text-sm text-foreground">
                    {role.systemPrompt?.trim() || "System prompt will appear here once the role is configured."}
                  </div>
                  <div className="flex items-center justify-end gap-2">
                    <Button
                      aria-label={`Edit ${getRoleName(role)}`}
                      size="sm"
                      variant="secondary"
                      onClick={() => navigate(`/orchestration/roles/${role.id}/edit`)}
                    >
                      <Pencil data-icon="inline-start" />
                      Edit
                    </Button>
                    <Button
                      aria-label={`Delete ${getRoleName(role)}`}
                      size="sm"
                      variant="outline"
                      onClick={() => setDeleting(role)}
                    >
                      <Trash2 data-icon="inline-start" />
                      Delete
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        ) : null}

        <ConfirmDeleteDialog
          open={Boolean(deleting)}
          title="Delete role"
          description={`Delete ${deleting ? getRoleName(deleting) : "this role"}? This cannot be undone.`}
          isPending={deleteMutation.isPending}
          onOpenChange={(open) => {
            if (!open) {
              setDeleting(null);
            }
          }}
          onConfirm={() => {
            if (!deleting) {
              return;
            }

            deleteMutation.mutate(deleting.id, {
              onError: (error) =>
                toast.error(error instanceof Error ? error.message : "Failed to delete role"),
              onSuccess: () => {
                toast.success("Role deleted");
                setDeleting(null);
              },
            });
          }}
        />
      </div>
    </div>
  );
}
