import { Puzzle } from "lucide-react";
import { toast } from "sonner";

import { EmptyStatePanel } from "@/components/shared/empty-state-panel";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { ProvenanceBadge } from "@/components/shared/provenance-badge";
import { ResourceStatusStrip } from "@/components/shared/resource-status-strip";
import { Switch } from "@/components/ui/switch";
import { useExtensions, useToggleExtension } from "@/hooks/use-extensions";
import type { ExtensionRead } from "@/lib/types/extension";

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
    <PlatformResourceCard
      actions={
        <Switch
          aria-label={`${extension.enabled ? "Disable" : "Enable"} ${extension.label} extension`}
          checked={extension.enabled}
          data-testid={`extension-toggle-${testSegment}`}
          disabled={togglePending}
          onCheckedChange={(checked) => onToggle(extension, checked)}
        />
      }
      badges={
        <ProvenanceBadge
          detail="statically resident"
          label="Bundled"
          tone="verified"
        />
      }
      density="compact"
      description="System control row for bundled route, navigation, and tool availability."
      metadata="Ownership: SignalDeck Core plus Finance Workspace extension"
      statusStrip={
        <ResourceStatusStrip
          items={[
            {
              label: "State",
              tone: extension.enabled ? "success" : "muted",
              value: enabledLabel,
            },
            {
              label: "Contract",
              tone: "neutral",
              value: "key, label, enabled",
            },
            {
              label: "Blast radius",
              tone: extension.enabled ? "neutral" : "warning",
              value: "Finance routes, nav, tools",
            },
          ]}
        />
      }
      subtitle={extension.key}
      testId={`extension-row-${testSegment}`}
      title={extension.label}
    />
  );
}

export function ExtensionsListPage() {
  const extensionsQuery = useExtensions();
  const toggleExtension = useToggleExtension();
  const extensions = sortExtensions(extensionsQuery.data?.items ?? []);
  const enabledCount = extensions.filter(
    (extension) => extension.enabled,
  ).length;

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
      className="gap-3 p-3 sm:p-4"
      pageContext={{
        description:
          "Manage bundled extension availability from the slim system-state contract only. Runtime gates own route and tool visibility.",
        meta: (
          <div className="flex flex-wrap items-center gap-2">
            <ProvenanceBadge detail="system state" label="Surface" />
            <ProvenanceBadge
              detail="slim contract"
              label="Backend"
              tone="verified"
            />
          </div>
        ),
        status: (
          <ResourceStatusStrip
            items={[
              {
                label: "Bundled",
                tone: extensions.length ? "success" : "muted",
                value: String(extensions.length),
              },
              {
                label: "Enabled",
                tone: enabledCount ? "success" : "muted",
                value: String(enabledCount),
              },
            ]}
          />
        ),
        title: "Extensions",
      }}
      testId="extensions-list-page"
      toolbar={{
        className: "gap-0",
        resultSummary: `${extensions.length} bundled ${extensions.length === 1 ? "extension" : "extensions"} returned`,
      }}
    >
      {extensionsQuery.isPending ? (
        <EmptyStatePanel
          description="Loading the slim bundled-extension state before route gates and tool discovery update."
          icon={<Puzzle className="size-4" />}
          title="Loading extension state"
        />
      ) : null}

      {extensionsQuery.isError ? (
        <EmptyStatePanel
          description={
            extensionsQuery.error instanceof Error
              ? extensionsQuery.error.message
              : "Failed to load extensions."
          }
          icon={<Puzzle className="size-4" />}
          title="Unable to load extension state."
          tone="danger"
        />
      ) : null}

      {!extensionsQuery.isPending &&
      !extensionsQuery.isError &&
      extensions.length === 0 ? (
        <EmptyStatePanel
          description="The backend returned an empty bundled-extension list. This route remains limited to bundled extension state."
          icon={<Puzzle className="size-4" />}
          title="No bundled extensions are registered."
        />
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
    </InventoryPageShell>
  );
}
