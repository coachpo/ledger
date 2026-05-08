import { useLocation, useParams } from "react-router";

import { Card, CardContent } from "@/components/ui/card";

function resolveMode(pathname: string) {
  if (pathname === "/workflow-packages") {
    return "list";
  }

  if (pathname.endsWith("/run")) {
    return "launch";
  }

  if (pathname.endsWith("/new")) {
    return "new";
  }

  return "detail";
}

export function WorkflowPackagePlaceholderPage() {
  const location = useLocation();
  const { packageId } = useParams();
  const mode = resolveMode(location.pathname);
  const title =
    mode === "list"
      ? "Workflow Packages"
      : mode === "new"
        ? "New Workflow Package"
        : "Workflow Package";
  const activeTab = mode === "launch" ? "Launch" : "Overview";

  return (
    <div className="p-4 space-y-4 max-w-7xl">
      <div className="space-y-0.5">
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        <p className="text-xs text-muted-foreground">
          Package-first workflow authoring shell placeholder.
        </p>
      </div>

      <Card data-testid="workflow-package-placeholder">
        <CardContent className="space-y-2 p-4 text-sm">
          <p className="font-medium text-foreground">{activeTab} tab</p>
          <p className="text-muted-foreground">
            Task 12 will replace this route contract placeholder with the package list and editor shell.
          </p>
          {packageId ? (
            <p className="text-xs text-muted-foreground">Package id: {packageId}</p>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
