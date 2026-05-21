import { useState } from "react";
import {
  LayoutGrid,
  List,
  MoreHorizontal,
  Plus,
  Search,
  Trash2,
} from "lucide-react";
import { Link } from "react-router";
import { toast } from "sonner";

import { useDeleteTemplate, useTemplates } from "@/hooks/use-templates";
import { formatDateTime } from "@/lib/format";
import type { TextTemplateRead } from "@/lib/types/text-template";

import { ConfirmDeleteDialog } from "@/components/portfolios/confirm-delete-dialog";
import { EntityListCard } from "@/components/shared/resource-row-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

type TemplateListData = TextTemplateRead[] | { items?: TextTemplateRead[] };

function getTemplateItems(
  data: TemplateListData | undefined,
): TextTemplateRead[] {
  if (Array.isArray(data)) {
    return data;
  }

  return data?.items ?? [];
}

export function TemplateListPage() {
  const templatesQuery = useTemplates();
  const deleteMutation = useDeleteTemplate();
  const [deleting, setDeleting] = useState<TextTemplateRead | null>(null);
  const [search, setSearch] = useState("");
  const [viewMode, setViewMode] = useState<"cards" | "table">("cards");

  const templates = getTemplateItems(templatesQuery.data);
  const query = search.trim().toLowerCase();
  const filteredTemplates = !query
    ? templates
    : templates.filter(
        (template) =>
          template.name.toLowerCase().includes(query) ||
          template.content.toLowerCase().includes(query),
      );

  return (
    <div className="space-y-4 p-4">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">Templates</h1>
          <p className="text-sm text-muted-foreground">
            Manage text templates with portfolio data placeholders.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button asChild size="sm">
            <Link to="/templates/new">
              <Plus data-icon="inline-start" />
              New Template
            </Link>
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <div className="relative max-w-sm flex-1" role="search">
          <Label htmlFor="template-search" className="sr-only">
            Search templates
          </Label>
          <Search
            className="pointer-events-none absolute left-2.5 top-2 size-4 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            id="template-search"
            name="templateSearch"
            placeholder="Search templates..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-8 pl-8 text-xs"
          />
        </div>
        <ToggleGroup
          type="single"
          value={viewMode}
          onValueChange={(value) =>
            value && setViewMode(value as "cards" | "table")
          }
        >
          <ToggleGroupItem
            value="cards"
            aria-label="Cards view"
            className="h-8 w-8 px-0"
          >
            <LayoutGrid className="size-3.5" />
          </ToggleGroupItem>
          <ToggleGroupItem
            value="table"
            aria-label="Table view"
            className="h-8 w-8 px-0"
          >
            <List className="size-3.5" />
          </ToggleGroupItem>
        </ToggleGroup>
      </div>

      <div className="grid gap-2 sm:gap-3">
        {templatesQuery.isPending ? (
          <Card>
            <CardContent className="py-8 text-center text-xs text-muted-foreground">
              Loading templates...
            </CardContent>
          </Card>
        ) : null}
        {templatesQuery.isError ? (
          <Card role="alert">
            <CardContent className="py-8 text-center text-xs text-muted-foreground">
              {templatesQuery.error instanceof Error
                ? templatesQuery.error.message
                : "Failed to load templates."}
            </CardContent>
          </Card>
        ) : null}
        {!templatesQuery.isPending &&
        !templatesQuery.isError &&
        templates.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-xs text-muted-foreground">
              No templates yet.
            </CardContent>
          </Card>
        ) : null}
        {!templatesQuery.isPending &&
        !templatesQuery.isError &&
        templates.length > 0 &&
        filteredTemplates.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-xs text-muted-foreground">
              No templates match your search.
            </CardContent>
          </Card>
        ) : null}
        {viewMode === "cards" ? (
          filteredTemplates.map((template) => (
            <EntityListCard
              key={template.id}
              title={template.name}
              metadata={<>Updated {formatDateTime(template.updatedAt)}</>}
              primaryAction={{
                kind: "link",
                label: `Open editor for ${template.name}`,
                to: `/templates/${template.id}/edit`,
              }}
              actions={
                <>
                  <Button asChild size="sm">
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
                        size="icon"
                        type="button"
                        variant="ghost"
                      >
                        <MoreHorizontal className="size-4" />
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
                </>
              }
            />
          ))
        ) : filteredTemplates.length > 0 ? (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Updated</TableHead>
                  <TableHead className="w-[160px]" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredTemplates.map((template) => (
                  <TableRow key={template.id}>
                    <TableCell className="font-medium">
                      {template.name}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatDateTime(template.updatedAt)}
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1.5">
                        <Button asChild size="sm">
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
                              <MoreHorizontal className="size-3.5" />
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
                ))}
              </TableBody>
            </Table>
          </div>
        ) : null}
      </div>

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
              setDeleting(null);
            },
          });
        }}
      />
    </div>
  );
}
