import { FileCheck2, PlayCircle, Save } from "lucide-react";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";

import { PageContextBar } from "@/components/shared/page-context-bar";
import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useModelConnections } from "@/hooks/use-model-connections";
import {
  useCreateWorkflowPackage,
  useDeleteWorkflowPackageSecretBinding,
  useTools,
  useUpdateWorkflowPackage,
  useUpsertWorkflowPackageSecretBinding,
  useValidateWorkflowPackageManifest,
  useWorkflowPackage,
  useWorkflowPackageManifest,
  useWorkflowPackageSecretBindings,
} from "@/hooks/use-workflow-packages";
import { formatDateTime } from "@/lib/format";
import {
  createWorkflowPackageDraft,
  mapBackendDiagnostics,
  packageDraftFromManifestSource,
  validateWorkflowPackageDraft,
  workflowPackageDraftToManifestSource,
  type WorkflowPackageDraft,
  type WorkflowPackageEditorIssue,
} from "@/lib/platform-authoring/workflow-packages/manifest";

import {
  AgentsTab,
  CapabilityProfilesTab,
  EditorSkeleton,
  ExportsTab,
  ManifestBlockingState,
  OverviewEditor,
  OutputSchemasTab,
  PrivateMcpTab,
  SecretBindingsTab,
  WorkflowYamlTab,
} from "./editor-sections";
import {
  collectSecretReferenceKeys,
  connectionKindLabel,
  diagnosticToAuthoringTarget,
  editorTabs,
  manifestIdentity,
  packageSubtitle,
  packageTitle,
  type DiagnosticTarget,
  type WorkflowPackageEditorTab,
} from "./editor-sections.shared";

function getWorkflowPackageEditorScrollElement() {
  return document.querySelector<HTMLElement>(
    '[data-testid="workflow-package-editor-shell"] [data-testid="workspace-page-shell-body"]',
  );
}

export function WorkflowPackageEditorPage() {
  const navigate = useNavigate();
  const { packageId } = useParams<{ packageId: string }>();
  const isNew = packageId === undefined;
  const packageQuery = useWorkflowPackage(isNew ? undefined : packageId);
  const manifestQuery = useWorkflowPackageManifest(
    isNew ? undefined : packageId,
  );
  const workflowPackage = packageQuery.data;
  const pendingTabScrollTop = useRef<number | null>(null);
  const [activeTab, setActiveTab] =
    useState<WorkflowPackageEditorTab>("overview");
  const [draft, setDraft] = useState<WorkflowPackageDraft>(() =>
    createWorkflowPackageDraft(),
  );
  const [isDirty, setIsDirty] = useState(false);
  const [launchConfirmationOpen, setLaunchConfirmationOpen] = useState(false);
  const [issues, setIssues] = useState<WorkflowPackageEditorIssue[]>([]);
  const [diagnosticTarget, setDiagnosticTarget] =
    useState<DiagnosticTarget>(null);
  const [initializedManifestIdentity, setInitializedManifestIdentity] =
    useState<string | null>(isNew ? "new" : null);
  const createPackage = useCreateWorkflowPackage();
  const updatePackage = useUpdateWorkflowPackage();
  const validatePackage = useValidateWorkflowPackageManifest();
  const modelConnectionsQuery = useModelConnections();
  const toolsQuery = useTools();
  const secretBindingsQuery = useWorkflowPackageSecretBindings(
    isNew ? undefined : packageId,
  );
  const upsertSecretBinding = useUpsertWorkflowPackageSecretBinding();
  const deleteSecretBinding = useDeleteWorkflowPackageSecretBinding();

  const selectEditorTab = (tab: WorkflowPackageEditorTab) => {
    pendingTabScrollTop.current =
      getWorkflowPackageEditorScrollElement()?.scrollTop ?? null;
    setActiveTab(tab);
  };

  useLayoutEffect(() => {
    const scrollTop = pendingTabScrollTop.current;
    if (scrollTop === null) {
      return;
    }
    pendingTabScrollTop.current = null;
    const editorShell = getWorkflowPackageEditorScrollElement();
    if (!editorShell) {
      return;
    }
    editorShell.scrollTop = scrollTop;
    const frame = window.requestAnimationFrame(() => {
      editorShell.scrollTop = scrollTop;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [activeTab]);

  const parsedManifest = useMemo(() => {
    if (isNew || !manifestQuery.data) {
      return null;
    }
    return packageDraftFromManifestSource(manifestQuery.data.manifestSource);
  }, [isNew, manifestQuery.data]);

  useEffect(() => {
    if (isNew) {
      if (initializedManifestIdentity !== "new") {
        setDraft(createWorkflowPackageDraft());
        setIssues([]);
        setDiagnosticTarget(null);
        setInitializedManifestIdentity("new");
        setIsDirty(false);
      }
      return;
    }
    if (
      !manifestQuery.data ||
      !parsedManifest ||
      parsedManifest.errors.length > 0
    ) {
      return;
    }
    const nextIdentity = manifestIdentity(manifestQuery.data);
    if (
      initializedManifestIdentity === nextIdentity ||
      (isDirty && initializedManifestIdentity !== null)
    ) {
      return;
    }
    setDraft(parsedManifest.draft);
    setIssues([]);
    setDiagnosticTarget(null);
    setInitializedManifestIdentity(nextIdentity);
    setIsDirty(false);
  }, [
    initializedManifestIdentity,
    isDirty,
    isNew,
    manifestQuery.data,
    parsedManifest,
  ]);

  const headerDescription =
    workflowPackage?.description ||
    (isNew ? "Create a package manifest." : "Edit package-local resources.");
  const localIssues = useMemo(
    () => validateWorkflowPackageDraft(draft),
    [draft],
  );
  const combinedIssues = [...localIssues, ...issues];
  const modelConnectionOptions = (modelConnectionsQuery.data?.items ?? []).map(
    (connection) => ({
      description: `${connection.modelId} ${connection.apiStyle} ${connectionKindLabel(connection.connectionKind)}`,
      label: connection.name,
      value: connection.key,
    }),
  );
  const referencedSecretKeys = useMemo(
    () => collectSecretReferenceKeys(draft.spec.workflows),
    [draft.spec.workflows],
  );
  const isSaving = createPackage.isPending || updatePackage.isPending;
  const manifestParseErrors = parsedManifest?.errors ?? [];
  const manifestLoadError =
    manifestQuery.error instanceof Error
      ? manifestQuery.error.message
      : "Failed to load package manifest.";
  const packageLoadError =
    packageQuery.error instanceof Error
      ? packageQuery.error.message
      : "Failed to load workflow package.";
  const editorBlocker =
    !isNew && packageQuery.isError
      ? {
          errors: [packageLoadError],
          title: "Package identity could not be loaded",
        }
      : !isNew && manifestQuery.isError
        ? {
            errors: [manifestLoadError],
            title: "Package manifest could not be loaded",
          }
        : !isNew && manifestParseErrors.length > 0
          ? {
              errors: manifestParseErrors,
              title: "Package manifest could not be parsed",
            }
          : null;
  const isEditorBlocked = editorBlocker !== null;
  const manifestHash = workflowPackage?.manifestHash?.slice(0, 12) ?? "Draft";
  const compiledHash = workflowPackage?.compiledHash?.slice(0, 12) ?? "Pending";
  const contextStatusItems = [
    {
      label: "Mode",
      tone: isNew ? ("warning" as const) : ("success" as const),
      value: isNew ? "New draft" : "Saved package",
    },
    {
      label: "Draft",
      tone: isDirty ? ("warning" as const) : ("neutral" as const),
      value: isDirty ? "Unsaved" : "Clean",
    },
    {
      label: "Diagnostics",
      tone:
        combinedIssues.length > 0 ? ("danger" as const) : ("success" as const),
      value:
        combinedIssues.length > 0 ? String(combinedIssues.length) : "Clear",
    },
  ];

  const updateDraft = (nextDraft: WorkflowPackageDraft) => {
    setIsDirty(true);
    setDraft(nextDraft);
  };

  const clearTransientEditorState = () => {
    setIssues([]);
    setDiagnosticTarget(null);
    setIsDirty(false);
  };

  const discardLoadedDraftState = () => {
    clearTransientEditorState();
    setInitializedManifestIdentity(null);
  };

  const confirmDiscardUnsavedChanges = (action: string) => {
    if (!isDirty) {
      return true;
    }
    return window.confirm(
      `You have unsaved changes. Discard them and ${action}?`,
    );
  };

  const retryManifestLoad = () => {
    if (!confirmDiscardUnsavedChanges("retry the manifest load")) {
      return;
    }
    if (isDirty) {
      discardLoadedDraftState();
    }
    if (packageQuery.isError) {
      void packageQuery.refetch();
    }
    void manifestQuery.refetch();
  };

  const openImportWorkspace = () => {
    if (!confirmDiscardUnsavedChanges("open the import workspace")) {
      return;
    }
    navigate("/workflow-packages/import");
  };

  const focusIssue = (issue: WorkflowPackageEditorIssue) => {
    const target = diagnosticToAuthoringTarget(issue.field);
    setDiagnosticTarget(target);
    setActiveTab(target.tab);
    window.setTimeout(() => {
      const field =
        document.querySelector<HTMLElement>(
          `[data-field="${CSS.escape(issue.field)}"]`,
        ) ??
        document.querySelector<HTMLElement>(
          `[data-field="${CSS.escape(target.field)}"]`,
        );
      field?.focus();
      field?.scrollIntoView({ block: "center", inline: "nearest" });
    }, 50);
  };

  const saveSecretBinding = async (key: string, value: string) => {
    if (!packageId) {
      toast.error("Save the package before binding secrets.");
      return;
    }
    try {
      await upsertSecretBinding.mutateAsync({
        key,
        packageId,
        payload: { value },
      });
      toast.success(`Secret binding ${key} saved`);
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Secret binding save failed.",
      );
    }
  };

  const removeSecretBinding = async (key: string) => {
    if (!packageId) {
      return;
    }
    try {
      await deleteSecretBinding.mutateAsync({ key, packageId });
      toast.success(`Secret binding ${key} deleted`);
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : "Secret binding delete failed.",
      );
    }
  };

  const validateCurrentDraft = async () => {
    if (isEditorBlocked) {
      toast.error("Load a valid package manifest before validating.");
      return;
    }
    const manifestSource = workflowPackageDraftToManifestSource(draft);
    const result = await validatePackage.mutateAsync({ manifestSource });
    const backendIssues = mapBackendDiagnostics(result.diagnostics);
    setIssues(backendIssues);
    if (backendIssues[0]) {
      focusIssue(backendIssues[0]);
    }
    toast[backendIssues.some((issue) => issue.issue) ? "warning" : "success"](
      backendIssues.length > 0
        ? "Package validation returned diagnostics"
        : "Package validation passed",
    );
  };

  const savePackage = async () => {
    if (isEditorBlocked) {
      toast.error("Load a valid package manifest before saving.");
      return;
    }
    const nextIssues = validateWorkflowPackageDraft(draft);
    setIssues(nextIssues);
    if (nextIssues[0]) {
      focusIssue(nextIssues[0]);
      toast.error("Resolve package editor validation before saving.");
      return;
    }
    const manifestSource = workflowPackageDraftToManifestSource(draft);
    if (isNew) {
      const created = await createPackage.mutateAsync({ manifestSource });
      clearTransientEditorState();
      toast.success("Workflow package created");
      navigate(`/workflow-packages/${created.id}`);
      return;
    }
    if (packageId) {
      await updatePackage.mutateAsync({
        packageId,
        payload: { manifestSource },
      });
      clearTransientEditorState();
      toast.success("Workflow package saved");
    }
  };

  const launchSavedPackage = () => {
    if (!packageId) {
      return;
    }
    setLaunchConfirmationOpen(false);
    navigate(`/workflow-packages/${packageId}/run`);
  };

  const requestLaunchSavedPackage = () => {
    if (!packageId) {
      return;
    }
    if (isDirty) {
      setLaunchConfirmationOpen(true);
      return;
    }
    launchSavedPackage();
  };

  if (!isNew && (packageQuery.isPending || manifestQuery.isPending)) {
    return (
      <WorkspacePageShell
        bodyAriaLabel="Workflow package authoring workspace"
        contextBar={
          <PageContextBar
            description="Loading saved package manifest and authoring resources."
            title="Workflow Package"
          />
        }
        testId="workflow-package-editor-shell"
      >
        <EditorSkeleton />
      </WorkspacePageShell>
    );
  }

  return (
    <>
      <Tabs
        orientation="vertical"
        value={activeTab}
        onValueChange={(value) =>
          selectEditorTab(value as WorkflowPackageEditorTab)
        }
        className="contents"
      >
        <WorkspacePageShell
          bodyAriaLabel="Workflow package authoring workspace"
          bodyClassName="gap-4"
          contextBar={
            <div data-testid="workflow-package-context-bar">
              <div
                className="rounded-xl border border-border/70 bg-card/95 px-3 py-2.5 text-card-foreground shadow-sm backdrop-blur"
                data-testid="workflow-package-editor-compact-header"
              >
                <div
                  className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-start sm:justify-between"
                  data-testid="workflow-package-editor-header-top-row"
                >
                  <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
                    <h1
                      id="workflow-package-editor-title"
                      className="min-w-0 text-xl font-semibold tracking-tight"
                    >
                      {packageTitle(workflowPackage, isNew)}
                    </h1>

                    <span className="min-w-0 break-all font-mono text-xs text-muted-foreground">
                      {packageSubtitle(workflowPackage, isNew)}
                    </span>
                  </div>
                  <div className="flex shrink-0 flex-wrap items-center gap-2 sm:justify-end">
                    <Button
                      aria-label="Save package"
                      className="cursor-pointer"
                      disabled={isSaving || isEditorBlocked}
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => void savePackage()}
                    >
                      <Save data-icon="inline-start" />
                      Save
                    </Button>
                    <Button
                      aria-label="Validate package"
                      className="cursor-pointer"
                      disabled={validatePackage.isPending || isEditorBlocked}
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => void validateCurrentDraft()}
                    >
                      <FileCheck2 data-icon="inline-start" />
                      Validate
                    </Button>
                    <Button
                      aria-label="Launch workflow package"
                      className="cursor-pointer"
                      disabled={isNew || isEditorBlocked}
                      type="button"
                      size="sm"
                      onClick={requestLaunchSavedPackage}
                    >
                      <PlayCircle data-icon="inline-start" />
                      Launch
                    </Button>
                  </div>
                </div>
                <div
                  className="mt-1.5 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground"
                  data-testid="workflow-package-editor-header-meta-row"
                >
                  <span className="min-w-0 truncate">{headerDescription}</span>
                  <span>
                    <span className="font-medium text-foreground">Manifest</span>{" "}
                    <span className="font-mono">{manifestHash}</span>
                  </span>
                  <span>
                    <span className="font-medium text-foreground">Compiled</span>{" "}
                    <span className="font-mono">{compiledHash}</span>
                  </span>
                  {workflowPackage ? (
                    <>
                      <span>
                        <span className="font-medium text-foreground">Updated</span>{" "}
                        {formatDateTime(workflowPackage.updatedAt)}
                      </span>
                    </>
                  ) : null}
                </div>
                <div
                  className="mt-1.5 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-xs"
                  data-testid="workflow-package-editor-header-status-row"
                >
                  {contextStatusItems.map((item, index) => (
                    <span
                      className="flex min-w-0 items-center gap-1.5"
                      key={item.label}
                    >

                      <span className="text-muted-foreground">{item.label}</span>
                      <span
                        className={
                          item.tone === "danger"
                            ? "font-medium text-destructive"
                            : item.tone === "warning"
                              ? "font-medium text-foreground"
                              : "font-medium text-foreground"
                        }
                      >
                        {item.value}
                      </span>
                    </span>
                  ))}
                </div>
              </div>
            </div>
          }
          leftRail={
            editorBlocker ? undefined : (
              <div
                className="flex max-h-64 min-w-0 flex-col gap-2 overflow-y-auto rounded-xl border bg-card/80 p-2 shadow-sm lg:max-h-full"
                data-testid="workflow-package-section-nav"
              >
                <div className="px-2 py-1">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Authoring Sections
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Package-local resources only; import and launch stay on their
                    dedicated routes.
                  </p>
                </div>
                <TabsList
                  aria-label="Workflow package editor sections"
                  className="h-auto w-full justify-start bg-transparent p-0"
                >
                  {editorTabs.map((tab) => {
                    const Icon = tab.icon;
                    return (
                      <TabsTrigger
                        key={tab.value}
                        value={tab.value}
                        aria-label={`${tab.label} tab`}
                        className="h-auto justify-start gap-3 whitespace-normal px-3 py-2 text-left"
                        onClick={() => selectEditorTab(tab.value)}
                      >
                        <Icon aria-hidden="true" />
                        <span className="flex min-w-0 flex-col gap-0.5">
                          <span>{tab.label}</span>
                          <span className="line-clamp-2 text-[11px] font-normal leading-4 text-muted-foreground">
                            {tab.description}
                          </span>
                        </span>
                      </TabsTrigger>
                    );
                  })}
                </TabsList>
              </div>
            )
          }
          leftRailAriaLabel="Workflow package authoring sections"
          leftRailClassName="lg:sticky lg:top-3 lg:w-72"
          testId="workflow-package-editor-shell"
        >
          {editorBlocker ? (
            <ManifestBlockingState
              errors={editorBlocker.errors}
              loading={packageQuery.isFetching || manifestQuery.isFetching}
              onRetry={retryManifestLoad}
              title={editorBlocker.title}
            />
          ) : (
            <>
              {packageDraftFromManifestSource(
                workflowPackageDraftToManifestSource(draft),
              ).errors.length > 0 ? (
                <Alert variant="destructive">
                  <AlertTitle>Generated manifest cannot be parsed</AlertTitle>
                  <AlertDescription>
                    Review package-local resource fields before saving.
                  </AlertDescription>
                </Alert>
              ) : null}
              <div className="min-w-0">
                <TabsContent value="overview" className="mt-0">
                  <OverviewEditor
                    draft={draft}
                    issues={combinedIssues}
                    isNew={isNew}
                    onChange={updateDraft}
                  />
                </TabsContent>
                <TabsContent value="agents" className="mt-0">
                  <AgentsTab
                    diagnosticTarget={diagnosticTarget}
                    draft={draft}
                    issues={combinedIssues}
                    modelConnectionOptions={modelConnectionOptions}
                    onChange={updateDraft}
                  />
                </TabsContent>
                <TabsContent value="output-schemas" className="mt-0">
                  <OutputSchemasTab
                    draft={draft}
                    issues={combinedIssues}
                    onChange={updateDraft}
                  />
                </TabsContent>
                <TabsContent value="capability-profiles" className="mt-0">
                  <CapabilityProfilesTab
                    draft={draft}
                    issues={combinedIssues}
                    onChange={updateDraft}
                    tools={(toolsQuery.data?.items ?? []).map((tool) => ({
                      description: tool.description,
                      displayName: tool.displayName,
                      key: tool.key,
                    }))}
                    toolsError={
                      toolsQuery.error instanceof Error
                        ? toolsQuery.error.message
                        : null
                    }
                    toolsLoading={toolsQuery.isPending}
                  />
                </TabsContent>
                <TabsContent value="private-mcp" className="mt-0">
                  <PrivateMcpTab
                    draft={draft}
                    issues={combinedIssues}
                    onChange={updateDraft}
                  />
                </TabsContent>
                <TabsContent value="workflow-yaml" className="mt-0">
                  <WorkflowYamlTab
                    draft={draft}
                    issues={combinedIssues}
                    onChange={updateDraft}
                  />
                </TabsContent>
                <TabsContent value="secret-bindings" className="mt-0">
                  <SecretBindingsTab
                    bindings={secretBindingsQuery.data?.items ?? []}
                    bindingsError={
                      secretBindingsQuery.error instanceof Error
                        ? secretBindingsQuery.error.message
                        : null
                    }
                    bindingsLoading={secretBindingsQuery.isPending}
                    deleting={deleteSecretBinding.isPending}
                    onDelete={removeSecretBinding}
                    onSave={saveSecretBinding}
                    packageId={packageId}
                    referencedSecretKeys={referencedSecretKeys}
                    saving={upsertSecretBinding.isPending}
                  />
                </TabsContent>
                <TabsContent value="exports" className="mt-0">
                  <ExportsTab
                    draft={draft}
                    onOpenImportWorkspace={openImportWorkspace}
                    packageId={packageId}
                  />
                </TabsContent>
              </div>
            </>
          )}
        </WorkspacePageShell>
      </Tabs>
      <Dialog
        open={launchConfirmationOpen}
        onOpenChange={setLaunchConfirmationOpen}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Launch saved package?</DialogTitle>
            <DialogDescription>
              This will open the launch page for the last saved version of this
              package. Unsaved editor changes are excluded until you save them.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setLaunchConfirmationOpen(false)}
            >
              Cancel
            </Button>
            <Button type="button" onClick={launchSavedPackage}>
              <PlayCircle data-icon="inline-start" />
              Launch saved package
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
