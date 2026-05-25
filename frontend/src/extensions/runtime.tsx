import type { ReactNode } from "react";
import { Link } from "react-router";
import { AlertCircle, RefreshCw } from "lucide-react";

import { EmptyStatePanel } from "@/components/shared/empty-state-panel";
import { PageContextBar } from "@/components/shared/page-context-bar";
import { ProvenanceBadge } from "@/components/shared/provenance-badge";
import {
  ResourceStatusStrip,
  type ResourceStatusStripItem,
} from "@/components/shared/resource-status-strip";
import { Button } from "@/components/ui/button";
import { useExtension } from "@/hooks/use-extensions";
import type { ExtensionRead } from "@/lib/types/extension";

import {
  FINANCE_WORKSPACE_EXTENSION_KEY,
  FINANCE_WORKSPACE_LABEL,
} from "./signaldeck-finance";

function GateStateShell({
  action,
  description,
  icon,
  statusItems,
  testId,
  title,
  tone = "neutral",
}: {
  action?: ReactNode;
  description: ReactNode;
  icon?: ReactNode;
  statusItems: readonly ResourceStatusStripItem[];
  testId: string;
  title: ReactNode;
  tone?: "neutral" | "warning" | "danger";
}) {
  return (
    <div
      className="flex min-h-full items-center justify-center p-4"
      data-testid={testId}
    >
      <div className="flex w-full max-w-2xl flex-col gap-3">
        <PageContextBar
          description="Extension-owned routes render only after backend state confirms the bundled workspace is enabled."
          meta={
            <div className="flex flex-wrap items-center gap-2">
              <ProvenanceBadge detail="runtime gate" label="Surface" />
              <ProvenanceBadge detail="bundled extension" label={FINANCE_WORKSPACE_LABEL} />
            </div>
          }
          status={<ResourceStatusStrip items={statusItems} />}
          title="Finance Workspace gate"
        />
        <EmptyStatePanel
          action={action}
          description={description}
          icon={icon}
          title={title}
          tone={tone}
        />
      </div>
    </div>
  );
}

function ExtensionStateUnavailable({ onRetry }: { onRetry: () => void }) {
  return (
    <GateStateShell
      action={
        <Button size="sm" type="button" variant="outline" onClick={onRetry}>
          <RefreshCw data-icon="inline-start" />
          Retry extension state
        </Button>
      }
      description="SignalDeck could not load backend extension state, so extension-owned routes are paused until the state read succeeds."
      icon={<AlertCircle className="size-4 text-destructive" />}
      statusItems={[
        { label: "State", tone: "danger", value: "Unavailable" },
        { label: "Core routes", tone: "success", value: "Available" },
      ]}
      testId="extension-state-unavailable"
      title="Extension state unavailable"
      tone="danger"
    />
  );
}

function ExtensionDisabled({ extension }: { extension: ExtensionRead }) {
  return (
    <GateStateShell
      action={
        <Button asChild size="sm" variant="outline">
          <Link to="/workflow-packages">Open core workflow packages</Link>
        </Button>
      }
      description="Finance-owned routes, navigation, and tools are paused while this bundled extension is disabled. Core workflow package routes remain available."
      icon={<AlertCircle className="size-4" />}
      statusItems={[
        { label: "State", tone: "muted", value: "Disabled" },
        { label: "Blast radius", tone: "warning", value: "Finance routes, nav, tools" },
        { label: "Core routes", tone: "success", value: "Available" },
      ]}
      testId="extension-disabled-state"
      title={`${extension.label} disabled`}
      tone="warning"
    />
  );
}

function ExtensionLoading() {
  return (
    <GateStateShell
      description="Loading backend extension state before opening this workspace route."
      icon={<RefreshCw className="size-4" />}
      statusItems={[
        { label: "State", tone: "warning", value: "Checking" },
        { label: "Workspace", tone: "neutral", value: FINANCE_WORKSPACE_LABEL },
      ]}
      testId="extension-state-loading"
      title={`Checking ${FINANCE_WORKSPACE_LABEL}`}
      tone="warning"
    />
  );
}

export function FinanceWorkspaceRouteGate({
  children,
}: {
  children: ReactNode;
}) {
  const extensionQuery = useExtension(FINANCE_WORKSPACE_EXTENSION_KEY);

  if (extensionQuery.isPending) {
    return <ExtensionLoading />;
  }

  if (extensionQuery.isError || !extensionQuery.data) {
    return (
      <ExtensionStateUnavailable
        onRetry={() => void extensionQuery.refetch()}
      />
    );
  }

  if (!extensionQuery.data.enabled) {
    return <ExtensionDisabled extension={extensionQuery.data} />;
  }

  return <>{children}</>;
}
