import { toast } from "sonner";

import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { useExtensions, useToggleExtension } from "@/hooks/use-extensions";
import type { ExtensionRead } from "@/lib/types/extension";

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

type ExtensionRowProps = {
  extension: ExtensionRead;
  onToggle: (extension: ExtensionRead, nextEnabled: boolean) => void;
  togglePending: boolean;
};

function ExtensionRow({
  extension,
  onToggle,
  togglePending,
}: ExtensionRowProps) {
  const testSegment = toExtensionTestSegment(extension.key);
  const enabledLabel = extension.enabled ? "Enabled" : "Disabled";

  return (
    <Card
      className="overflow-hidden transition-[background-color,border-color,box-shadow] hover:border-border hover:bg-accent/35"
      data-testid={`extension-row-${testSegment}`}
    >
      <CardContent className="flex min-w-0 flex-col gap-3 p-3 sm:flex-row sm:items-center sm:justify-between sm:p-4">
        <div className="min-w-0 flex flex-col gap-1">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h2 className="min-w-0 break-words text-sm font-medium leading-5 tracking-tight text-foreground">
              {extension.label}
            </h2>
            <Badge variant="outline">{enabledLabel}</Badge>
          </div>
          <p className="min-w-0 break-words text-xs text-muted-foreground">
            {extension.key}
          </p>
        </div>
        <div className="flex w-full shrink-0 items-center gap-2 sm:w-auto sm:justify-end">
          <Switch
            aria-label={`${extension.enabled ? "Disable" : "Enable"} ${extension.label} extension`}
            checked={extension.enabled}
            data-testid={`extension-toggle-${testSegment}`}
            disabled={togglePending}
            onCheckedChange={(checked) => onToggle(extension, checked)}
          />
        </div>
      </CardContent>
    </Card>
  );
}

export function ExtensionsListPage() {
  const extensionsQuery = useExtensions();
  const toggleExtension = useToggleExtension();
  const extensions = sortExtensions(extensionsQuery.data?.items ?? []);

  const handleToggle = async (
    extension: ExtensionRead,
    nextEnabled: boolean,
  ) => {
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
      toast.error(
        error instanceof Error
          ? error.message
          : "Failed to update extension state.",
      );
    }
  };

  return (
    <InventoryPageShell
      className="gap-3 p-4 sm:p-5 lg:p-6"
      pageContext={{
        description: "Manage bundled extensions.",
        title: "Extensions",
      }}
      testId="extensions-list-page"
      toolbar={null}
    >
      {extensionsQuery.isPending ? (
        <InventoryStatePanel
          description="Loading the slim bundled-extension state before route gates and tool discovery update."
          testId="extensions-loading-state"
          title="Loading extension state"
        />
      ) : null}

      {extensionsQuery.isError ? (
        <InventoryStatePanel
          description={
            extensionsQuery.error instanceof Error
              ? extensionsQuery.error.message
              : "Failed to load extensions."
          }
          testId="extensions-error-state"
          title="Unable to load extension state."
          tone="danger"
        />
      ) : null}

      {!extensionsQuery.isPending &&
      !extensionsQuery.isError &&
      extensions.length === 0 ? (
        <InventoryStatePanel
          description="The backend returned an empty bundled-extension list. This route remains limited to bundled extension state."
          testId="extensions-empty-state"
          title="No bundled extensions are registered."
        />
      ) : null}

      {!extensionsQuery.isPending &&
      !extensionsQuery.isError &&
      extensions.length > 0 ? (
        <div className="grid gap-2 sm:gap-3">
          {extensions.map((extension) => (
            <ExtensionRow
              extension={extension}
              key={extension.key}
              onToggle={handleToggle}
              togglePending={toggleExtension.isPending}
            />
          ))}
        </div>
      ) : null}
    </InventoryPageShell>
  );
}
