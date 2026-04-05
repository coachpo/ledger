import { useEffect, useRef, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useForm } from "react-hook-form";

import { useDebounce } from "@/hooks/use-debounce";
import { usePositionSymbolLookup } from "@/hooks/use-positions";
import type { PositionRead, PositionUpdateInput, PositionWriteInput } from "@/lib/types/position";
import { positionCreateFormSchema, type PositionCreateFormValues } from "@/components/shared/form-schemas";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
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

type PositionFormDialogProps = {
  portfolioId: number | string;
  open: boolean;
  initial?: PositionRead;
  isPending: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (data: PositionWriteInput | PositionUpdateInput) => void;
};

export function PositionFormDialog({
  portfolioId,
  open,
  initial,
  isPending,
  onOpenChange,
  onSave,
}: PositionFormDialogProps) {
  const form = useForm<PositionCreateFormValues>({
    defaultValues: {
      averageCost: initial?.averageCost ?? "",
      name: initial?.name ?? "",
      quantity: initial?.quantity ?? "",
      symbol: initial?.symbol ?? "",
    },
    resolver: zodResolver(positionCreateFormSchema),
  });

  const symbol = form.watch("symbol");
  const normalizedSymbol = symbol.trim().toUpperCase();
  const debouncedSymbol = useDebounce(normalizedSymbol, 300);
  const lastSymbolRef = useRef(initial?.symbol ?? "");
  const [nameManuallyEdited, setNameManuallyEdited] = useState(false);

  const {
    data: symbolLookup,
    isError: isSymbolLookupError,
    isFetching: isSymbolLookupFetching,
  } = usePositionSymbolLookup(
    portfolioId,
    initial ? undefined : debouncedSymbol,
  );

  useEffect(() => {
    if (initial) return;
    if (normalizedSymbol === lastSymbolRef.current) {
      return;
    }

    lastSymbolRef.current = normalizedSymbol;
    setNameManuallyEdited(false);
    form.setValue("name", "", { shouldDirty: false });
  }, [form, initial, normalizedSymbol]);

  useEffect(() => {
    if (initial) return;
    if (!debouncedSymbol || normalizedSymbol !== debouncedSymbol || nameManuallyEdited) {
      return;
    }

    form.setValue("name", symbolLookup?.name ?? "", { shouldDirty: false });
  }, [debouncedSymbol, form, initial, nameManuallyEdited, normalizedSymbol, symbolLookup?.name]);

  useEffect(() => {
    form.reset({
      averageCost: initial?.averageCost ?? "",
      name: initial?.name ?? "",
      quantity: initial?.quantity ?? "",
      symbol: initial?.symbol ?? "",
    });
    lastSymbolRef.current = initial?.symbol ?? "";
    setNameManuallyEdited(false);
  }, [form, initial, open]);

  const lookupStatusMessage = !initial && debouncedSymbol && normalizedSymbol === debouncedSymbol
    ? isSymbolLookupFetching
      ? "Looking up company name..."
      : symbolLookup?.name
        ? "Suggested name loaded. You can edit it before saving."
        : "No company name found. You can enter one manually."
    : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{initial ? "Edit Position" : "Add Position"}</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form
            className="space-y-4"
            onSubmit={form.handleSubmit((values) => {
              const payload = {
                averageCost: values.averageCost.trim(),
                name: values.name.trim() || null,
                quantity: values.quantity.trim(),
              };

              if (initial) {
                onSave(payload satisfies PositionUpdateInput);
                return;
              }

              onSave({
                ...payload,
                symbol: values.symbol.trim().toUpperCase(),
              } satisfies PositionWriteInput);
            })}
          >
            <FormField
              control={form.control}
              name="symbol"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Symbol</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      disabled={isPending || Boolean(initial)}
                      onChange={(event) => field.onChange(event.target.value.toUpperCase())}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <div className="relative">
                    <FormControl>
                      <Input
                        {...field}
                        disabled={isPending}
                        onChange={(event) => {
                          if (!initial) {
                            setNameManuallyEdited(true);
                          }
                          field.onChange(event.target.value);
                        }}
                      />
                    </FormControl>
                    {isSymbolLookupFetching && !initial && debouncedSymbol && normalizedSymbol === debouncedSymbol && (
                      <div className="absolute right-3 top-1/2 -translate-y-1/2">
                        <Loader2 className="size-4 animate-spin text-muted-foreground" />
                      </div>
                    )}
                  </div>
                  {lookupStatusMessage ? <FormDescription>{lookupStatusMessage}</FormDescription> : null}
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="sr-only" aria-live="polite">
              {isSymbolLookupFetching
                ? "Searching for company..."
                : symbolLookup?.name
                  ? `Auto-filled: ${symbolLookup.name}`
                  : isSymbolLookupError || lookupStatusMessage
                    ? "No company name found"
                    : ""}
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="quantity"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Quantity</FormLabel>
                    <FormControl>
                      <Input {...field} disabled={isPending} inputMode="decimal" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="averageCost"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Average Cost</FormLabel>
                    <FormControl>
                      <Input {...field} disabled={isPending} inputMode="decimal" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button onClick={() => onOpenChange(false)} type="button" variant="outline" disabled={isPending}>
                Cancel
              </Button>
              <Button disabled={isPending} type="submit">
                {isPending ? <Loader2 className="mr-2 size-4 animate-spin" /> : null}
                Save
              </Button>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
