import type { ReactNode } from "react";
import { Link } from "react-router";
import { AlertCircle, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useExtension } from "@/hooks/use-extensions";
import type { ExtensionRead } from "@/lib/types/extension";

import {
  FINANCE_WORKSPACE_EXTENSION_KEY,
  FINANCE_WORKSPACE_LABEL,
} from "./signaldeck-finance";

function DisabledShell({
  children,
  testId,
}: {
  children: ReactNode;
  testId: string;
}) {
  return (
    <div
      className="flex min-h-full items-center justify-center p-4"
      data-testid={testId}
    >
      <Card className="w-full max-w-2xl border-border/70 bg-card/90 shadow-sm backdrop-blur">
        {children}
      </Card>
    </div>
  );
}

function ExtensionStateUnavailable({ onRetry }: { onRetry: () => void }) {
  return (
    <DisabledShell testId="extension-state-unavailable">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <AlertCircle className="size-5 text-destructive" />
          Extension state unavailable
        </CardTitle>
        <CardDescription>
          SignalDeck could not load backend extension state, so extension-owned
          routes are paused.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Button size="sm" type="button" variant="outline" onClick={onRetry}>
          <RefreshCw data-icon="inline-start" />
          Retry extension state
        </Button>
      </CardContent>
    </DisabledShell>
  );
}

function ExtensionDisabled({ extension }: { extension: ExtensionRead }) {
  return (
    <DisabledShell testId="extension-disabled-state">
      <CardHeader>
        <CardTitle>{extension.label} disabled</CardTitle>
        <CardDescription>
          This workspace is unavailable while its bundled extension is disabled.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Button asChild size="sm" variant="outline">
          <Link to="/workflow-packages">Open core workflow packages</Link>
        </Button>
      </CardContent>
    </DisabledShell>
  );
}

function ExtensionLoading() {
  return (
    <DisabledShell testId="extension-state-loading">
      <CardHeader>
        <CardTitle>Checking {FINANCE_WORKSPACE_LABEL}</CardTitle>
        <CardDescription>
          Loading backend extension state before opening this workspace route.
        </CardDescription>
      </CardHeader>
    </DisabledShell>
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
