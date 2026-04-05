import { useState, useEffect, useMemo, useRef } from "react";
import { useParams, useNavigate } from "react-router";
import {
  X,
  Save,
  Loader2,
  Eye,
  Code2,
  Braces,
  FileOutput,
} from "lucide-react";
import { toast } from "sonner";

import { TemplatePlaceholderReference } from "@/components/templates/template-placeholder-reference";
import { TemplateRuntimeInputsSection } from "@/components/templates/template-runtime-inputs-section";
import { Button } from "@/components/ui/button";
import { GenerateReportDialog } from "@/components/forms/generate-report-dialog";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

import {
  useTemplate,
  useCreateTemplate,
  useUpdateTemplate,
  useCompileInline,
  usePlaceholders,
} from "@/hooks/use-templates";
import { useCompileReport } from "@/hooks/use-reports";
import { useDebounce } from "@/hooks/use-debounce";
import { formatMarkdown } from "@/lib/markdown-format";
import {
  buildRuntimeInputs,
  createRuntimeInputRow,
  createRuntimeInputRows,
  type RuntimeInputRow,
} from "@/lib/runtime-inputs";
import type { TemplateRuntimeInputs } from "@/lib/types/text-template";

export function TemplateEditorPage() {
  const { templateId } = useParams<{ templateId: string }>();
  const navigate = useNavigate();
  const isEditing = Boolean(templateId);

  const [name, setName] = useState("");
  const [content, setContent] = useState("");
  const [isFormatting, setIsFormatting] = useState(false);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [placeholdersOpen, setPlaceholdersOpen] = useState(true);
  const [runtimeInputsOpen, setRuntimeInputsOpen] = useState(false);
  const [runtimeInputRows, setRuntimeInputRows] = useState<RuntimeInputRow[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { data: template, isLoading: isLoadingTemplate } = useTemplate(templateId);
  const { data: placeholderTree, isLoading: isLoadingPlaceholders } = usePlaceholders();
  const createMutation = useCreateTemplate();
  const updateMutation = useUpdateTemplate();
  const { mutate: compileInline, ...compileMutation } = useCompileInline();
  const compileReportMutation = useCompileReport();

  const debouncedContent = useDebounce(content, 500);
  const runtimeInputs = useMemo(() => buildRuntimeInputs(runtimeInputRows), [runtimeInputRows]);
  const debouncedRuntimeInputs = useDebounce(runtimeInputs, 500);
  const handleClose = () => navigate("/templates");

  useEffect(() => {
    if (template) {
      setName(template.name);
      setContent(template.content);
    }
  }, [template]);

  useEffect(() => {
    if (debouncedContent) {
      compileInline({ content: debouncedContent, inputs: debouncedRuntimeInputs });
    }
  }, [compileInline, debouncedContent, debouncedRuntimeInputs]);

  const handleSave = async () => {
    if (!name.trim()) {
      toast.error("Template name is required");
      return;
    }

    try {
      if (isEditing && templateId) {
        await updateMutation.mutateAsync({
          templateId,
          data: { name, content },
        });
        toast.success("Template updated successfully");
      } else {
        const newTemplate = await createMutation.mutateAsync({ name, content });
        toast.success("Template created successfully");
        navigate(`/templates/${newTemplate.id}/edit`);
      }
    } catch {
      toast.error("Failed to save template");
    }
  };

  const insertPlaceholder = (placeholder: string) => {
    if (!textareaRef.current) return;

    const start = textareaRef.current.selectionStart;
    const end = textareaRef.current.selectionEnd;
    const text = textareaRef.current.value;
    const before = text.substring(0, start);
    const after = text.substring(end);
    const newContent = `${before}{{${placeholder}}}${after}`;

    setContent(newContent);

    setTimeout(() => {
      if (textareaRef.current) {
        textareaRef.current.focus();
        const newCursorPos = start + placeholder.length + 4;
        textareaRef.current.setSelectionRange(newCursorPos, newCursorPos);
      }
    }, 0);
  };

  const handleGenerateReport = ({
    inputs,
    templateId: selectedTemplateId,
  }: {
    inputs: TemplateRuntimeInputs;
    templateId: string;
  }) => {
    setRuntimeInputRows(createRuntimeInputRows("template", inputs));
    if (Object.keys(inputs).length > 0) {
      setRuntimeInputsOpen(true);
    }

    compileReportMutation.mutate({ templateId: selectedTemplateId, input: { inputs } }, {
      onError: () => toast.error("Failed to generate report"),
      onSuccess: (report) => {
        setGenerateOpen(false);
        toast.success(`Report "${report.name}" generated`, {
          action: {
            label: "View",
            onClick: () => navigate(`/reports/${report.slug}`),
          },
        });
      },
    });
  };

  const handleFormat = async () => {
    const selectionStart = textareaRef.current?.selectionStart ?? 0;
    const selectionEnd = textareaRef.current?.selectionEnd ?? 0;
    const currentContent = content;

    setIsFormatting(true);

    try {
      const formattedContent = await formatMarkdown(currentContent);

      setContent(formattedContent);

      requestAnimationFrame(() => {
        if (textareaRef.current) {
          textareaRef.current.focus();
          textareaRef.current.setSelectionRange(
            Math.min(selectionStart, formattedContent.length),
            Math.min(selectionEnd, formattedContent.length),
          );
        }
      });

      if (formattedContent === currentContent) {
        toast.success("Markdown already formatted");
        return;
      }

      toast.success("Markdown formatted");
    } catch {
      toast.error("Failed to format markdown");
    } finally {
      setIsFormatting(false);
    }
  };

  const addRuntimeInputRow = () => {
    setRuntimeInputsOpen(true);
    setRuntimeInputRows((rows) => [...rows, createRuntimeInputRow("template")]);
  };

  const updateRuntimeInputRow = (
    rowId: string,
    field: "key" | "value",
    value: string,
  ) => {
    setRuntimeInputRows((rows) =>
      rows.map((row) => (row.id === rowId ? { ...row, [field]: value } : row)),
    );
  };

  const removeRuntimeInputRow = (rowId: string) => {
    setRuntimeInputRows((rows) => rows.filter((row) => row.id !== rowId));
  };

  if (isEditing && isLoadingTemplate) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const isSaving = createMutation.isPending || updateMutation.isPending;
  const isGenerating = compileReportMutation.isPending;

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      <div className="border-b border-border bg-card px-4 py-3">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
          <div className="flex min-w-0 flex-wrap items-center gap-2 xl:flex-1">
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8 shrink-0"
              onClick={handleClose}
              aria-label="Close editor"
            >
              <X className="h-4 w-4" />
            </Button>
            <Separator orientation="vertical" className="hidden h-5 sm:block" />
            <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <Code2 className="h-3 w-3" />
              <span>{isEditing ? "Edit" : "New"}</span>
            </div>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Template name…"
              className="h-9 min-w-[14rem] flex-1 basis-full border-border/70 bg-background px-3 text-sm font-medium shadow-none focus-visible:ring-1 sm:basis-auto xl:max-w-lg"
            />
          </div>
          <div className="flex flex-wrap items-center gap-2 border-t border-border/60 pt-3 sm:justify-end xl:ml-auto xl:border-t-0 xl:pt-0">
            <Button
              variant="ghost"
              size="sm"
              className="h-8 gap-1.5 px-3 text-sm"
              onClick={handleFormat}
              disabled={isFormatting}
            >
              {isFormatting ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
              {isFormatting ? "Formatting" : "Format"}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 gap-1.5 px-3 text-sm"
              onClick={() => setPlaceholdersOpen((o) => !o)}
            >
              <Braces className="h-3 w-3" />
              Vars
            </Button>
            <Separator orientation="vertical" className="hidden h-5 xl:block" />
            <Button
              variant="ghost"
              size="sm"
              className="h-8 px-3 text-sm"
              onClick={handleClose}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              className="h-8 gap-1.5 px-3.5 text-sm"
              onClick={handleSave}
              disabled={isSaving}
            >
              {isSaving ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <Save className="h-3 w-3" />
              )}
              Save
            </Button>
            {isEditing && templateId ? (
              <Button
                variant="secondary"
                size="sm"
                className="h-8 gap-1.5 px-3.5 text-sm"
                onClick={() => setGenerateOpen(true)}
                disabled={isGenerating}
              >
                {isGenerating ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <FileOutput className="h-3 w-3" />
                )}
                Generate Report
              </Button>
            ) : (
              <Button
                variant="secondary"
                size="sm"
                className="h-8 gap-1.5 px-3.5 text-sm"
                disabled
              >
                <FileOutput className="h-3 w-3" />
                Generate Report
              </Button>
            )}
          </div>
        </div>
      </div>

      <TemplateRuntimeInputsSection
        open={runtimeInputsOpen}
        rows={runtimeInputRows}
        onAddRow={addRuntimeInputRow}
        onOpenChange={setRuntimeInputsOpen}
        onRemoveRow={removeRuntimeInputRow}
        onUpdateRow={updateRuntimeInputRow}
      />

      <div className="grid min-h-0 flex-1 grid-cols-1 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)] 2xl:grid-cols-[minmax(0,1.3fr)_minmax(0,0.7fr)]">
        <div className="flex min-h-0 min-w-0 flex-col xl:border-r xl:border-border">
          <div className="flex items-center gap-2 border-b border-border bg-muted/50 px-4 py-2">
            <Code2 className="h-3 w-3 text-muted-foreground" />
            <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              Editor
            </span>
            <span className="ml-auto text-[10px] text-muted-foreground">
              Markdown + {"{{placeholders}}"}
            </span>
          </div>
          <div className="relative min-h-0 flex-1">
            <textarea
              id="content"
              ref={textareaRef}
              className="h-full w-full resize-none border-none bg-background px-4 py-3 font-mono text-sm leading-7 text-foreground placeholder:text-muted-foreground focus:outline-none"
              placeholder="Enter template content…"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              spellCheck={false}
            />
          </div>
        </div>

        <div className="flex min-h-0 min-w-0 flex-col">
          <div className="flex items-center gap-2 border-b border-border bg-muted/50 px-4 py-2">
            <Eye className="h-3 w-3 text-muted-foreground" />
            <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              Preview
            </span>
            {compileMutation.isPending && (
              <Loader2 className="ml-auto h-3 w-3 animate-spin text-muted-foreground" />
            )}
          </div>
          <ScrollArea className="min-h-0 flex-1">
            <div className="min-h-full bg-muted/30 px-4 py-3">
              {compileMutation.error ? (
                <div className="rounded border border-destructive/30 bg-destructive/10 px-3 py-2 font-mono text-xs text-destructive">
                  {compileMutation.error instanceof Error
                    ? compileMutation.error.message
                    : "Compile error"}
                </div>
              ) : compileMutation.data ? (
                <pre className="whitespace-pre-wrap font-mono text-sm leading-relaxed text-foreground">
                  {compileMutation.data.compiled}
                </pre>
              ) : (
                <div className="flex items-center justify-center py-12 text-xs italic text-muted-foreground">
                  {content ? "Compiling…" : "Enter content to see preview"}
                </div>
              )}
            </div>
          </ScrollArea>
        </div>
      </div>

      <TemplatePlaceholderReference
        open={placeholdersOpen}
        isLoading={isLoadingPlaceholders}
        onClose={() => setPlaceholdersOpen(false)}
        onInsert={insertPlaceholder}
        placeholderTree={placeholderTree}
      />

      {isEditing && templateId ? (
        <GenerateReportDialog
          open={generateOpen}
          onOpenChange={setGenerateOpen}
          templateOptions={[
            {
              id: templateId,
              name: template?.name ?? (name || "Current template"),
            },
          ]}
          defaultTemplateId={templateId}
          description="Generate a report snapshot from this saved template and provide runtime inputs if needed."
          initialInputs={runtimeInputs}
          isPending={isGenerating}
          lockTemplateSelection
          onGenerate={handleGenerateReport}
        />
      ) : null}
    </div>
  );
}
