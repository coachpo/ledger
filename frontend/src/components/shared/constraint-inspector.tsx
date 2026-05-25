import type { ReactNode } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

export type ConstraintInspectorItem = ReactNode;

export type ConstraintInspectorProps = {
  blocking: readonly ConstraintInspectorItem[];
  requirements?: readonly ConstraintInspectorItem[];
  summary?: ReactNode;
  title: ReactNode;
  warnings?: readonly ConstraintInspectorItem[];
};

function ConstraintList({
  items,
  label,
}: {
  items: readonly ConstraintInspectorItem[];
  label: string;
}) {
  if (items.length === 0) {
    return <p className="text-xs text-muted-foreground">No {label.toLowerCase()}.</p>;
  }

  return (
    <ul className="flex flex-col gap-1.5 text-sm" aria-label={`${label} items`}>
      {items.map((item, index) => (
        <li className="min-w-0 break-words" key={index}>{item}</li>
      ))}
    </ul>
  );
}

export function ConstraintInspector({
  blocking,
  requirements = [],
  summary,
  title,
  warnings = [],
}: ConstraintInspectorProps) {
  const hasBlocking = blocking.length > 0;

  return (
    <Alert data-state={hasBlocking ? "blocked" : "ready"} variant={hasBlocking ? "destructive" : "default"}>
      <AlertTitle className="flex min-w-0 flex-wrap items-center gap-2">
        <span className="min-w-0 break-words">{title}</span>
        <Badge variant={hasBlocking ? "destructive" : "secondary"}>{hasBlocking ? "Blocked" : "Ready"}</Badge>
      </AlertTitle>
      <AlertDescription className="gap-3">
        {summary ? <p>{summary}</p> : null}
        <section className="flex flex-col gap-2" aria-label="Blocking constraints">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-foreground">Blocking</h4>
          <ConstraintList items={blocking} label="Blocking constraints" />
        </section>
        <Separator />
        <section className="flex flex-col gap-2" aria-label="Warnings">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-foreground">Warnings</h4>
          <ConstraintList items={warnings} label="Warnings" />
        </section>
        <Separator />
        <section className="flex flex-col gap-2" aria-label="Requirements">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-foreground">Requirements</h4>
          <ConstraintList items={requirements} label="Requirements" />
        </section>
      </AlertDescription>
    </Alert>
  );
}
