import { useEffect } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import { useForm } from "react-hook-form";

import type { BalanceRead, BalanceUpdateInput, BalanceWriteInput } from "@/lib/types/balance";
import { balanceFormSchema, type BalanceFormValues } from "@/components/shared/form-schemas";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

type BalanceFormDialogProps = {
  open: boolean;
  initial?: BalanceRead;
  isPending: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (data: BalanceWriteInput | BalanceUpdateInput) => void;
};

export function BalanceFormDialog({
  open,
  initial,
  isPending,
  onOpenChange,
  onSave,
}: BalanceFormDialogProps) {
  const operationTypeLocked = Boolean(initial?.hasTradingOperations);

  const form = useForm<BalanceFormValues>({
    defaultValues: {
      amount: initial?.amount ?? "0",
      label: initial?.label ?? "",
      operationType: initial?.operationType ?? "DEPOSIT",
    },
    resolver: zodResolver(balanceFormSchema),
  });

  useEffect(() => {
    form.reset({
      amount: initial?.amount ?? "0",
      label: initial?.label ?? "",
      operationType: initial?.operationType ?? "DEPOSIT",
    });
  }, [form, initial, open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{initial ? "Edit Balance" : "Add Balance"}</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form
            className="space-y-4"
            onSubmit={form.handleSubmit((values) =>
              onSave({
                amount: values.amount.trim(),
                label: values.label.trim(),
                operationType: values.operationType,
              }),
            )}
          >
            <FormField
              control={form.control}
              name="operationType"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Operation Type</FormLabel>
                  <Select
                    disabled={isPending || operationTypeLocked}
                    value={field.value}
                    onValueChange={field.onChange}
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select operation type" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="DEPOSIT">DEPOSIT</SelectItem>
                      <SelectItem value="WITHDRAWAL">WITHDRAWAL</SelectItem>
                    </SelectContent>
                  </Select>
                  {operationTypeLocked ? (
                    <p className="text-sm text-muted-foreground">
                      Operation type is locked once this balance has trading history.
                    </p>
                  ) : null}
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="label"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Label</FormLabel>
                  <FormControl>
                    <Input {...field} disabled={isPending} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="amount"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Amount</FormLabel>
                  <FormControl>
                    <Input {...field} disabled={isPending} inputMode="decimal" />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
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
