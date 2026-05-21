import { toast } from "sonner";

import { useExtensions, useToggleExtension } from "@/hooks/use-extensions";
import type { ExtensionRead } from "@/lib/types/extension";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";

import {
  PlatformResourceCard,
  PlatformResourceList,
} from "../platform-resource-shared";

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

function ExtensionStatusBadge({ enabled }: { enabled: boolean }) {
  return <Badge variant="secondary">{enabled ? "Enabled" : "Disabled"}</Badge>;
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

  return (
    <PlatformResourceCard
      badges={<ExtensionStatusBadge enabled={extension.enabled} />}
      density="compactPlus"
      testId={`extension-row-${testSegment}`}
      title={extension.label}
      subtitle={extension.key}
      actions={
        <Switch
          aria-label={`${extension.enabled ? "Disable" : "Enable"} ${extension.label} extension`}
          checked={extension.enabled}
          data-testid={`extension-toggle-${testSegment}`}
          disabled={togglePending}
          onCheckedChange={(checked) => onToggle(extension, checked)}
        />
      }
    />
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
    <div className="space-y-4 p-4" data-testid="extensions-list-page">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">Extensions</h1>
          <p className="max-w-3xl text-sm text-muted-foreground">
            System-state surface for bundled extension availability. This page
            only reflects backend enablement state; route visibility and tool
            filtering stay owned by the extension runtime.
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
        <Card role="alert" aria-live="polite">
          <CardContent className="space-y-1 py-8 text-center text-sm text-muted-foreground">
            <p className="font-medium text-foreground">
              Unable to load extension state.
            </p>
            <p className="text-xs">
              {extensionsQuery.error instanceof Error
                ? extensionsQuery.error.message
                : "Failed to load extensions."}
            </p>
          </CardContent>
        </Card>
      ) : null}

      {!extensionsQuery.isPending &&
      !extensionsQuery.isError &&
      extensions.length === 0 ? (
        <Card>
          <CardContent className="space-y-1 py-8 text-center text-sm text-muted-foreground">
            <p className="font-medium text-foreground">
              No bundled extensions are registered.
            </p>
            <p className="text-xs">
              Extension rows appear only when the backend exposes slim bundled
              state with a key, label, and enabled flag.
            </p>
          </CardContent>
        </Card>
      ) : null}

      {!extensionsQuery.isPending &&
      !extensionsQuery.isError &&
      extensions.length > 0 ? (
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
