import { Fragment, type ComponentProps } from "react";

import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/components/ui/utils";

type StructuredValueInspectorProps = {
  label?: string;
  value: unknown;
} & ComponentProps<"div">;

type StructuredValueKind =
  | "array"
  | "boolean"
  | "null"
  | "number"
  | "object"
  | "string"
  | "unknown";

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function getStructuredValueKind(value: unknown): StructuredValueKind {
  if (value === null) {
    return "null";
  }

  if (Array.isArray(value)) {
    return "array";
  }

  if (isPlainObject(value)) {
    return "object";
  }

  if (typeof value === "string") {
    return "string";
  }

  if (typeof value === "number") {
    return "number";
  }

  if (typeof value === "boolean") {
    return "boolean";
  }

  return "unknown";
}

function formatPrimitiveValue(value: unknown, kind: StructuredValueKind): string {
  switch (kind) {
    case "string":
      return JSON.stringify(value);
    case "null":
      return "null";
    case "unknown":
      return String(value);
    default:
      return String(value);
  }
}

function formatCollectionSummary(value: unknown, kind: StructuredValueKind): string | null {
  if (kind === "array") {
    return `${(value as unknown[]).length} item(s)`;
  }

  if (kind === "object") {
    return `${Object.keys(value as Record<string, unknown>).length} field(s)`;
  }

  return null;
}

function getCollectionEntries(
  value: unknown,
  kind: StructuredValueKind,
): Array<readonly [string, unknown]> {
  if (kind === "array") {
    return (value as unknown[]).map((item, index) => [`[${index}]`, item] as const);
  }

  if (kind === "object") {
    return Object.entries(value as Record<string, unknown>).sort(([left], [right]) =>
      left.localeCompare(right),
    );
  }

  return [];
}

type StructuredValueNodeProps = {
  depth: number;
  label: string;
  value: unknown;
};

function StructuredValueNode({ depth, label, value }: StructuredValueNodeProps) {
  const kind = getStructuredValueKind(value);
  const summary = formatCollectionSummary(value, kind);
  const entries = getCollectionEntries(value, kind);
  const isCollection = kind === "array" || kind === "object";

  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-lg border border-border/70 bg-muted/20 p-3",
        depth > 0 && "ml-4",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium text-foreground">{label}</span>
        <Badge variant="outline" className="capitalize">
          {kind}
        </Badge>
        {summary ? <span className="text-xs text-muted-foreground">{summary}</span> : null}
      </div>

      {isCollection ? (
        entries.length > 0 ? (
          <div className="flex flex-col">
            {entries.map(([entryLabel, entryValue], index) => (
              <Fragment key={`${label}-${entryLabel}`}>
                {index > 0 ? <Separator className="my-3" /> : null}
                <StructuredValueNode depth={depth + 1} label={entryLabel} value={entryValue} />
              </Fragment>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Empty {kind}</p>
        )
      ) : (
        <div className="rounded-md bg-background px-3 py-2">
          <code className="break-words text-sm whitespace-pre-wrap text-foreground">
            {formatPrimitiveValue(value, kind)}
          </code>
        </div>
      )}
    </div>
  );
}

export function StructuredValueInspector({
  className,
  label = "Value",
  value,
  ...props
}: StructuredValueInspectorProps) {
  return (
    <div className={cn("flex flex-col gap-3", className)} {...props}>
      <StructuredValueNode depth={0} label={label} value={value} />
    </div>
  );
}
