import type { ReactNode } from "react";

import type { SchemaIRNode } from "@/lib/platform-authoring/schema/types";

export type SchemaComposerNodeProps = {
  depth?: number;
  label: string;
  node: SchemaIRNode;
  onChange: (node: SchemaIRNode) => void;
  onRemove?: () => void;
};

export type SchemaNodeRenderer = (props: SchemaComposerNodeProps) => ReactNode;
