import { useEffect } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useForm } from "react-hook-form";

import type {
  PortfolioRead,
  PortfolioUpdateInput,
  PortfolioWriteInput,
} from "@/lib/types/portfolio";
import {
  portfolioCreateFormSchema,
  type PortfolioCreateFormValues,
} from "@/components/shared/form-schemas";

import { EntityDialogShell } from "@/components/shared/entity-dialog-shell";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

type PortfolioFormDialogProps = {
  open: boolean;
  initial?: PortfolioRead;
  isPending: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (data: PortfolioWriteInput | PortfolioUpdateInput) => void;
};

export function PortfolioFormDialog({
  open,
  initial,
  isPending,
  onOpenChange,
  onSave,
}: PortfolioFormDialogProps) {
  const initialBaseCurrency = initial?.baseCurrency ?? "USD";
  const form = useForm<PortfolioCreateFormValues>({
    defaultValues: {
      baseCurrency: initialBaseCurrency,
      description: initial?.description ?? "",
      name: initial?.name ?? "",
      slug: initial?.slug ?? "",
    },
    resolver: zodResolver(portfolioCreateFormSchema),
  });

  useEffect(() => {
    form.reset({
      baseCurrency: initialBaseCurrency,
      description: initial?.description ?? "",
      name: initial?.name ?? "",
      slug: initial?.slug ?? "",
    });
  }, [form, initial, initialBaseCurrency, open]);

  const formId = "portfolio-form-dialog-form";
  const dialogTitle = initial ? "Edit Portfolio" : "Create Portfolio";
  const dialogDescription = initial
    ? "Update the editable portfolio identity fields."
    : "Create a Finance Workspace portfolio with a stable slug.";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <EntityDialogShell
        title={dialogTitle}
        description={dialogDescription}
        footer={
          <>
            <Button
              onClick={() => onOpenChange(false)}
              type="button"
              variant="outline"
              disabled={isPending}
            >
              Cancel
            </Button>
            <Button form={formId} disabled={isPending} type="submit">
              {isPending ? (
                <Loader2 className="animate-spin" data-icon="inline-start" />
              ) : null}
              Save
            </Button>
          </>
        }
      >
        <Form {...form}>
          <form
            id={formId}
            className="flex flex-col gap-4"
            onSubmit={form.handleSubmit((values) => {
              const payload = {
                description: values.description.trim() || null,
                name: values.name.trim(),
              };

              if (initial) {
                onSave(payload satisfies PortfolioUpdateInput);
                return;
              }

              onSave({
                ...payload,
                baseCurrency: initialBaseCurrency.trim().toUpperCase(),
                slug: values.slug.trim().toLowerCase(),
              } satisfies PortfolioWriteInput);
            })}
          >
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input {...field} disabled={isPending} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="slug"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Slug</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      autoCapitalize="off"
                      autoCorrect="off"
                      disabled={isPending || Boolean(initial)}
                      onChange={(event) =>
                        field.onChange(event.target.value.toLowerCase())
                      }
                      placeholder="retirement"
                    />
                  </FormControl>
                  {!initial ? (
                    <FormDescription>
                      Use lowercase letters, numbers, and underscores.
                    </FormDescription>
                  ) : null}
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Description</FormLabel>
                  <FormControl>
                    <Textarea {...field} disabled={isPending} rows={4} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </form>
        </Form>
      </EntityDialogShell>
    </Dialog>
  );
}
