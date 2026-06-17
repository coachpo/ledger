import type { ReactNode } from "react";
import { Link } from "react-router";
import { AlertCircle, RefreshCw } from "lucide-react";

import { CanonicalErrorPage } from "@/components/shared/canonical-error-page";
import { ProvenanceBadge } from "@/components/shared/provenance-badge";
import type { ResourceStatusStripItem } from "@/components/shared/resource-status-strip";
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
    <CanonicalErrorPage
      action={action}
      contentClassName="min-h-0"
      contentTestId="extension-gate-content"
      description="Extension-owned routes render only after backend state confirms the bundled workspace is enabled."
      descriptionTestId="extension-gate-description"
      icon={icon}
      meta={
        <>
          <ProvenanceBadge detail="runtime gate" label="Surface" />
          <ProvenanceBadge
            detail="bundled extension"
            label={FINANCE_WORKSPACE_LABEL}
          />
        </>
      }
      metaTestId="extension-gate-meta"
      panelDescription={description}
      panelTestId="extension-gate-panel"
      panelTitle={title}
      rootClassName="min-h-full"
      rootElement="div"
      statusItems={statusItems}
      statusTestId="extension-gate-status"
      testId={testId}
      title="Finance Workspace gate"
      tone={tone}
    />
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
