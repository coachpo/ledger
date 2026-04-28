import { useState } from "react";
import { MoreHorizontal, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import { useDeleteTemplate, useTemplates } from "@/hooks/use-templates";
import { formatDateTime } from "@/lib/format";
import type { TextTemplateRead } from "@/lib/types/text-template";

import { ConfirmDeleteDialog } from "@/components/portfolios/confirm-delete-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardTitle } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";

export function TemplateListPage() {
  const navigate = useNavigate();
  const templatesQuery = useTemplates();
  const deleteMutation = useDeleteTemplate();
  const [deleting, setDeleting] = useState<TextTemplateRead | null>(null);
  const [search, setSearch] = useState("");

  const templates = templatesQuery.data ?? [];
  const query = search.trim().toLowerCase();
  const filteredTemplates = !query
    ? templates
    : templates.filter((template) =>
        template.name.toLowerCase().includes(query)
        || template.content.toLowerCase().includes(query),
      );

  return (
    <div className="max-w-6xl space-y-3 p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="space-y-0.5">
          <h1 className="text-xl font-semibold tracking-tight">Templates</h1>
          <p className="text-xs text-muted-foreground">
            Manage text templates with portfolio data placeholders.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" onClick={() => navigate("/templates/new")}>
            <Plus data-icon="inline-start" />
            New Template
          </Button>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <div className="relative max-w-sm flex-1">
          <Search className="absolute left-2.5 top-2 size-4 text-muted-foreground" />
          <Input
            id="template-search"
            name="templateSearch"
            placeholder="Search templates..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-8 pl-8 text-xs"
          />
        </div>
      </div>

      <div className="space-y-2">
        {templatesQuery.isPending ? (
          <Card>
            <CardContent className="py-8 text-center text-xs text-muted-foreground">
              Loading templates...
            </CardContent>
          </Card>
        ) : null}
        {templatesQuery.isError ? (
          <Card>
            <CardContent className="py-8 text-center text-xs text-muted-foreground">
              {templatesQuery.error instanceof Error
                ? templatesQuery.error.message
                : "Failed to load templates."}
            </CardContent>
          </Card>
        ) : null}
        {!templatesQuery.isPending && !templatesQuery.isError && templates.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-xs text-muted-foreground">
              No templates yet.
            </CardContent>
          </Card>
        ) : null}
        {!templatesQuery.isPending && !templatesQuery.isError && templates.length > 0 && filteredTemplates.length === 0 ? (
          <Card>
            <CardContent className="py-8 text-center text-xs text-muted-foreground">
              No templates match your search.
            </CardContent>
          </Card>
        ) : null}
        {filteredTemplates.map((template) => (
          <Card key={template.id} className="transition-colors hover:bg-accent/50">
            <CardContent className="flex items-center justify-between gap-3 px-4 py-3">
              <div className="min-w-0 space-y-0.5">
                <CardTitle className="text-sm font-medium tracking-tight">
                  {template.name}
                </CardTitle>
                <p className="text-[11px] text-muted-foreground">
                  Updated {formatDateTime(template.updatedAt)}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      aria-label={`Open actions for ${template.name}`}
                      className="size-7"
                      size="icon"
                      variant="ghost"
                    >
                      <MoreHorizontal className="size-3.5" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onSelect={() => navigate(`/templates/${template.id}/edit`)}>
                      <Pencil className="size-3.5" />
                      Edit
                    </DropdownMenuItem>
                    <DropdownMenuItem onSelect={() => setDeleting(template)} variant="destructive">
                      <Trash2 className="size-3.5" />
                      Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
                <Button
                  className="h-7 text-xs"
                  size="sm"
                  variant="secondary"
                  onClick={() => navigate(`/templates/${template.id}/edit`)}
                >
                  Open Editor
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
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
              toast.error(error instanceof Error ? error.message : "Failed to delete template"),
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
