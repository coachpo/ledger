import { Plus, SquarePen } from "lucide-react";
import { useNavigate } from "react-router";

import { useOutputSchemas } from "@/hooks/use-output-schemas";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import { PlatformResourceBadges, sortByKey } from "../platform-resource-shared";

export function OutputSchemasListPage() {
  const navigate = useNavigate();
  const schemasQuery = useOutputSchemas();
  const schemas = sortByKey(schemasQuery.data?.items ?? []);

  return (
    <div className="space-y-4 p-4" data-testid="platform-output-schemas-page">
      <div
        className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"
        data-testid="output-schemas-list"
      >
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">Output Schemas</h1>
          <p className="text-sm text-muted-foreground">
            Define reusable structured-output contracts with a builder-first editor, direct JSON Schema access,
            and a derived preview for quick verification.
          </p>
        </div>
        <Button data-testid="output-schemas-new" size="sm" onClick={() => navigate("/output-schemas/new")}>
          <Plus data-icon="inline-start" />
          New Output Schema
        </Button>
      </div>

      {schemasQuery.isPending ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            Loading output schemas...
          </CardContent>
        </Card>
      ) : null}

      {schemasQuery.isError ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            {schemasQuery.error instanceof Error ? schemasQuery.error.message : "Failed to load output schemas."}
          </CardContent>
        </Card>
      ) : null}

      {!schemasQuery.isPending && !schemasQuery.isError && schemas.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No output schemas exist yet.
          </CardContent>
        </Card>
      ) : null}

      {!schemasQuery.isPending && !schemasQuery.isError && schemas.length > 0 ? (
        <div className="grid gap-3">
          {schemas.map((schema) => (
            <Card key={schema.id} data-testid={`output-schemas-row-${schema.key}`}>
              <CardHeader className="gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="space-y-2">
                  <div className="space-y-1">
                    <CardTitle className="text-base">{schema.name}</CardTitle>
                    <CardDescription>{schema.key}</CardDescription>
                  </div>
                  <PlatformResourceBadges
                    status={schema.status}
                    version={schema.version}
                    extra={
                      <>
                        <span className="rounded-md border px-2 py-0.5 text-xs text-muted-foreground">
                          {schema.kind}
                        </span>
                        <span className="rounded-md border px-2 py-0.5 text-xs text-muted-foreground">
                          {schema.registryRefs.length} ref(s)
                        </span>
                      </>
                    }
                  />
                </div>
                <Button
                  data-testid={`output-schemas-open-${schema.key}`}
                  size="sm"
                  variant="outline"
                  onClick={() => navigate(`/output-schemas/${schema.id}/edit`)}
                >
                  <SquarePen data-icon="inline-start" />
                  Edit
                </Button>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                <p>{schema.description || "No description provided."}</p>
                <p>{Object.keys((schema.jsonSchema.properties as Record<string, unknown> | undefined) ?? {}).length} property definition(s)</p>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}
    </div>
  );
}
