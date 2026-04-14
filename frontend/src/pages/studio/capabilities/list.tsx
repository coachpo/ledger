import { useMemo } from "react";
import { Pencil, Plus } from "lucide-react";
import { useNavigate } from "react-router";

import { useStudioCapabilities } from "@/hooks/use-studio";
import { formatDateTime } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

import { StudioResourceBadges } from "../shared";
import { sortByKey } from "../shared-utils";

export function StudioCapabilitiesListPage() {
  const navigate = useNavigate();
  const capabilitiesQuery = useStudioCapabilities();
  const capabilities = useMemo(
    () => sortByKey(capabilitiesQuery.data?.items ?? []),
    [capabilitiesQuery.data?.items],
  );

  return (
    <div className="space-y-4 p-4" data-testid="studio-capabilities-list">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">Studio Capabilities</h1>
          <p className="text-sm text-muted-foreground">Connector, tool, and bundle records that power Studio execution.</p>
        </div>
        <Button size="sm" onClick={() => navigate("/studio/capabilities/new")}>
          <Plus className="mr-1 size-3.5" />
          New Capability
        </Button>
      </div>

      {capabilitiesQuery.isPending ? <div className="p-4 text-sm text-muted-foreground">Loading capabilities...</div> : null}
      {capabilitiesQuery.isError ? <div className="p-4 text-sm text-muted-foreground">{capabilitiesQuery.error instanceof Error ? capabilitiesQuery.error.message : "Failed to load Studio capabilities."}</div> : null}

      {!capabilitiesQuery.isPending && !capabilitiesQuery.isError ? (
        <div className="flex flex-col gap-3">
          {capabilities.map((capability) => {
            const isReadOnly = capability.origin !== "managed";

            return (
              <Card key={capability.id}>
                <CardHeader className="gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <CardTitle className="text-base font-semibold">{capability.displayName}</CardTitle>
                    <StudioResourceBadges
                      origin={capability.origin}
                      status={capability.status}
                      version={capability.version}
                      extra={<><Badge variant="outline">{capability.type}</Badge>{isReadOnly ? <Badge variant="outline">Read-only</Badge> : <Badge variant="secondary">Editable</Badge>}</>}
                    />
                  </div>
                  <CardDescription>{capability.key}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="text-sm text-muted-foreground">{capability.description}</p>
                  <p className="text-xs text-muted-foreground">Updated {formatDateTime(capability.updatedAt)}</p>
                  <div className="flex items-center justify-end gap-2">
                    <Button size="sm" variant={isReadOnly ? "outline" : "secondary"} onClick={() => navigate(`/studio/capabilities/${capability.key}/edit`)}>
                      <Pencil className="mr-1 size-3.5" />
                      {isReadOnly ? "Inspect" : "Edit"}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
