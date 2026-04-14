import type { ReactNode } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";

import { formatOriginLabel, formatStatusLabel } from "./shared-utils";

export function StudioResourceBadges(props: {
  origin: string;
  status: string;
  version?: number;
  extra?: ReactNode;
}) {
  const { extra, origin, status, version } = props;

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Badge variant={origin === "managed" ? "secondary" : "outline"}>{formatOriginLabel(origin)}</Badge>
      <Badge variant="outline" className="capitalize">
        {formatStatusLabel(status)}
      </Badge>
      {typeof version === "number" ? <Badge variant="outline">v{version}</Badge> : null}
      {extra}
    </div>
  );
}

export function StudioReadOnlyBanner(props: { reason: string; testId: string }) {
  const { reason, testId } = props;

  return (
    <Alert data-testid={testId}>
      <AlertTitle>Read-only</AlertTitle>
      <AlertDescription>{reason}</AlertDescription>
    </Alert>
  );
}
