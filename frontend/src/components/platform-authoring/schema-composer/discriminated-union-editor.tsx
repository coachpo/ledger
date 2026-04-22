import { Fragment } from "react";
import { Plus } from "lucide-react";

import { createDefaultSchemaNode } from "@/lib/platform-authoring/schema/factories";
import type {
  SchemaIRDiscriminatedUnion,
  SchemaIRNode,
} from "@/lib/platform-authoring/schema/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

import type { SchemaNodeRenderer } from "./types";

type DiscriminatedUnionEditorProps = {
  depth: number;
  label: string;
  node: SchemaIRDiscriminatedUnion;
  onChange: (node: SchemaIRNode) => void;
  renderNode: SchemaNodeRenderer;
};

export function DiscriminatedUnionEditor({
  depth,
  label,
  node,
  onChange,
  renderNode,
}: DiscriminatedUnionEditorProps) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <Label>Discriminator field</Label>
        <Input value={node.discriminator} onChange={(event) => onChange({ ...node, discriminator: event.target.value })} />
      </div>
      <div className="flex flex-col gap-3">
        {node.variants.map((variant, index) => (
          <Fragment key={`${label}-variant-${index}`}>
            {renderNode({
              depth: depth + 1,
              label: `Variant ${index + 1}`,
              node: variant,
              onChange: (nextVariant) => {
                const nextVariants = [...node.variants];
                nextVariants[index] = nextVariant;
                onChange({ ...node, variants: nextVariants });
              },
              onRemove:
                node.variants.length > 2
                  ? () =>
                      onChange({
                        ...node,
                        variants: node.variants.filter((_, itemIndex) => itemIndex !== index),
                      })
                  : undefined,
            })}
          </Fragment>
        ))}
      </div>
      <div>
        <Button size="sm" variant="outline" onClick={() => onChange({ ...node, variants: [...node.variants, createDefaultSchemaNode("object")] })}>
          <Plus data-icon="inline-start" />
          Add Variant
        </Button>
      </div>
    </div>
  );
}
