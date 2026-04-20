import { useEffect, useMemo, useState } from "react";
import { AlertCircle, Plus, Save, Trash2 } from "lucide-react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import {
  useActivateOutputSchema,
  useCreateOutputSchema,
  useOutputSchema,
  useUpdateOutputSchema,
} from "@/hooks/use-output-schemas";
import { ApiRequestError } from "@/lib/api-client";
import type {
  OutputSchemaBuilderField,
  OutputSchemaBuilderNode,
  OutputSchemaKind,
} from "@/lib/types/output-schema";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

import { parseRequiredText, PlatformResourceBadges } from "../platform-resource-shared";
import {
  builderToJsonSchema,
  createDefaultBuilderNode,
  createDefaultField,
  createLiteralValueDraft,
  createPreviewJson,
  formatPrimitiveList,
  parseJsonSchemaText,
  parsePrimitiveInput,
  parsePrimitiveList,
  stringifyJsonSchema,
  type OutputSchemaValidationIssue,
} from "./shared";

type LiteralDraft = {
  kind: "boolean" | "integer" | "number" | "string";
  value: string;
};

type BuilderNodeEditorProps = {
  depth?: number;
  label: string;
  node: OutputSchemaBuilderNode;
  onChange: (node: OutputSchemaBuilderNode) => void;
  onRemove?: () => void;
};

const kindOptions: OutputSchemaBuilderNode["kind"][] = [
  "object",
  "string",
  "integer",
  "number",
  "boolean",
  "enum",
  "literal",
  "array",
  "ref",
  "discriminated_union",
];

function updateNodeMetadata(
  node: OutputSchemaBuilderNode,
  key: "description" | "title",
  value: string,
): OutputSchemaBuilderNode {
  return { ...node, [key]: value.trim() ? value : null };
}

function BuilderNodeEditor({ depth = 0, label, node, onChange, onRemove }: BuilderNodeEditorProps) {
  const [literalDraft, setLiteralDraft] = useState<LiteralDraft>(() =>
    node.kind === "literal"
      ? createLiteralValueDraft(node)
      : { kind: "string", value: "value" },
  );

  useEffect(() => {
    if (node.kind === "literal") {
      setLiteralDraft(createLiteralValueDraft(node));
    }
  }, [node]);

  const handleKindChange = (nextKind: OutputSchemaBuilderNode["kind"]) => {
    const nextNode = createDefaultBuilderNode(nextKind);
    onChange({
      ...nextNode,
      description: node.description ?? null,
      title: node.title ?? null,
    });
  };

  return (
    <Card className={depth > 0 ? "border-dashed" : undefined}>
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1">
            <CardTitle className="text-base">{label}</CardTitle>
            <CardDescription>Adjust the supported builder subset and keep the JSON Schema tab in sync.</CardDescription>
          </div>
          {onRemove ? (
            <Button size="sm" variant="outline" onClick={onRemove}>
              <Trash2 data-icon="inline-start" />
              Remove
            </Button>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="grid gap-4 md:grid-cols-3">
          <div className="space-y-2">
            <Label>Node kind</Label>
            <Select value={node.kind} onValueChange={(value: OutputSchemaBuilderNode["kind"]) => handleKindChange(value)}>
              <SelectTrigger aria-label={`${label} node kind`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {kindOptions.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Title</Label>
            <Input value={node.title ?? ""} onChange={(event) => onChange(updateNodeMetadata(node, "title", event.target.value))} />
          </div>
          <div className="space-y-2">
            <Label>Description</Label>
            <Input value={node.description ?? ""} onChange={(event) => onChange(updateNodeMetadata(node, "description", event.target.value))} />
          </div>
        </div>

        {node.kind === "object" ? (
          <ObjectFieldsEditor node={node} onChange={onChange} />
        ) : null}

        {node.kind === "array" ? (
          <BuilderNodeEditor label="Array items" node={node.items} depth={depth + 1} onChange={(items) => onChange({ ...node, items })} />
        ) : null}

        {node.kind === "enum" ? (
          <div className="space-y-2">
            <Label>Enum values</Label>
            <Textarea value={formatPrimitiveList(node.values)} rows={5} onChange={(event) => onChange({ ...node, values: parsePrimitiveList(event.target.value) })} />
            <p className="text-sm text-muted-foreground">Enter one value per line. Numbers and booleans keep their primitive types.</p>
          </div>
        ) : null}

        {node.kind === "literal" ? (
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>Literal type</Label>
              <Select
                value={literalDraft.kind}
                onValueChange={(value: LiteralDraft["kind"]) => {
                  const nextDraft = { kind: value, value: value === "boolean" ? "true" : literalDraft.value };
                  setLiteralDraft(nextDraft);
                  onChange({ ...node, value: parsePrimitiveInput(nextDraft.value, nextDraft.kind) });
                }}
              >
                <SelectTrigger aria-label={`${label} literal type`}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="string">string</SelectItem>
                  <SelectItem value="integer">integer</SelectItem>
                  <SelectItem value="number">number</SelectItem>
                  <SelectItem value="boolean">boolean</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Literal value</Label>
              <Input
                value={literalDraft.value}
                onChange={(event) => {
                  const nextDraft = { ...literalDraft, value: event.target.value };
                  setLiteralDraft(nextDraft);
                  onChange({ ...node, value: parsePrimitiveInput(nextDraft.value, nextDraft.kind) });
                }}
              />
            </div>
          </div>
        ) : null}

        {node.kind === "ref" ? (
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>Schema key</Label>
              <Input value={node.schemaKey} onChange={(event) => onChange({ ...node, schemaKey: event.target.value })} />
            </div>
            <div className="space-y-2">
              <Label>Schema version</Label>
              <Input
                value={node.schemaVersion ?? ""}
                onChange={(event) => {
                  const value = event.target.value.trim();
                  onChange({ ...node, schemaVersion: value ? Number.parseInt(value, 10) : undefined });
                }}
              />
            </div>
          </div>
        ) : null}

        {node.kind === "discriminated_union" ? (
          <div className="flex flex-col gap-4">
            <div className="space-y-2">
              <Label>Discriminator field</Label>
              <Input value={node.discriminator} onChange={(event) => onChange({ ...node, discriminator: event.target.value })} />
            </div>
            <div className="flex flex-col gap-3">
              {node.variants.map((variant, index) => (
                <BuilderNodeEditor
                  key={`${label}-variant-${index}`}
                  depth={depth + 1}
                  label={`Variant ${index + 1}`}
                  node={variant}
                  onChange={(nextVariant) => {
                    const nextVariants = [...node.variants];
                    nextVariants[index] = nextVariant;
                    onChange({ ...node, variants: nextVariants });
                  }}
                  onRemove={node.variants.length > 2 ? () => onChange({ ...node, variants: node.variants.filter((_, itemIndex) => itemIndex !== index) }) : undefined}
                />
              ))}
            </div>
            <div>
              <Button size="sm" variant="outline" onClick={() => onChange({ ...node, variants: [...node.variants, createDefaultBuilderNode("object")] })}>
                <Plus data-icon="inline-start" />
                Add Variant
              </Button>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

type ObjectFieldsEditorProps = {
  node: Extract<OutputSchemaBuilderNode, { kind: "object" }>;
  onChange: (node: OutputSchemaBuilderNode) => void;
};

function ObjectFieldsEditor({ node, onChange }: ObjectFieldsEditorProps) {
  const fields = node.fields ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between rounded-md border p-4">
        <div className="space-y-1">
          <Label htmlFor="allow-additional-properties">Allow additional properties</Label>
          <p className="text-sm text-muted-foreground">Objects default to closed contracts, matching the backend compiler.</p>
        </div>
        <Switch id="allow-additional-properties" checked={Boolean(node.allowAdditionalProperties)} onCheckedChange={(checked) => onChange({ ...node, allowAdditionalProperties: checked })} />
      </div>

      {fields.length === 0 ? (
        <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">Add at least one field to build an object schema.</div>
      ) : null}

      <div className="flex flex-col gap-4">
        {fields.map((field, index) => (
          <Card key={`${field.name}-${index}`}>
            <CardHeader>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="space-y-1">
                  <CardTitle className="text-base">Field {index + 1}</CardTitle>
                  <CardDescription>Field names feed both the builder and generated JSON Schema.</CardDescription>
                </div>
                <Button size="sm" variant="outline" onClick={() => onChange({ ...node, fields: fields.filter((_, itemIndex) => itemIndex !== index) })}>
                  <Trash2 data-icon="inline-start" />
                  Remove Field
                </Button>
              </div>
            </CardHeader>
            <CardContent className="flex flex-col gap-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label>Field name</Label>
                  <Input data-testid={`output-schema-field-name-${index}`} aria-label="Field name" value={field.name} onChange={(event) => onFieldChange(index, field, { name: event.target.value }, node, onChange)} />
                </div>
                <div className="flex items-center justify-between rounded-md border p-4">
                  <div className="space-y-1">
                    <Label htmlFor={`field-required-${index}`}>Required</Label>
                    <p className="text-sm text-muted-foreground">Required fields flow into the JSON Schema `required` array.</p>
                  </div>
                  <Switch id={`field-required-${index}`} checked={field.required !== false} onCheckedChange={(checked) => onFieldChange(index, field, { required: checked }, node, onChange)} />
                </div>
              </div>
              <BuilderNodeEditor label={`Field schema: ${field.name || `field_${index + 1}`}`} node={field.schema} depth={1} onChange={(schema) => onFieldChange(index, field, { schema }, node, onChange)} />
            </CardContent>
          </Card>
        ))}
      </div>

      <div>
        <Button data-testid="output-schema-add-field" size="sm" variant="outline" onClick={() => onChange({ ...node, fields: [...fields, createDefaultField(`field_${fields.length + 1}`)] })}>
          <Plus data-icon="inline-start" />
          Add Field
        </Button>
      </div>
    </div>
  );
}

function onFieldChange(
  index: number,
  currentField: OutputSchemaBuilderField,
  patch: Partial<OutputSchemaBuilderField>,
  node: Extract<OutputSchemaBuilderNode, { kind: "object" }>,
  onChange: (node: OutputSchemaBuilderNode) => void,
) {
  const nextFields = [...(node.fields ?? [])];
  nextFields[index] = { ...currentField, ...patch };
  onChange({ ...node, fields: nextFields });
}

export function OutputSchemasEditorPage() {
  const { schemaId } = useParams<{ schemaId: string }>();
  const navigate = useNavigate();
  const isEditing = Boolean(schemaId);
  const schemaQuery = useOutputSchema(schemaId);
  const createMutation = useCreateOutputSchema();
  const updateMutation = useUpdateOutputSchema();
  const activateMutation = useActivateOutputSchema();
  const [activeTab, setActiveTab] = useState("builder");
  const [key, setKey] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [kind, setKind] = useState<OutputSchemaKind>("standalone");
  const [builder, setBuilder] = useState<OutputSchemaBuilderNode>(createDefaultBuilderNode("object"));
  const [jsonSchemaText, setJsonSchemaText] = useState(() => stringifyJsonSchema(builderToJsonSchema(createDefaultBuilderNode("object"))));
  const [validationIssues, setValidationIssues] = useState<OutputSchemaValidationIssue[]>([]);

  useEffect(() => {
    if (!schemaQuery.data) {
      return;
    }

    setKey(schemaQuery.data.key);
    setName(schemaQuery.data.name);
    setDescription(schemaQuery.data.description ?? "");
    setKind(schemaQuery.data.kind);
    setBuilder(schemaQuery.data.builder);
    setJsonSchemaText(stringifyJsonSchema(schemaQuery.data.jsonSchema));
    setValidationIssues([]);
  }, [schemaQuery.data]);

  const isSaving = createMutation.isPending || updateMutation.isPending;
  const isBusy = isSaving || activateMutation.isPending;
  const canActivate = Boolean(isEditing && schemaQuery.data?.status === "draft");
  const derivedJsonSchema = useMemo(() => builderToJsonSchema(builder), [builder]);

  const syncBuilder = (nextBuilder: OutputSchemaBuilderNode) => {
    setBuilder(nextBuilder);
    setJsonSchemaText(stringifyJsonSchema(builderToJsonSchema(nextBuilder)));
    setValidationIssues([]);
  };

  const syncJsonSchema = (value: string) => {
    setJsonSchemaText(value);
    const parsed = parseJsonSchemaText(value);
    if (parsed.issues.length > 0 || !parsed.builder) {
      setValidationIssues(parsed.issues);
      return;
    }

    setBuilder(parsed.builder);
    setValidationIssues([]);
  };

  const applyApiIssues = (error: unknown) => {
    if (error instanceof ApiRequestError && error.details.length > 0) {
      setValidationIssues(error.details.map((detail) => ({ field: detail.field, issue: detail.issue })));
      setActiveTab("json-schema");
    }
  };

  const handleSave = async () => {
    try {
      if (validationIssues.length > 0) {
        setActiveTab("json-schema");
        throw new Error("Resolve JSON Schema validation issues before saving.");
      }

      const payload = {
        builder,
        description: description.trim() || undefined,
        jsonSchema: derivedJsonSchema,
        kind,
        key: parseRequiredText("Key", key).toLowerCase(),
        name: parseRequiredText("Name", name),
      };

      if (isEditing && schemaId) {
        const { key: _ignored, kind: _ignoredKind, ...updatePayload } = payload;
        const updated = await updateMutation.mutateAsync({ payload: updatePayload, schemaId });
        toast.success("Output schema updated");
        navigate(`/output-schemas/${updated.id}/edit`);
        return;
      }

      const created = await createMutation.mutateAsync(payload);
      toast.success("Output schema created");
      navigate(`/output-schemas/${created.id}/edit`);
    } catch (error) {
      applyApiIssues(error);
      toast.error(error instanceof Error ? error.message : "Failed to save output schema");
    }
  };

  const handleActivate = async () => {
    if (!schemaId) {
      return;
    }

    try {
      await activateMutation.mutateAsync(schemaId);
      toast.success("Output schema activated");
    } catch (error) {
      applyApiIssues(error);
      toast.error(error instanceof Error ? error.message : "Failed to activate output schema");
    }
  };

  if (isEditing && schemaQuery.isPending) {
    return <div className="p-4 text-sm text-muted-foreground">Loading output schema details...</div>;
  }

  if (isEditing && schemaQuery.isError) {
    return (
      <div className="p-4 text-sm text-muted-foreground">
        {schemaQuery.error instanceof Error ? schemaQuery.error.message : "Output schema not found."}
      </div>
    );
  }

  return (
    <div className="space-y-4 p-4" data-testid="output-schemas-editor">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">{isEditing ? "Edit Output Schema" : "Create Output Schema"}</h1>
          <p className="text-sm text-muted-foreground">
            Keep the supported builder subset, raw JSON Schema, and preview output synchronized in one route-backed editor.
          </p>
          {schemaQuery.data ? <PlatformResourceBadges status={schemaQuery.data.status} version={schemaQuery.data.version} /> : null}
        </div>
        <div className="flex flex-wrap gap-2">
          {canActivate ? (
            <Button data-testid="output-schemas-activate" disabled={isBusy} size="sm" variant="outline" onClick={() => void handleActivate()}>
              Activate Output Schema
            </Button>
          ) : null}
          <Button data-testid="output-schemas-save" disabled={isSaving} size="sm" onClick={() => void handleSave()}>
            <Save data-icon="inline-start" />
            Save Output Schema
          </Button>
        </div>
      </div>

      {validationIssues.length > 0 ? (
        <Alert data-testid="output-schema-validation-feedback" variant="destructive">
          <AlertCircle />
          <AlertTitle>Unsupported or invalid JSON Schema</AlertTitle>
          <AlertDescription>
            <ul className="list-disc pl-5">
              {validationIssues.map((issue) => (
                <li key={`${issue.field}-${issue.issue}`}>{`${issue.field}: ${issue.issue}`}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Schema details</CardTitle>
          <CardDescription>Keys are immutable after creation. Shared schemas can be referenced from other editor flows.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="output-schema-key">Key</Label>
            <Input id="output-schema-key" aria-label="Key" disabled={isEditing || isSaving} value={key} onChange={(event) => setKey(event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="output-schema-name">Name</Label>
            <Input id="output-schema-name" aria-label="Name" disabled={isSaving} value={name} onChange={(event) => setName(event.target.value)} />
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label htmlFor="output-schema-description">Description</Label>
            <Textarea id="output-schema-description" aria-label="Description" disabled={isSaving} rows={3} value={description} onChange={(event) => setDescription(event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Kind</Label>
            <Select value={kind} disabled={isEditing || isSaving} onValueChange={(value: OutputSchemaKind) => setKind(value)}>
              <SelectTrigger aria-label="Kind">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="standalone">standalone</SelectItem>
                <SelectItem value="shared">shared</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList>
          <TabsTrigger value="builder">Builder</TabsTrigger>
          <TabsTrigger value="json-schema">JSON Schema</TabsTrigger>
          <TabsTrigger value="preview">Preview</TabsTrigger>
        </TabsList>
      </Tabs>

      <div className={activeTab === "builder" ? "mt-4" : "mt-4 hidden"}>
        <BuilderNodeEditor label="Root schema" node={builder} onChange={syncBuilder} />
      </div>

      <div className={activeTab === "json-schema" ? "mt-4" : "mt-4 hidden"}>
        <Card>
          <CardHeader>
            <CardTitle>JSON Schema</CardTitle>
            <CardDescription>Unsupported keywords are rejected here with deterministic feedback before save.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Textarea
              data-testid="output-schema-json-editor"
              aria-label="JSON Schema"
              rows={24}
              value={jsonSchemaText}
              onChange={(event) => syncJsonSchema(event.target.value)}
            />
            <p className="text-sm text-muted-foreground">Supported keywords mirror the backend compiler subset for objects, arrays, primitives, refs, enums, literals, and discriminated unions.</p>
          </CardContent>
        </Card>
      </div>

      <div className={activeTab === "preview" ? "mt-4" : "mt-4 hidden"}>
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Preview data</CardTitle>
              <CardDescription>Derived sample output from the current builder state.</CardDescription>
            </CardHeader>
            <CardContent>
              <pre data-testid="output-schema-preview" className="overflow-x-auto rounded-md bg-muted p-4 text-sm">
                {createPreviewJson(builder)}
              </pre>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Derived JSON Schema</CardTitle>
              <CardDescription>Builder changes serialize directly into the JSON Schema you save.</CardDescription>
            </CardHeader>
            <CardContent>
              <pre className="overflow-x-auto rounded-md bg-muted p-4 text-sm">{stringifyJsonSchema(derivedJsonSchema)}</pre>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
