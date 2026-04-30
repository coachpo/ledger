import { Archive, Plus, SquarePen } from "lucide-react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import { useArchiveCapability, useCapabilities } from "@/hooks/use-capabilities";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import { PlatformResourceBadges, sortByKey } from "../platform-resource-shared";

export function CapabilitiesListPage() {
  const navigate = useNavigate();
  const capabilitiesQuery = useCapabilities();
  const archiveMutation = useArchiveCapability();
  const capabilities = sortByKey(capabilitiesQuery.data?.items ?? []);

  const handleArchive = async (capabilityId: number) => {
    try {
      await archiveMutation.mutateAsync(capabilityId);
      toast.success("Capability archived");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to archive capability");
    }
  };

  return (
    <div className="space-y-4 p-4" data-testid="platform-capabilities-page">
      <div
        className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"
        data-testid="capabilities-list"
      >
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">Capabilities</h1>
          <p className="text-sm text-muted-foreground">
            Manage reusable capability definitions and their tool grants for the primary workspace.
          </p>
        </div>
        <Button data-testid="capabilities-new" size="sm" onClick={() => navigate("/capabilities/new")}>
          <Plus data-icon="inline-start" />
          New Capability
        </Button>
      </div>

      {capabilitiesQuery.isPending ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            Loading capabilities...
          </CardContent>
        </Card>
      ) : null}

      {capabilitiesQuery.isError ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            {capabilitiesQuery.error instanceof Error ? capabilitiesQuery.error.message : "Failed to load capabilities."}
          </CardContent>
        </Card>
      ) : null}

      {!capabilitiesQuery.isPending && !capabilitiesQuery.isError && capabilities.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No capabilities exist yet.
          </CardContent>
        </Card>
      ) : null}

      {!capabilitiesQuery.isPending && !capabilitiesQuery.isError && capabilities.length > 0 ? (
        <div className="grid gap-3">
          {capabilities.map((capability) => (
            <Card key={capability.id} data-testid={`capabilities-row-${capability.key}`}>
              <CardHeader className="gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="space-y-2">
                  <div className="space-y-1">
                    <CardTitle className="text-base">{capability.name}</CardTitle>
                    <CardDescription>{capability.key}</CardDescription>
                  </div>
                  <PlatformResourceBadges status={capability.status} version={capability.version} />
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    data-testid={`capabilities-open-${capability.key}`}
                    size="sm"
                    variant="outline"
                    onClick={() => navigate(`/capabilities/${capability.id}/edit`)}
                  >
                    <SquarePen data-icon="inline-start" />
                    Edit
                  </Button>
                  {capability.status !== "archived" ? (
                    <Button
                      data-testid={`capabilities-archive-${capability.key}`}
                      disabled={archiveMutation.isPending}
                      size="sm"
                      variant="outline"
                      onClick={() => void handleArchive(capability.id)}
                    >
                      <Archive data-icon="inline-start" />
                      Archive
                    </Button>
                  ) : null}
                </div>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                <p>{capability.description || "No description provided."}</p>
                <p>{capability.toolGrants.length} tool grant(s)</p>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}
    </div>
  );
}
