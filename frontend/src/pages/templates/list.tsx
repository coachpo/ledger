import { useMemo, useState } from "react";
import { MoreHorizontal, Plus, Trash2 } from "lucide-react";
import { Link } from "react-router";
import { toast } from "sonner";

import { useResourceFilterState } from "@/hooks/use-resource-filter-state";
import { useResourceSelectionState } from "@/hooks/use-resource-selection-state";
import {
  useDeleteTemplate,
  useDeleteTemplates,
  useTemplates,
} from "@/hooks/use-templates";
import { formatDateTime } from "@/lib/format";
import type { TextTemplateRead } from "@/lib/types/text-template";

import { ConfirmDeleteDialog } from "@/components/portfolios/confirm-delete-dialog";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { ResourceFilterBar } from "@/components/shared/resource-filter-bar";
import { ResourceTableFrame } from "@/components/shared/resource-table-frame";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

type TemplateListData = TextTemplateRead[] | { items?: TextTemplateRead[] };

function getTemplateItems(
  data: TemplateListData | undefined,
): TextTemplateRead[] {
  if (Array.isArray(data)) {
    return data;
  }

  return data?.items ?? [];
}

function getTemplateId(template: TextTemplateRead) {
  return template.id;
}

function getTemplateSearchText(template: TextTemplateRead) {
  return `${template.name} ${template.content}`;
}

function formatTemplateCount(count: number) {
  return `${count} ${count === 1 ? "template" : "templates"}`;
}

export function TemplateListPage() {
  const templatesQuery = useTemplates();
  const deleteMutation = useDeleteTemplate();
  const deleteTemplatesMutation = useDeleteTemplates();
  const [deleting, setDeleting] = useState<TextTemplateRead | null>(null);

  const templates = useMemo(
    () => getTemplateItems(templatesQuery.data),
    [templatesQuery.data],
  );
  const { filteredItems: filteredTemplates, search, setSearch } =
    useResourceFilterState({
      items: templates,
      searchText: getTemplateSearchText,
    });
  const activeSearch = search.trim();
  const templateSelection = useResourceSelectionState({
    getId: getTemplateId,
    items: filteredTemplates,
  });
  const selectedTemplates = templateSelection.selectedItems;
  const selectedCount = templateSelection.selectedCount;
  const handleDeleteSelected = () => {
    if (selectedTemplates.length === 0) {
      return;
    }

    const templateIds = selectedTemplates.map((template) => template.id);
    const count = selectedTemplates.length;
    deleteTemplatesMutation.mutate(templateIds, {
      onError: (error) =>
        toast.error(
          error instanceof Error ? error.message : "Failed to delete templates",
        ),
      onSuccess: () => {
        toast.success(`${formatTemplateCount(count)} deleted`);
        templateSelection.clearSelection();
      },
    });
  };

  return (
    <InventoryPageShell
      filterBar={
        activeSearch
          ? {
              items: [
                {
                  active: true,
                  clearLabel: "Clear template search",
                  id: "search",
                  label: "Search",
                  value: activeSearch,
                  onClear: () => setSearch(""),
                },
              ],
              onClearAll: () => setSearch(""),
              testId: "templates-active-filters",
            }
          : null
      }
      pageContext={{
        actions: (
          <Button asChild size="sm">
            <Link to="/templates/new">
              <Plus data-icon="inline-start" />
              New Template
            </Link>
          </Button>
        ),
        description: "Manage templates.",
        title: "Templates",
      }}
      testId="templates-list-page"
      toolbar={{
        resultSummary:
          templates.length > 0
            ? `Showing ${formatTemplateCount(filteredTemplates.length)} of ${formatTemplateCount(templates.length)}`
            : "No templates loaded",
        search: {
          id: "template-search",
          label: "Search templates",
          name: "templateSearch",
          placeholder: "Search templates...",
          value: search,
          onChange: setSearch,
        },
      }}
    >
      <section
        aria-label="Template inventory"
        className="grid gap-2 sm:gap-3"
        data-testid="templates-inventory"
      >
        {templatesQuery.isPending ? (
          <InventoryStatePanel title="Loading templates..." />
        ) : null}
        {templatesQuery.isError ? (
          <InventoryStatePanel
            description={
              templatesQuery.error instanceof Error
                ? templatesQuery.error.message
                : "Failed to load templates."
            }
            tone="danger"
            title="Failed to load templates"
          />
        ) : null}
        {!templatesQuery.isPending &&
        !templatesQuery.isError &&
        templates.length === 0 ? (
          <InventoryStatePanel
            description="Create a reusable markdown template with portfolio, report, and runtime-input placeholders."
            testId="templates-empty-state"
            title="No templates yet."
          />
        ) : null}
        {!templatesQuery.isPending &&
        !templatesQuery.isError &&
        templates.length > 0 &&
        filteredTemplates.length === 0 ? (
          <InventoryStatePanel
            description="Refine the search by template name or placeholder content."
            testId="templates-filtered-empty-state"
            title="No templates match your search."
          />
        ) : null}
        {filteredTemplates.length > 0 ? (
          <ResourceTableFrame>
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/30 hover:bg-muted/30">
                  <TableHead className="w-9">
                    <Checkbox
                      aria-label="Select all shown templates"
                      checked={
                        templateSelection.allSelected
                          ? true
                          : templateSelection.someSelected
                            ? "indeterminate"
                            : false
                      }
                      onCheckedChange={(checked) =>
                        templateSelection.setItemsSelected(
                          filteredTemplates,
                          checked === true,
                        )
                      }
                    />
                  </TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Updated</TableHead>
                  <TableHead className="w-[160px] text-right">
                    Actions
                  </TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredTemplates.map((template) => {
                  const isSelected = templateSelection.isSelected(template.id);

                  return (
                    <TableRow
                      key={template.id}
                      data-state={isSelected ? "selected" : undefined}
                    >
                      <TableCell>
                        <Checkbox
                          aria-label={`Select template ${template.name}`}
                          checked={isSelected}
                          onCheckedChange={(checked) =>
                            templateSelection.setItemsSelected(
                              [template],
                              checked === true,
                            )
                          }
                        />
                      </TableCell>
                      <TableCell className="font-medium">
                        <Link
                          className="rounded-sm underline-offset-4 hover:underline focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                          to={`/templates/${template.id}/edit`}
                        >
                          {template.name}
                        </Link>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {formatDateTime(template.updatedAt)}
                      </TableCell>
                      <TableCell>
                        <div className="flex justify-end gap-1.5">
                          <Button asChild size="sm" variant="outline">
                            <Link
                              aria-label={`Open editor for ${template.name}`}
                              to={`/templates/${template.id}/edit`}
                            >
                              Open Editor
                            </Link>
                          </Button>
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button
                                aria-label={`Open actions for ${template.name}`}
                                className="size-7"
                                size="icon"
                                type="button"
                                variant="ghost"
                              >
                                <MoreHorizontal />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem
                                onSelect={() => setDeleting(template)}
                                variant="destructive"
                              >
                                <Trash2 className="size-3.5" />
                                Delete
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </ResourceTableFrame>
        ) : null}
      </section>

      {selectedCount > 0 ? (
        <ResourceFilterBar
          actions={
            <>
              <Button
                size="sm"
                variant="destructive"
                disabled={deleteTemplatesMutation.isPending}
                onClick={handleDeleteSelected}
              >
                <Trash2 data-icon="inline-start" />
                Delete selected
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={templateSelection.clearSelection}
              >
                Clear
              </Button>
            </>
          }
          summary={`${selectedCount} of ${filteredTemplates.length} templates selected`}
          testId="templates-bulk-actions"
        />
      ) : null}

      <ConfirmDeleteDialog
        open={Boolean(deleting)}
        title="Delete template"
        description={`Delete ${deleting?.name ?? "this template"}? This cannot be undone.`}
        isPending={deleteMutation.isPending}
        onOpenChange={(open) => {
          if (!open) {
            setDeleting(null);
          }
        }}
        onConfirm={() => {
          if (!deleting) {
            return;
          }

          deleteMutation.mutate(deleting.id, {
            onError: (error) =>
              toast.error(
                error instanceof Error
                  ? error.message
                  : "Failed to delete template",
              ),
            onSuccess: () => {
              toast.success("Template deleted");
              templateSelection.setIdsSelected([deleting.id], false);
              setDeleting(null);
            },
          });
        }}
      />
    </InventoryPageShell>
  );
}
