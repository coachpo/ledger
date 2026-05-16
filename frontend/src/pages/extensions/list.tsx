import { toast } from "sonner";

import { useExtensions, useToggleExtension } from "@/hooks/use-extensions";
import { formatDateTime } from "@/lib/format";
import type { ExtensionRead } from "@/lib/types/extension";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";

import { PlatformResourceCard, PlatformResourceList } from "../platform-resource-shared";

function sortExtensions(items: readonly ExtensionRead[]) {
  return [...items].sort((left, right) => {
    const byLabel = left.label.localeCompare(right.label);
    return byLabel !== 0 ? byLabel : left.key.localeCompare(right.key);
  });
}

function toExtensionTestSegment(extensionKey: string) {
  return extensionKey
    .replace(/[^a-z0-9]+/gi, "-")
    .replace(/^-|-$/g, "")
    .toLowerCase();
}

function formatTokenLabel(value: string) {
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatNullableDateTime(value: string | null) {
  return value ? formatDateTime(value) : "Not recorded";
}

function ExtensionStatusBadge({ enabled }: { enabled: boolean }) {
  if (enabled) {
    return (
      <Badge className="border-positive/30 bg-positive/10 text-positive" variant="outline">
        Enabled
      </Badge>
    );
  }

  return (
    <Badge className="border-negative/30 bg-negative/10 text-negative" variant="outline">
      Disabled
    </Badge>
  );
}

type ExtensionRowProps = {
  extension: ExtensionRead;
  onToggle: (extension: ExtensionRead, nextEnabled: boolean) => void;
  togglePending: boolean;
};

function ExtensionRow({ extension, onToggle, togglePending }: ExtensionRowProps) {
  const testSegment = toExtensionTestSegment(extension.key);
  const categories = extension.contributionCategories.map(formatTokenLabel).join(", ");
  const dependencies = extension.dependencies.length > 0 ? extension.dependencies.join(", ") : "None";

  return (
    <PlatformResourceCard
      badges={<ExtensionStatusBadge enabled={extension.enabled} />}
      density="compactPlus"
      testId={`extension-row-${testSegment}`}
      title={extension.label}
      subtitle={extension.key}
      description={`Bundled ${formatTokenLabel(extension.phase)} extension. ${extension.versioningRule}`}
      metadata={
        <div className="grid min-w-0 gap-x-5 gap-y-2 text-sm text-muted-foreground sm:grid-cols-2 xl:grid-cols-3">
          <div className="min-w-0">
            <span className="font-medium text-foreground">Current state:</span>{" "}
            <span>{extension.enabled ? "Enabled" : "Disabled"}</span>
          </div>
          <div className="min-w-0">
            <span className="font-medium text-foreground">Contributions:</span>{" "}
            <span>{extension.contributions.length}</span>
            <span aria-hidden="true"> · </span>
            <span className="break-words">{categories || "None"}</span>
          </div>
          <div className="min-w-0">
            <span className="font-medium text-foreground">Dependencies:</span>{" "}
            <span className="break-words">{dependencies}</span>
          </div>
          <div className="min-w-0">
            <span className="font-medium text-foreground">State version:</span>{" "}
            <span>{extension.stateVersion}</span>
          </div>
          <div className="min-w-0">
            <span className="font-medium text-foreground">Last updated:</span>{" "}
            <span>{formatNullableDateTime(extension.updatedAt)}</span>
          </div>
          <div className="min-w-0">
            <span className="font-medium text-foreground">Disabled reason:</span>{" "}
            <span className="break-words">{extension.disabledReason ?? "None"}</span>
          </div>
        </div>
      }
      actions={
        <div className="flex items-center gap-3 rounded-lg border bg-background px-3 py-2">
          <div className="text-right">
            <p className="text-sm font-medium text-foreground">
              {extension.enabled ? "Enabled" : "Disabled"}
            </p>
            <p className="text-xs text-muted-foreground">Enable or disable</p>
          </div>
          <Switch
            aria-label={`${extension.enabled ? "Disable" : "Enable"} ${extension.label} extension`}
            checked={extension.enabled}
            data-testid={`extension-toggle-${testSegment}`}
            disabled={togglePending}
            onCheckedChange={(checked) => onToggle(extension, checked)}
          />
        </div>
      }
    />
  );
}

export function ExtensionsListPage() {
  const extensionsQuery = useExtensions();
  const toggleExtension = useToggleExtension();
  const extensions = sortExtensions(extensionsQuery.data?.items ?? []);

  const handleToggle = async (extension: ExtensionRead, nextEnabled: boolean) => {
    try {
      await toggleExtension.mutateAsync({
        extensionKey: extension.key,
        payload: { enabled: nextEnabled },
      });
      toast.success(
        nextEnabled
          ? `${extension.label} enabled`
          : `${extension.label} disabled`,
      );
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to update extension state.");
    }
  };

  return (
    <div className="space-y-4 p-4" data-testid="extensions-list-page">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">Extensions</h1>
          <p className="max-w-3xl text-sm text-muted-foreground">
            Manage bundled extension availability from the backend state registry.
          </p>
        </div>
      </div>

      {extensionsQuery.isPending ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            Loading extensions...
          </CardContent>
        </Card>
      ) : null}

      {extensionsQuery.isError ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            {extensionsQuery.error instanceof Error
              ? extensionsQuery.error.message
              : "Failed to load extensions."}
          </CardContent>
        </Card>
      ) : null}

      {!extensionsQuery.isPending && !extensionsQuery.isError && extensions.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No bundled extensions are registered.
          </CardContent>
        </Card>
      ) : null}

      {!extensionsQuery.isPending && !extensionsQuery.isError && extensions.length > 0 ? (
        <PlatformResourceList>
          {extensions.map((extension) => (
            <ExtensionRow
              extension={extension}
              key={extension.key}
              onToggle={handleToggle}
              togglePending={toggleExtension.isPending}
            />
          ))}
        </PlatformResourceList>
      ) : null}
    </div>
  );
}
