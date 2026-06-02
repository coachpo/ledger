import { Plus, Trash2 } from "lucide-react";

import { createDefaultSchemaField } from "@/lib/platform-authoring/schema/factories";
import type { SchemaIRField, SchemaIRNode, SchemaIRObject } from "@/lib/platform-authoring/schema/types";
import { InlineStatePanel } from "@/components/shared/inline-state-panel";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

import type { SchemaNodeRenderer } from "./types";

type ObjectFieldsEditorProps = {
  depth: number;
  node: SchemaIRObject;
  onChange: (node: SchemaIRNode) => void;
  renderNode: SchemaNodeRenderer;
};

export function ObjectFieldsEditor({ depth, node, onChange, renderNode }: ObjectFieldsEditorProps) {
  const fields = node.fields ?? [];

  return (
    <div className="flex flex-col gap-4">
      {fields.length === 0 ? (
        <InlineStatePanel description="Add at least one field to build an object schema." />
      ) : null}

      <div className="flex flex-col gap-4">
        {fields.map((field, index) => (
          <Card key={`${field.name}-${index}`}>
            <CardHeader>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="flex flex-col gap-1">
                  <CardTitle className="text-base">Field {index + 1}</CardTitle>
                  <CardDescription>
                    Field names feed both the builder and generated JSON Schema.
                  </CardDescription>
                </div>
                <Button size="sm" variant="outline" onClick={() => onChange({ ...node, fields: fields.filter((_, itemIndex) => itemIndex !== index) })}>
                  <Trash2 data-icon="inline-start" />
                  Remove Field
                </Button>
              </div>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="flex flex-col gap-2">
                  <Label>Field name</Label>
                  <Input data-testid={`output-schema-field-name-${index}`} aria-label="Field name" value={field.name} onChange={(event) => onFieldChange(index, field, { name: event.target.value }, node, onChange)} />
                </div>
                <div className="flex items-center justify-between rounded-md border p-4">
                  <div className="flex flex-col gap-1">
                    <Label htmlFor={`field-required-${index}`}>Required</Label>
                    <p className="text-sm text-muted-foreground">
                      Required fields flow into the JSON Schema `required` array.
                    </p>
                  </div>
                  <Switch id={`field-required-${index}`} checked={field.required !== false} onCheckedChange={(checked) => onFieldChange(index, field, { required: checked }, node, onChange)} />
                </div>
              </div>
              {renderNode({
                depth: depth + 1,
                label: `Field schema: ${field.name || `field_${index + 1}`}`,
                node: field.schema,
                onChange: (schema) => onFieldChange(index, field, { schema }, node, onChange),
              })}
            </CardContent>
          </Card>
        ))}
      </div>

      <div>
        <Button data-testid="output-schema-add-field" size="sm" variant="outline" onClick={() => onChange({ ...node, fields: [...fields, createDefaultSchemaField(`field_${fields.length + 1}`)] })}>
          <Plus data-icon="inline-start" />
          Add Field
        </Button>
      </div>
    </div>
  );
}

function onFieldChange(
  index: number,
  currentField: SchemaIRField,
  patch: Partial<SchemaIRField>,
  node: SchemaIRObject,
  onChange: (node: SchemaIRNode) => void,
) {
  const nextFields = [...(node.fields ?? [])];
  nextFields[index] = { ...currentField, ...patch };
  onChange({ ...node, fields: nextFields });
}
