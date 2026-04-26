import { useState } from "react";
import { RefreshCcw } from "lucide-react";
import { toast } from "sonner";

import { useSeedTemplates } from "@/hooks/use-templates";
import type { TextTemplateSeedRead } from "@/lib/types/text-template";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";

export function TemplateSeedPage() {
  const seedMutation = useSeedTemplates();
  const [confirmChecked, setConfirmChecked] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [summary, setSummary] = useState<TextTemplateSeedRead | null>(null);

  const handleSeed = async () => {
    try {
      const result = await seedMutation.mutateAsync({ confirm: true });
      setSummary(result);
      setConfirmChecked(false);
      setDialogOpen(false);
      toast.success("Starter workspace reset complete");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to reset starter workspace");
    }
  };

  return (
    <div className="flex flex-col gap-4 p-4" data-testid="template-seed-page">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold tracking-tight">Reset Workspace</h1>
        <p className="text-sm text-muted-foreground">
          Run the existing starter workspace reset-and-seed flow from the Web UI.
        </p>
      </div>

      <Alert variant="destructive">
        <AlertTitle>Destructive action</AlertTitle>
        <AlertDescription>
          <p>
            This runs <code>backend/app/reset_seed.py</code>, recreates the database,
            and replaces the current workspace with the starter seed data.
          </p>
        </AlertDescription>
      </Alert>

      <Card>
        <CardHeader>
          <CardTitle>Starter workspace seed</CardTitle>
          <CardDescription>
            The seeded templates come with the same starter portfolio, reports,
            workflows, agents, and schemas as the backend reset flow.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <div className="flex items-start gap-3">
            <Checkbox
              id="template-seed-confirm"
              checked={confirmChecked}
              disabled={seedMutation.isPending}
              onCheckedChange={(checked) => setConfirmChecked(checked === true)}
            />
            <label
              htmlFor="template-seed-confirm"
              className="text-sm leading-relaxed text-foreground"
            >
              I understand this will wipe the current data and reseed the starter workspace.
            </label>
          </div>
        </CardContent>
        <CardFooter className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-muted-foreground">
            Continue only if you want the exact starter data from the existing reset seed script.
          </p>
          <AlertDialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <AlertDialogTrigger asChild>
              <Button
                data-testid="template-seed-trigger"
                disabled={!confirmChecked || seedMutation.isPending}
                variant="destructive"
              >
                <RefreshCcw data-icon="inline-start" />
                {seedMutation.isPending ? "Seeding..." : "Reset and seed"}
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Reset the current workspace?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will drop the current Ledger data and recreate the starter workspace.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel disabled={seedMutation.isPending}>Cancel</AlertDialogCancel>
                <AlertDialogAction asChild>
                  <Button
                    disabled={seedMutation.isPending}
                    onClick={(event) => {
                      event.preventDefault();
                      void handleSeed();
                    }}
                    variant="destructive"
                  >
                    {seedMutation.isPending ? "Seeding..." : "Confirm reset"}
                  </Button>
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </CardFooter>
      </Card>

      {summary ? (
        <Card data-testid="template-seed-summary">
          <CardHeader>
            <CardTitle>Seed complete</CardTitle>
            <CardDescription>
              The starter workspace was recreated successfully.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 text-sm">
            <div className="flex flex-col gap-1">
              <p className="font-medium text-foreground">Template names</p>
              <ul className="list-disc pl-5">
                {summary.templateNames.map((templateName) => (
                  <li key={templateName}>{templateName}</li>
                ))}
              </ul>
            </div>
            <p className="text-muted-foreground">
              Portfolio: {summary.portfolioSlugs.join(", ")} · Workflows: {summary.workflowKeys.join(", ")}
            </p>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
