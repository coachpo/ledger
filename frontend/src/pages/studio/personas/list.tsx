import { useMemo } from "react";
import { Eye, Plus } from "lucide-react";
import { useNavigate } from "react-router";

import { useStudioPersonas } from "@/hooks/use-studio";
import { formatDateTime } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

import { StudioResourceBadges } from "../shared";
import { formatKindLabel, sortByKey } from "../shared-utils";

export function StudioPersonasListPage() {
  const navigate = useNavigate();
  const personasQuery = useStudioPersonas();
  const personas = useMemo(() => sortByKey(personasQuery.data?.items ?? []), [personasQuery.data?.items]);

  return (
    <div className="space-y-4 p-4" data-testid="studio-personas-list">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">Studio Personas</h1>
          <p className="text-sm text-muted-foreground">
            Managed persona drafts are editable in Studio, while imported and seeded personas stay
            visibly read-only.
          </p>
        </div>
        <Button data-testid="studio-personas-new" size="sm" variant="outline" onClick={() => navigate("/studio/personas/new")}>
          <Plus className="mr-1 size-3.5" />
          New Persona
        </Button>
      </div>

      {personasQuery.isPending ? <div className="p-4 text-sm text-muted-foreground">Loading persona profiles...</div> : null}
      {personasQuery.isError ? <div className="p-4 text-sm text-muted-foreground">{personasQuery.error instanceof Error ? personasQuery.error.message : "Failed to load Studio personas."}</div> : null}

      {!personasQuery.isPending && !personasQuery.isError && personas.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">No Studio personas found.</CardContent>
        </Card>
      ) : null}

      {!personasQuery.isPending && !personasQuery.isError ? (
        <div className="flex flex-col gap-3">
          {personas.map((persona) => (
            <Card data-testid={`studio-personas-row-${persona.key}`} key={persona.id}>
              <CardHeader className="gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle className="text-base font-semibold">{persona.displayName}</CardTitle>
                  <StudioResourceBadges
                    origin={persona.origin}
                    status={persona.status}
                    version={persona.version}
                    extra={
                      <>
                        <Badge variant="outline">{formatKindLabel(persona.kind)}</Badge>
                        {persona.origin !== "managed" ? <Badge variant="outline">Read-only</Badge> : null}
                      </>
                    }
                  />
                </div>
                <CardDescription>{persona.key}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-muted-foreground">Canonical target: {persona.canonicalTargetId}</p>
                <p className="text-xs text-muted-foreground">Updated {formatDateTime(persona.updatedAt)}</p>
                <div className="flex items-center justify-end gap-2">
                  <Button
                    aria-label={`Inspect ${persona.displayName}`}
                    data-testid={`studio-personas-open-${persona.key}`}
                    size="sm"
                    variant="outline"
                    onClick={() => navigate(`/studio/personas/${persona.key}/edit`)}
                  >
                    <Eye className="mr-1 size-3.5" />
                    {persona.origin === "managed" && persona.status === "DRAFT" ? "Edit" : "Inspect"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}
    </div>
  );
}
