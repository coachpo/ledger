import { Fragment, type ComponentProps } from "react";

import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/components/ui/utils";

type StructuredValueInspectorPresentation = "cards" | "tree";

type StructuredValueInspectorProps = {
  label?: string | null;
  preserveObjectKeyOrder?: boolean;
  presentation?: StructuredValueInspectorPresentation;
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

function formatPrimitiveValue(
  value: unknown,
  kind: StructuredValueKind,
): string {
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

function formatCollectionSummary(
  value: unknown,
  kind: StructuredValueKind,
): string | null {
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
  preserveObjectKeyOrder: boolean,
): Array<readonly [string, unknown]> {
  if (kind === "array") {
    return (value as unknown[]).map(
      (item, index) => [`[${index}]`, item] as const,
    );
  }

  if (kind === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    return preserveObjectKeyOrder
      ? entries
      : entries.sort(([left], [right]) => left.localeCompare(right));
  }

  return [];
}

type StructuredValueNodeProps = {
  depth: number;
  label: string | null;
  preserveObjectKeyOrder: boolean;
  presentation: StructuredValueInspectorPresentation;
  value: unknown;
};

function StructuredValueNode({
  depth,
  label,
  preserveObjectKeyOrder,
  presentation,
  value,
}: StructuredValueNodeProps) {
  const kind = getStructuredValueKind(value);
  const summary = formatCollectionSummary(value, kind);
  const entries = getCollectionEntries(value, kind, preserveObjectKeyOrder);
  const isCollection = kind === "array" || kind === "object";

  if (presentation === "tree") {
    return (
      <div
        className={cn("min-w-0", depth > 0 && "border-l border-border/70 pl-3")}
      >
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 py-1">
          {label ? (
            <span
              className={cn(
                "font-medium text-foreground",
                depth === 0 ? "text-sm" : "text-xs",
              )}
            >
              {label}
            </span>
          ) : null}
          <Badge variant="outline" className="h-5 px-1.5 capitalize">
            {kind}
          </Badge>
          {summary ? (
            <span className="text-xs text-muted-foreground">{summary}</span>
          ) : null}
          {!isCollection ? (
            <code className="min-w-0 break-words whitespace-pre-wrap rounded bg-background px-1.5 py-0.5 text-xs text-foreground">
              {formatPrimitiveValue(value, kind)}
            </code>
          ) : null}
        </div>

        {isCollection ? (
          entries.length > 0 ? (
            <div className="mt-1 space-y-1">
              {entries.map(([entryLabel, entryValue]) => (
                <StructuredValueNode
                  depth={depth + 1}
                  key={`${label ?? "root"}-${entryLabel}`}
                  label={entryLabel}
                  preserveObjectKeyOrder={preserveObjectKeyOrder}
                  presentation={presentation}
                  value={entryValue}
                />
              ))}
            </div>
          ) : (
            <p className="py-1 text-sm text-muted-foreground">Empty {kind}</p>
          )
        ) : null}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-lg border border-border/70 bg-muted/20 p-3",
        depth > 0 && "ml-4",
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        {label ? (
          <span className="text-sm font-medium text-foreground">{label}</span>
        ) : null}
        <Badge variant="outline" className="capitalize">
          {kind}
        </Badge>
        {summary ? (
          <span className="text-xs text-muted-foreground">{summary}</span>
        ) : null}
      </div>

      {isCollection ? (
        entries.length > 0 ? (
          <div className="flex flex-col">
            {entries.map(([entryLabel, entryValue], index) => (
              <Fragment key={`${label ?? "root"}-${entryLabel}`}>
                {index > 0 ? <Separator className="my-3" /> : null}
                <StructuredValueNode
                  depth={depth + 1}
                  label={entryLabel}
                  preserveObjectKeyOrder={preserveObjectKeyOrder}
                  presentation={presentation}
                  value={entryValue}
                />
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
  preserveObjectKeyOrder = false,
  presentation = "cards",
  value,
  ...props
}: StructuredValueInspectorProps) {
  return (
    <div
      className={cn(
        presentation === "cards" ? "flex flex-col gap-3" : "min-w-0",
        className,
      )}
      {...props}
    >
      <StructuredValueNode
        depth={0}
        label={label}
        preserveObjectKeyOrder={preserveObjectKeyOrder}
        presentation={presentation}
        value={value}
      />
    </div>
  );
}
