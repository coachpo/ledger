import { Link } from "react-router";
import { ArrowLeft, SearchX } from "lucide-react";

import { EmptyStatePanel } from "@/components/shared/empty-state-panel";
import { ProvenanceBadge } from "@/components/shared/provenance-badge";
import { ResourceStatusStrip } from "@/components/shared/resource-status-strip";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <section
      className="min-h-[calc(100vh-3rem)] px-4 py-8 sm:px-6 sm:py-10 lg:px-8"
      data-testid="not-found-page"
    >
      <div
        className="mx-auto flex w-full max-w-6xl flex-col gap-6"
        data-testid="not-found-content"
      >
        <header className="flex w-full min-w-0 flex-col gap-4">
          <div className="flex min-w-0 flex-col gap-2">
            <h1 className="text-2xl font-semibold leading-tight tracking-tight text-foreground sm:text-[1.75rem]">
              Page not found
            </h1>
            <p
              className="max-w-4xl text-sm leading-6 text-muted-foreground"
              data-testid="not-found-description"
            >
              The requested path did not match any registered SignalDeck route
              metadata.
            </p>
          </div>
          <div className="flex w-full min-w-0 flex-col gap-3">
            <div className="w-full min-w-0" data-testid="not-found-status">
              <ResourceStatusStrip
                className="w-full max-w-none justify-start flex-wrap"
                items={[
                  { label: "State", tone: "warning", value: "Not found" },
                  {
                    label: "Fallback",
                    tone: "neutral",
                    value: "Workflow packages",
                  },
                ]}
              />
            </div>
            <div
              className="flex w-full min-w-0 flex-wrap items-center gap-2 text-xs text-muted-foreground"
              data-testid="not-found-meta"
            >
              <ProvenanceBadge detail="catch-all" label="Route owner" />
              <ProvenanceBadge
                detail="product fallback"
                label="Shell"
                tone="verified"
              />
            </div>
          </div>
        </header>
        <EmptyStatePanel
          className="w-full max-w-none"
          action={
            <Button asChild size="sm">
              <Link to="/workflow-packages">
                <ArrowLeft data-icon="inline-start" />
                Open workflow packages
              </Link>
            </Button>
          }
          description="The workspace path you requested is not registered in SignalDeck. Return to a known route to continue your workflow."
          icon={<SearchX className="size-4" />}
          title="Unknown route"
          tone="warning"
        />
      </div>
    </section>
  );
}
