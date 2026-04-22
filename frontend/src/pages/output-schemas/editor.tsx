import { useEffect, useMemo, useState } from "react";
import { AlertCircle, Save } from "lucide-react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { StructuredValueInspector } from "@/components/platform-authoring/inspectors/structured-value-inspector";
import { SchemaComposer } from "@/components/platform-authoring/schema-composer/schema-composer";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  useActivateOutputSchema,
  useCreateOutputSchema,
  useOutputSchema,
  useUpdateOutputSchema,
} from "@/hooks/use-output-schemas";
import { ApiRequestError } from "@/lib/api-client";
import { stringifyJson } from "@/lib/platform-authoring/common/serialization";
import { parseSchemaJsonText, schemaBuilderToJsonSchema } from "@/lib/platform-authoring/schema/codec";
import { createDefaultSchemaNode } from "@/lib/platform-authoring/schema/factories";
import { buildPreviewValue } from "@/lib/platform-authoring/schema/preview";
import type { SchemaValidationIssue } from "@/lib/platform-authoring/schema/validation";
import type { OutputSchemaBuilderNode, OutputSchemaKind, OutputSchemaRead } from "@/lib/types/output-schema";

import { parseRequiredText, PlatformResourceBadges } from "../platform-resource-shared";

function decodePersistedSchema(record: OutputSchemaRead) {
  return parseSchemaJsonText(stringifyJson(record.jsonSchema));
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
  const [builder, setBuilder] = useState<OutputSchemaBuilderNode>(() => createDefaultSchemaNode("object"));
  const [validationIssues, setValidationIssues] = useState<SchemaValidationIssue[]>([]);
  const [unsupportedRecordIssues, setUnsupportedRecordIssues] = useState<SchemaValidationIssue[]>([]);

  useEffect(() => {
    if (!schemaQuery.data) {
      return;
    }

    setKey(schemaQuery.data.key);
    setName(schemaQuery.data.name);
    setDescription(schemaQuery.data.description ?? "");
    setKind(schemaQuery.data.kind);
    setValidationIssues([]);

    const decoded = decodePersistedSchema(schemaQuery.data);
    if (decoded.issues.length > 0 || !decoded.builder) {
      setUnsupportedRecordIssues(decoded.issues);
      setBuilder(createDefaultSchemaNode("object"));
      return;
    }

    setUnsupportedRecordIssues([]);
    setBuilder(decoded.builder);
  }, [schemaQuery.data]);

  const hasUnsupportedPersistedRecord = isEditing && unsupportedRecordIssues.length > 0;
  const isSaving = createMutation.isPending || updateMutation.isPending;
  const isBusy = isSaving || activateMutation.isPending;
  const canActivate = Boolean(isEditing && schemaQuery.data?.status === "draft" && !hasUnsupportedPersistedRecord);
  const derivedJsonSchema = useMemo(() => schemaBuilderToJsonSchema(builder), [builder]);
  const previewValue = useMemo(() => buildPreviewValue(builder), [builder]);

  const syncBuilder = (nextBuilder: OutputSchemaBuilderNode) => {
    setBuilder(nextBuilder);
    setValidationIssues([]);
  };

  const applyApiIssues = (error: unknown) => {
    if (error instanceof ApiRequestError && error.details.length > 0) {
      setValidationIssues(error.details.map((detail) => ({ field: detail.field, issue: detail.issue })));
      setActiveTab("builder");
    }
  };

  const handleSave = async () => {
    try {
      if (hasUnsupportedPersistedRecord) {
        throw new Error("Unsupported retired schema shape");
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
    if (!schemaId || hasUnsupportedPersistedRecord) {
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
            Author supported output schemas through the shared builder and review the derived sample output before save.
          </p>
          {schemaQuery.data ? <PlatformResourceBadges status={schemaQuery.data.status} version={schemaQuery.data.version} /> : null}
        </div>
        <div className="flex flex-wrap gap-2">
          {canActivate ? (
            <Button data-testid="output-schemas-activate" disabled={isBusy} size="sm" variant="outline" onClick={() => void handleActivate()}>
              Activate Output Schema
            </Button>
          ) : null}
          <Button data-testid="output-schemas-save" disabled={isSaving || hasUnsupportedPersistedRecord} size="sm" onClick={() => void handleSave()}>
            <Save data-icon="inline-start" />
            Save Output Schema
          </Button>
        </div>
      </div>

      {hasUnsupportedPersistedRecord ? (
        <Alert data-testid="output-schema-unsupported-record" variant="destructive">
          <AlertCircle />
          <AlertTitle>Unsupported retired schema shape</AlertTitle>
          <AlertDescription>
            <p>This persisted output schema cannot be edited in the builder because it does not decode into the supported shared schema model.</p>
            <ul className="list-disc pl-5">
              {unsupportedRecordIssues.map((issue) => (
                <li key={`${issue.field}-${issue.issue}`}>{`${issue.field}: ${issue.issue}`}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      ) : null}

      {validationIssues.length > 0 ? (
        <Alert data-testid="output-schema-validation-feedback" variant="destructive">
          <AlertCircle />
          <AlertTitle>Unsupported or invalid schema</AlertTitle>
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
            <Input id="output-schema-description" aria-label="Description" disabled={isSaving} value={description} onChange={(event) => setDescription(event.target.value)} />
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

      {!hasUnsupportedPersistedRecord ? (
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <TabsList>
            <TabsTrigger value="builder">Builder</TabsTrigger>
            <TabsTrigger value="preview">Preview</TabsTrigger>
          </TabsList>
          <TabsContent forceMount value="builder" className="mt-4">
            <SchemaComposer label="Root schema" node={builder} onChange={syncBuilder} />
          </TabsContent>
          <TabsContent forceMount value="preview" className="mt-4">
            <Card>
              <CardHeader>
                <CardTitle>Preview data</CardTitle>
                <CardDescription>Derived sample output from the current builder state.</CardDescription>
              </CardHeader>
              <CardContent>
                <StructuredValueInspector data-testid="output-schema-preview" label="Derived sample output" value={previewValue} />
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      ) : null}
    </div>
  );
}
