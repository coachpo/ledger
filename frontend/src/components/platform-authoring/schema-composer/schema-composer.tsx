import { SchemaNodeCard } from "./schema-node-card";
import type { SchemaComposerNodeProps } from "./types";

export type SchemaComposerProps = SchemaComposerNodeProps;

function renderNode(props: SchemaComposerNodeProps) {
  return <SchemaNodeCard {...props} renderNode={renderNode} />;
}

export function SchemaComposer(props: SchemaComposerProps) {
  return renderNode(props);
}
