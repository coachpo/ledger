import { Plus, SquarePen } from "lucide-react";
import { useNavigate } from "react-router";

import { useOutputSchemas } from "@/hooks/use-output-schemas";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

import { sortByKey } from "@/pages/platform-resource-helpers";

import {
  PlatformResourceBadges,
  PlatformResourceCard,
  PlatformResourceList,
} from "../platform-resource-shared";

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
        <Button
          className="cursor-pointer"
          data-testid="output-schemas-new"
          size="sm"
          onClick={() => navigate("/output-schemas/new")}
        >
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
        <PlatformResourceList>
          {schemas.map((schema) => (
            <PlatformResourceCard
              key={schema.id}
              density="compact"
              primaryAction={{
                kind: "link",
                label: `Open output schema ${schema.name}`,
                to: `/output-schemas/${schema.id}/edit`,
              }}
              actions={
                <Button
                  data-testid={`output-schemas-open-${schema.key}`}
                  size="sm"
                  variant="outline"
                  onClick={() => navigate(`/output-schemas/${schema.id}/edit`)}
                >
                  <SquarePen data-icon="inline-start" />
                  Edit
                </Button>
              }
              badges={
                <PlatformResourceBadges
                  status={schema.status}
                  version={schema.version}
                  extra={
                    <>
                      <span className="inline-flex h-4 items-center rounded-md border px-1.5 text-[10px] font-medium text-muted-foreground">
                        {schema.kind}
                      </span>
                      <span className="inline-flex h-4 items-center rounded-md border px-1.5 text-[10px] font-medium text-muted-foreground">
                        {schema.registryRefs.length} ref(s)
                      </span>
                    </>
                  }
                />
              }
              description={schema.description}
              metadata={
                <p className="text-sm text-muted-foreground">
                  {Object.keys((schema.jsonSchema.properties as Record<string, unknown> | undefined) ?? {}).length} property definition(s)
                </p>
              }
              subtitle={schema.key}
              testId={`output-schemas-row-${schema.key}`}
              title={schema.name}
            />
          ))}
        </PlatformResourceList>
      ) : null}
    </div>
  );
}
