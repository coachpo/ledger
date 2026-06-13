import { AlertCircle, Loader2, Save, Trash2 } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/components/ui/utils";

export type SavedRuntimeInputRegistryEntry = {
  id: number;
  label: string;
  mode: "history" | "preset";
  sourceLabel: string;
  stale: boolean;
  staleReasonLines: readonly string[];
};

type SavedRuntimeInputRegistryPanelProps = {
  capMessage: string;
  createDisabled: boolean;
  createPending: boolean;
  deletePending?: boolean;
  disableTabsWhenUnavailable?: boolean;
  entryLabelNoun?: string;
  error: Error | null;
  errorTitle: string;
  helperCopy: string;
  historyEmptyMessage: string;
  historyEntries: readonly SavedRuntimeInputRegistryEntry[];
  historyListClassName?: string;
  historyListTestId?: string;
  historySectionLabel?: string;
  loading: boolean;
  loadingMessage: string;
  presetEntries: readonly SavedRuntimeInputRegistryEntry[];
  presetEmptyMessage: string;
  presetListClassName?: string;
  presetNameInputId?: string;
  presetNameInputName?: string;
  presetNameLabel: string;
  presetNamePlaceholder: string;
  presetNameValue: string;
  presetLimit: number;
  presetSectionLabel?: string;
  rowTestIdPrefix?: string;
  saveLabel: string;
  showPresetNameLabel?: boolean;
  staleNoticeTitle: string;
  tabContentClassName?: string;
  tabsListClassName?: string;
  testId?: string;
  title: string;
  updatePending?: boolean;
  workflowBadgeFallback: string;
  workflowEnabled?: boolean;
  workflowKey: string;
  onCreate: () => void;
  onDelete: (entry: SavedRuntimeInputRegistryEntry) => void;
  onLoad: (entry: SavedRuntimeInputRegistryEntry) => void;
  onOverwrite: (entry: SavedRuntimeInputRegistryEntry) => void;
  onPresetNameChange: (value: string) => void;
};

type SavedRuntimeInputEntryRowProps = {
  actionsDisabled: boolean;
  deletePending: boolean;
  entry: SavedRuntimeInputRegistryEntry;
  entryLabelNoun: string;
  rowTestIdPrefix: string;
  staleNoticeTitle: string;
  updatePending: boolean;
  onDelete: (entry: SavedRuntimeInputRegistryEntry) => void;
  onLoad: (entry: SavedRuntimeInputRegistryEntry) => void;
  onOverwrite: (entry: SavedRuntimeInputRegistryEntry) => void;
};

function SavedRuntimeInputEntryRow({
  actionsDisabled,
  deletePending,
  entry,
  entryLabelNoun,
  rowTestIdPrefix,
  staleNoticeTitle,
  updatePending,
  onDelete,
  onLoad,
  onOverwrite,
}: SavedRuntimeInputEntryRowProps) {
  const actionEntryDescription =
    entry.mode === "preset"
      ? `saved runtime input preset ${entry.label}`
      : `${entry.mode} ${entryLabelNoun} ${entry.label}`;

  return (
    <div
      className="flex min-w-0 flex-col gap-2 rounded-lg border bg-background/60 p-3"
      data-testid={`${rowTestIdPrefix}-${entry.mode}-${entry.id}`}
    >
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 flex-col gap-1">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <p className="min-w-0 max-w-full truncate text-sm font-medium">{entry.label}</p>
            {entry.stale ? (
              <Badge className="border-chart-3/30 bg-chart-3/10 text-chart-3" variant="outline">
                Stale
              </Badge>
            ) : null}
          </div>
          <p className="text-xs text-muted-foreground">{entry.sourceLabel}</p>
        </div>
        <div className="flex w-full flex-wrap gap-2 sm:w-auto sm:justify-end">
          <Button
            aria-label={`Load ${actionEntryDescription}`}
            className="h-7 px-2 text-xs"
            disabled={actionsDisabled}
            size="sm"
            type="button"
            variant="outline"
            onClick={() => onLoad(entry)}
          >
            Load
          </Button>
          {entry.mode === "preset" ? (
            <>
              <Button
                aria-label={`Overwrite ${actionEntryDescription}`}
                className="h-7 px-2 text-xs"
                disabled={actionsDisabled || updatePending}
                size="sm"
                type="button"
                variant="outline"
                onClick={() => onOverwrite(entry)}
              >
                {updatePending ? <Loader2 className="animate-spin" data-icon="inline-start" /> : null}
                Overwrite
              </Button>
              <Button
                aria-label={`Delete ${actionEntryDescription}`}
                className="h-7 px-2 text-xs"
                disabled={actionsDisabled || deletePending}
                size="sm"
                type="button"
                variant="ghost"
                onClick={() => onDelete(entry)}
              >
                {deletePending ? (
                  <Loader2 className="animate-spin" data-icon="inline-start" />
                ) : (
                  <Trash2 className="size-3" data-icon="inline-start" />
                )}
                Delete
              </Button>
            </>
          ) : null}
        </div>
      </div>
      {entry.stale ? (
        <div className="rounded-md border border-chart-3/30 bg-chart-3/10 px-2 py-1 text-xs text-muted-foreground">
          <p className="font-medium text-foreground">{staleNoticeTitle}</p>
          {entry.staleReasonLines.length > 0 ? (
            <ul className="mt-1 flex list-disc flex-col gap-0.5 pl-4">
              {entry.staleReasonLines.map((reasonLine, reasonIndex) => (
                <li key={`${entry.id}-${reasonLine}-${reasonIndex}`}>{reasonLine}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function SavedRuntimeInputRegistryPanel(props: SavedRuntimeInputRegistryPanelProps) {
  const {
    capMessage,
    createDisabled,
    createPending,
    deletePending = false,
    disableTabsWhenUnavailable = false,
    entryLabelNoun = "input",
    error,
    errorTitle,
    helperCopy,
    historyEmptyMessage,
    historyEntries,
    historyListClassName,
    historyListTestId,
    historySectionLabel,
    loading,
    loadingMessage,
    onCreate,
    onDelete,
    onLoad,
    onOverwrite,
    onPresetNameChange,
    presetEntries,
    presetEmptyMessage,
    presetListClassName,
    presetNameInputId,
    presetNameInputName,
    presetNameLabel,
    presetNamePlaceholder,
    presetNameValue,
    presetLimit,
    presetSectionLabel,
    rowTestIdPrefix = "saved-runtime-input",
    saveLabel,
    showPresetNameLabel = false,
    staleNoticeTitle,
    tabContentClassName,
    tabsListClassName,
    testId,
    title,
    updatePending = false,
    workflowBadgeFallback,
    workflowEnabled = Boolean(props.workflowKey),
    workflowKey,
  } = props;

  const presetLimitReached = presetEntries.length >= presetLimit;
  const badgeLabel = workflowKey || workflowBadgeFallback;
  const tabsDisabled = disableTabsWhenUnavailable && !workflowEnabled;

  return (
    <div className="flex min-w-0 flex-col gap-3" data-testid={testId}>
      <div className="flex min-w-0 flex-col gap-1">
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">{title}</h3>
          <Badge variant="outline">{badgeLabel}</Badge>
        </div>
        <p className="text-xs text-muted-foreground">{helperCopy}</p>
      </div>
      {workflowEnabled && loading ? (
        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="size-3 animate-spin" />
          {loadingMessage}
        </p>
      ) : null}
      {workflowEnabled && error ? (
        <Alert variant="destructive">
          <AlertCircle />
          <AlertTitle>{errorTitle}</AlertTitle>
          <AlertDescription>{error.message}</AlertDescription>
        </Alert>
      ) : null}
      <Tabs className="min-w-0 gap-3" defaultValue="presets">
        <TabsList className={cn("w-full justify-start sm:w-fit", tabsListClassName)}>
          <TabsTrigger disabled={tabsDisabled} value="presets">
            Presets
            <Badge className="ml-1" variant="secondary">
              {presetEntries.length}/{presetLimit}
            </Badge>
          </TabsTrigger>
          <TabsTrigger disabled={tabsDisabled} value="history">
            History
            <Badge className="ml-1" variant="secondary">
              {historyEntries.length}/{presetLimit}
            </Badge>
          </TabsTrigger>
        </TabsList>
        <TabsContent className={cn("min-w-0 space-y-3", tabContentClassName)} value="presets">
          {presetSectionLabel ? (
            <div className="flex min-w-0 flex-wrap items-center justify-between gap-2 rounded-lg border bg-muted/10 px-3 py-2">
              <p className="text-xs font-medium text-muted-foreground">{presetSectionLabel}</p>
              <Badge variant="outline">{presetEntries.length} saved</Badge>
            </div>
          ) : null}
          <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-end">
            <div className="flex min-w-0 flex-1 flex-col gap-2">
              {showPresetNameLabel ? <Label htmlFor={presetNameInputId}>{presetNameLabel}</Label> : null}
              <Input
                aria-label={presetNameLabel}
                className="h-8 min-w-0 text-xs"
                disabled={!workflowEnabled}
                id={presetNameInputId}
                name={presetNameInputName}
                placeholder={presetNamePlaceholder}
                value={presetNameValue}
                onChange={(event) => onPresetNameChange(event.target.value)}
              />
            </div>
            <Button
              className="h-8 w-full text-xs sm:w-auto"
              disabled={createDisabled || createPending || presetLimitReached}
              size="sm"
              type="button"
              onClick={onCreate}
            >
              {createPending ? (
                <Loader2 className="animate-spin" data-icon="inline-start" />
              ) : (
                <Save data-icon="inline-start" />
              )}
              {saveLabel}
            </Button>
          </div>
          {workflowEnabled && presetLimitReached ? (
            <p className="text-xs text-destructive">{capMessage}</p>
          ) : null}
          {workflowEnabled && presetEntries.length === 0 ? (
            <p className="text-xs text-muted-foreground">{presetEmptyMessage}</p>
          ) : null}
          <div className={cn("flex min-w-0 flex-col gap-2", presetListClassName)}>
            {presetEntries.map((entry) => (
              <SavedRuntimeInputEntryRow
                actionsDisabled={!workflowEnabled}
                deletePending={deletePending}
                entry={entry}
                entryLabelNoun={entryLabelNoun}
                key={`${entry.mode}-${entry.id}`}
                rowTestIdPrefix={rowTestIdPrefix}
                staleNoticeTitle={staleNoticeTitle}
                updatePending={updatePending}
                onDelete={onDelete}
                onLoad={onLoad}
                onOverwrite={onOverwrite}
              />
            ))}
          </div>
        </TabsContent>
        <TabsContent className={cn("min-w-0 space-y-3", tabContentClassName)} value="history">
          {historySectionLabel ? (
            <div className="flex min-w-0 flex-wrap items-center justify-between gap-2 rounded-lg border bg-muted/10 px-3 py-2">
              <p className="text-xs font-medium text-muted-foreground">{historySectionLabel}</p>
              <Badge variant="outline">{historyEntries.length} saved</Badge>
            </div>
          ) : null}
          {workflowEnabled && historyEntries.length === 0 ? (
            <p className="text-xs text-muted-foreground">{historyEmptyMessage}</p>
          ) : null}
          <div
            className={cn("flex min-w-0 flex-col gap-2", historyListClassName)}
            data-testid={historyListTestId}
          >
            {historyEntries.map((entry) => (
              <SavedRuntimeInputEntryRow
                actionsDisabled={!workflowEnabled}
                deletePending={false}
                entry={entry}
                entryLabelNoun={entryLabelNoun}
                key={`${entry.mode}-${entry.id}`}
                rowTestIdPrefix={rowTestIdPrefix}
                staleNoticeTitle={staleNoticeTitle}
                updatePending={false}
                onDelete={onDelete}
                onLoad={onLoad}
                onOverwrite={onOverwrite}
              />
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
