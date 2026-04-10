import { useState } from "react";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import * as orchestrationHooks from "@/hooks/use-orchestration";
import { ConfirmDeleteDialog } from "@/components/portfolios/confirm-delete-dialog";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

type LooseCharacter = {
  id: number;
  handle?: string;
  displayName?: string;
  name?: string;
  description?: string | null;
  roleKey?: string;
  roleId?: number;
};

function getCharacterName(character: LooseCharacter) {
  return character.displayName ?? character.name ?? character.handle ?? "Unnamed character";
}

function getRoleLabel(character: LooseCharacter) {
  if (character.roleKey) {
    return character.roleKey;
  }

  if (typeof character.roleId === "number") {
    return `Role #${character.roleId}`;
  }

  return "Role not assigned";
}

export function OrchestrationCharactersListPage() {
  const navigate = useNavigate();
  const charactersQuery = orchestrationHooks.useOrchestrationCharacters();
  const deleteMutation = orchestrationHooks.useDeleteOrchestrationCharacter();
  const characters = (charactersQuery.data ?? []) as LooseCharacter[];
  const [deleting, setDeleting] = useState<LooseCharacter | null>(null);

  return (
    <div className="max-w-5xl p-4">
      <div className="flex flex-col gap-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-1">
            <h1 className="text-xl font-semibold tracking-tight">Orchestration Characters</h1>
            <p className="text-sm text-muted-foreground">
              Map named characters onto shared roles so orchestration prompts can stay reusable.
            </p>
          </div>
          <Button size="sm" onClick={() => navigate("/orchestration/characters/new") }>
            <Plus data-icon="inline-start" />
            Create Character
          </Button>
        </div>

        {charactersQuery.isPending ? (
          <Card>
            <CardContent className="py-8 text-center text-sm text-muted-foreground">
              Loading characters...
            </CardContent>
          </Card>
        ) : null}

        {charactersQuery.isError ? (
          <Card>
            <CardContent className="py-8 text-center text-sm text-muted-foreground">
              {charactersQuery.error instanceof Error
                ? charactersQuery.error.message
                : "Failed to load characters."}
            </CardContent>
          </Card>
        ) : null}

        {!charactersQuery.isPending && !charactersQuery.isError && characters.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-sm text-muted-foreground">
              No orchestration characters yet.
            </CardContent>
          </Card>
        ) : null}

        {!charactersQuery.isPending && !charactersQuery.isError ? (
          <div className="flex flex-col gap-3">
            {characters.map((character) => (
              <Card key={character.id}>
                <CardHeader className="gap-2">
                  <CardTitle className="text-base font-semibold">
                    {getCharacterName(character)}
                  </CardTitle>
                  <CardDescription>@{character.handle ?? "unknown_character"}</CardDescription>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  <div className="rounded-lg border bg-muted/30 px-3 py-2 text-sm">
                    <span className="font-medium text-foreground">Role:</span>{" "}
                    <span className="text-muted-foreground">{getRoleLabel(character)}</span>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {character.description?.trim() || "Characters add a concrete persona on top of a shared orchestration role."}
                  </p>
                  <div className="flex items-center justify-end gap-2">
                    <Button
                      aria-label={`Edit ${getCharacterName(character)}`}
                      size="sm"
                      variant="secondary"
                      onClick={() => navigate(`/orchestration/characters/${character.id}/edit`)}
                    >
                      <Pencil data-icon="inline-start" />
                      Edit
                    </Button>
                    <Button
                      aria-label={`Delete ${getCharacterName(character)}`}
                      size="sm"
                      variant="outline"
                      onClick={() => setDeleting(character)}
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
          title="Delete character"
          description={`Delete ${deleting ? getCharacterName(deleting) : "this character"}? This cannot be undone.`}
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
                toast.error(error instanceof Error ? error.message : "Failed to delete character"),
              onSuccess: () => {
                toast.success("Character deleted");
                setDeleting(null);
              },
            });
          }}
        />
      </div>
    </div>
  );
}
