import { useEffect, useState } from "react";
import { Trash2 } from "lucide-react";

import {
  buildRuntimeInputs,
  createRuntimeInputRow,
  createRuntimeInputRows,
  type RuntimeInputMap,
  type RuntimeInputRow,
} from "@/lib/runtime-inputs";

import { Button } from "@/components/ui/button";
import { EntityDialogShell } from "@/components/shared/entity-dialog-shell";
import { ResourceStatusStrip } from "@/components/shared/resource-status-strip";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type GenerateReportTemplateOption = {
  id: string;
  name: string;
};

type GenerateReportPayload = {
  inputs: RuntimeInputMap;
  templateId: string;
};

type GenerateReportDialogProps = {
  defaultTemplateId?: string;
  description?: string;
  initialInputs?: RuntimeInputMap;
  isPending: boolean;
  lockTemplateSelection?: boolean;
  onGenerate: (payload: GenerateReportPayload) => void;
  onOpenChange: (open: boolean) => void;
  open: boolean;
  templateOptions: GenerateReportTemplateOption[];
};

export function GenerateReportDialog({
  defaultTemplateId,
  description = "Select a template to compile into a report snapshot.",
  initialInputs,
  isPending,
  lockTemplateSelection = false,
  onGenerate,
  onOpenChange,
  open,
  templateOptions,
}: GenerateReportDialogProps) {
  const [selectedTemplateId, setSelectedTemplateId] = useState(
    defaultTemplateId ?? "",
  );
  const [runtimeInputRows, setRuntimeInputRows] = useState<RuntimeInputRow[]>(
    () => createRuntimeInputRows("report", initialInputs),
  );

  useEffect(() => {
    if (!open) {
      return;
    }

    setSelectedTemplateId(defaultTemplateId ?? "");
    setRuntimeInputRows(createRuntimeInputRows("report", initialInputs));
  }, [defaultTemplateId, initialInputs, open]);

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      setSelectedTemplateId(defaultTemplateId ?? "");
      setRuntimeInputRows(createRuntimeInputRows("report", initialInputs));
    }

    onOpenChange(nextOpen);
  };

  const addRuntimeInputRow = () => {
    setRuntimeInputRows((rows) => [...rows, createRuntimeInputRow("report")]);
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

  const handleGenerate = (event?: { preventDefault: () => void }) => {
    event?.preventDefault();

    if (!selectedTemplateId || isPending) {
      return;
    }

    onGenerate({
      inputs: buildRuntimeInputs(runtimeInputRows),
      templateId: selectedTemplateId,
    });
  };

  const selectedTemplateName = templateOptions.find(
    (template) => template.id === selectedTemplateId,
  )?.name;
  const formId = "generate-report-form";

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <EntityDialogShell
        title="Generate Report"
        description={description}
        constraintStrip={
          <ResourceStatusStrip
            items={[
              {
                label: "Template",
                value: selectedTemplateName ?? "Select one",
              },
              {
                label: "Runtime inputs",
                value: `${runtimeInputRows.length} ${runtimeInputRows.length === 1 ? "row" : "rows"}`,
              },
              {
                label: "Selection",
                value: lockTemplateSelection ? "Locked" : "Editable",
              },
            ]}
          />
        }
        footer={
          <>
            <Button
              type="button"
              variant="ghost"
              onClick={() => handleOpenChange(false)}
            >
              Cancel
            </Button>
            <Button
              form={formId}
              type="submit"
              disabled={!selectedTemplateId || isPending}
            >
              {isPending ? "Generating..." : "Generate"}
            </Button>
          </>
        }
      >
        <form
          id={formId}
          className="flex flex-col gap-4"
          onSubmit={handleGenerate}
        >
          <div className="flex flex-col gap-2">
            <Label htmlFor="generate-report-template">Template</Label>
            <Select
              value={selectedTemplateId}
              onValueChange={setSelectedTemplateId}
              disabled={isPending || lockTemplateSelection}
            >
              <SelectTrigger
                id="generate-report-template"
                aria-label="Template"
              >
                <SelectValue placeholder="Select a template..." />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {templateOptions.map((template) => (
                    <SelectItem key={template.id} value={template.id}>
                      {template.name}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-medium">Runtime Inputs</p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={addRuntimeInputRow}
              >
                Add Input
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Use key/value pairs like `ticker`, `portfolio_slug`, or
              `analysis_tag` when the selected template is parameterized.
            </p>
            {runtimeInputRows.length === 0 ? (
              <p className="text-xs italic text-muted-foreground">
                No runtime inputs provided.
              </p>
            ) : null}
            <div className="flex flex-col gap-2">
              {runtimeInputRows.map((row) => (
                <div key={row.id} className="flex items-center gap-2">
                  <Input
                    aria-label={`Runtime input key ${row.id}`}
                    name={`runtimeInputKey-${row.id}`}
                    value={row.key}
                    onChange={(event) =>
                      updateRuntimeInputRow(row.id, "key", event.target.value)
                    }
                    placeholder="ticker"
                  />
                  <Input
                    aria-label={`Runtime input value ${row.id}`}
                    name={`runtimeInputValue-${row.id}`}
                    value={row.value}
                    onChange={(event) =>
                      updateRuntimeInputRow(row.id, "value", event.target.value)
                    }
                    placeholder="AAPL"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => removeRuntimeInputRow(row.id)}
                    aria-label={`Remove runtime input ${row.key || row.id}`}
                  >
                    <Trash2 />
                  </Button>
                </div>
              ))}
            </div>
          </div>
        </form>
      </EntityDialogShell>
    </Dialog>
  );
}
