import { type ComponentProps, useId, useMemo } from "react";

import type { ResourceRef } from "@/lib/platform-authoring/common/resource-ref";
import {
  SearchableSelect,
  type SearchableSelectOption,
} from "@/components/shared/searchable-select";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/components/ui/utils";

const NO_VERSION_OPTION = "__none__";
const LATEST_VERSION_OPTION = "__latest__";
const STALE_VERSION_OPTION = "__stale__";

export type ResourceRefSelectOption = ResourceRef & {
  description?: string;
  keywords?: string[];
  label: string;
  status?: string;
};

type ResourceRefOptionGroup = {
  description?: string;
  key: string;
  keywords: string[];
  label: string;
  status?: string;
  versions: ResourceRefSelectOption[];
};

export type ResourceRefSelectProps = {
  description?: string;
  disabled?: boolean;
  emptyDescription?: string;
  emptyTitle?: string;
  label?: string;
  onChange: (nextValue: ResourceRef | null) => void;
  options?: readonly ResourceRefSelectOption[];
  resourceLabel?: string;
  resourcePlaceholder?: string;
  searchPlaceholder?: string;
  value: ResourceRef | null;
  versionLabel?: string;
} & Omit<ComponentProps<"div">, "onChange">;

function compareResourceOptions(
  left: ResourceRefSelectOption,
  right: ResourceRefSelectOption,
): number {
  const keyComparison = left.key.localeCompare(right.key);

  if (keyComparison !== 0) {
    return keyComparison;
  }

  if (left.version === right.version) {
    return 0;
  }

  if (left.version == null) {
    return 1;
  }

  if (right.version == null) {
    return -1;
  }

  return right.version - left.version;
}

function formatVersionLabel(version: number | null): string {
  return version == null ? "Latest published version" : `v${version}`;
}

function groupResourceOptions(
  options: readonly ResourceRefSelectOption[],
): ResourceRefOptionGroup[] {
  const groupedOptions = new Map<string, ResourceRefOptionGroup>();

  [...options].sort(compareResourceOptions).forEach((option) => {
    const existingGroup = groupedOptions.get(option.key);

    if (existingGroup) {
      existingGroup.versions.push(option);
      return;
    }

    groupedOptions.set(option.key, {
      description: option.description,
      key: option.key,
      keywords: option.keywords ?? [],
      label: option.label,
      status: option.status,
      versions: [option],
    });
  });

  return Array.from(groupedOptions.values());
}

function getSelectedGroup(
  groups: readonly ResourceRefOptionGroup[],
  value: ResourceRef | null,
): ResourceRefOptionGroup | null {
  if (!value?.key) {
    return null;
  }

  return groups.find((group) => group.key === value.key) ?? null;
}

function getSelectedVersionOption(
  group: ResourceRefOptionGroup | null,
  value: ResourceRef | null,
): ResourceRefSelectOption | null {
  if (!group || !value) {
    return null;
  }

  return group.versions.find((option) => option.version === value.version) ?? null;
}

function getResourceSearchOptions(
  groups: readonly ResourceRefOptionGroup[],
): SearchableSelectOption[] {
  return groups.map((group) => ({
    description: `${group.key} · ${group.versions.length} version${group.versions.length === 1 ? "" : "s"}`,
    keywords: [group.key, ...(group.keywords ?? [])],
    label: group.label,
    value: group.key,
  }));
}

export function ResourceRefSelect({
  className,
  description = "Choose a resource key and optionally pin a published version for this binding.",
  disabled = false,
  emptyDescription = "Publish at least one resource before binding it here.",
  emptyTitle = "No resources available",
  label = "Resource binding",
  onChange,
  options = [],
  resourceLabel = "Resource",
  resourcePlaceholder = "Select resource",
  searchPlaceholder = "Search resources...",
  value,
  versionLabel = "Version",
  ...props
}: ResourceRefSelectProps) {
  const versionFieldId = useId();
  const groupedOptions = useMemo(() => groupResourceOptions(options), [options]);
  const resourceOptions = useMemo(
    () => getResourceSearchOptions(groupedOptions),
    [groupedOptions],
  );
  const selectedGroup = useMemo(
    () => getSelectedGroup(groupedOptions, value),
    [groupedOptions, value],
  );
  const selectedVersionOption = useMemo(
    () => getSelectedVersionOption(selectedGroup, value),
    [selectedGroup, value],
  );

  const selectedPreviewOption = selectedVersionOption ?? selectedGroup?.versions[0] ?? null;
  const hasStaleSelection = Boolean(
    value?.key && (!selectedGroup || (value.version != null && !selectedVersionOption)),
  );
  const versionSelectValue = !selectedGroup
    ? NO_VERSION_OPTION
    : value?.version == null
      ? LATEST_VERSION_OPTION
      : selectedVersionOption
        ? String(selectedVersionOption.version)
        : STALE_VERSION_OPTION;

  return (
    <Card className={cn(className)} {...props}>
      <CardHeader>
        <CardTitle>{label}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {groupedOptions.length === 0 ? (
          <Alert>
            <AlertTitle>{emptyTitle}</AlertTitle>
            <AlertDescription>{emptyDescription}</AlertDescription>
          </Alert>
        ) : null}

        {hasStaleSelection ? (
          <Alert>
            <AlertTitle>Current binding is unavailable</AlertTitle>
            <AlertDescription>
              The saved resource key or version is not present in the current catalog. Pick a
              different resource or version to continue.
            </AlertDescription>
          </Alert>
        ) : null}

        <div className="grid gap-4 md:grid-cols-2">
          <div className="flex flex-col gap-2">
            <Label>{resourceLabel}</Label>
            <SearchableSelect
              disabled={disabled || resourceOptions.length === 0}
              emptyText="No matching resources found."
              options={resourceOptions}
              placeholder={resourcePlaceholder}
              searchPlaceholder={searchPlaceholder}
              value={value?.key ?? ""}
              onValueChange={(nextKey) => {
                const nextGroup = groupedOptions.find((group) => group.key === nextKey);
                const nextVersion = nextGroup?.versions[0]?.version ?? null;

                onChange(nextGroup ? { key: nextGroup.key, version: nextVersion } : null);
              }}
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor={versionFieldId}>{versionLabel}</Label>
            <Select
              disabled={disabled || !selectedGroup}
              value={versionSelectValue}
              onValueChange={(nextValue) => {
                if (!selectedGroup) {
                  return;
                }

                onChange({
                  key: selectedGroup.key,
                  version:
                    nextValue === LATEST_VERSION_OPTION ? null : Number.parseInt(nextValue, 10),
                });
              }}
            >
              <SelectTrigger aria-label={versionLabel} id={versionFieldId}>
                <SelectValue placeholder="Select version" />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  <SelectItem disabled value={NO_VERSION_OPTION}>
                    Select version
                  </SelectItem>
                  {hasStaleSelection && selectedGroup && value?.version != null ? (
                    <SelectItem disabled value={STALE_VERSION_OPTION}>
                      Saved version unavailable (v{value.version})
                    </SelectItem>
                  ) : null}
                  <SelectItem value={LATEST_VERSION_OPTION}>Latest published version</SelectItem>
                  {selectedGroup?.versions.map((option) => (
                    <SelectItem key={`${option.key}-${option.version}`} value={String(option.version)}>
                      {formatVersionLabel(option.version)}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
            <p className="text-sm text-muted-foreground">
              {selectedGroup
                ? `${selectedGroup.versions.length} published version${selectedGroup.versions.length === 1 ? " is" : "s are"} available for ${selectedGroup.key}.`
                : "Select a resource key before pinning a specific version."}
            </p>
          </div>
        </div>

        <Separator />

        <div className="flex flex-col gap-3 rounded-md border border-dashed bg-muted/20 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline">{value?.key || "No resource selected"}</Badge>
            <Badge variant="outline">
              {value ? formatVersionLabel(value.version) : "Version pending"}
            </Badge>
            {selectedPreviewOption?.status ? (
              <Badge variant="secondary" className="capitalize">
                {selectedPreviewOption.status.replace(/_/g, " ")}
              </Badge>
            ) : null}
          </div>
          <p className="text-sm text-muted-foreground">
            {selectedPreviewOption
              ? `${selectedPreviewOption.label} is bound through ${value?.version == null ? "the latest published version" : `version ${value.version}`}.`
              : "Choose a resource key and version to replace raw versioned-ref text entry with a structured binding control."}
          </p>
          {value ? (
            <div>
              <Button type="button" variant="outline" onClick={() => onChange(null)}>
                Clear binding
              </Button>
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}
