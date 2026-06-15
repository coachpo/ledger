import type { ComponentProps } from "react";

import { Checkbox } from "@/components/ui/checkbox";

type ResourceSelectionCheckboxProps = Omit<
  ComponentProps<typeof Checkbox>,
  "aria-label" | "checked" | "onCheckedChange"
> & {
  ariaLabel: string;
  indeterminate?: boolean;
  selected: boolean;
  testId?: string;
  onSelectedChange: (selected: boolean) => void;
};

function getResourceSelectionCheckedState(
  selected: boolean,
  indeterminate = false,
) {
  return selected ? true : indeterminate ? "indeterminate" : false;
}

export function ResourceSelectionCheckbox({
  ariaLabel,
  indeterminate = false,
  selected,
  testId,
  onSelectedChange,
  ...props
}: ResourceSelectionCheckboxProps) {
  return (
    <Checkbox
      aria-label={ariaLabel}
      checked={getResourceSelectionCheckedState(selected, indeterminate)}
      data-testid={testId}
      onCheckedChange={(checked) => onSelectedChange(checked === true)}
      {...props}
    />
  );
}
