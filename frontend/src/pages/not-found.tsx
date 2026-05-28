import { Link } from "react-router";
import { ArrowLeft, SearchX } from "lucide-react";

import { EmptyStatePanel } from "@/components/shared/empty-state-panel";
import { PageContextBar } from "@/components/shared/page-context-bar";
import { ProvenanceBadge } from "@/components/shared/provenance-badge";
import { ResourceStatusStrip } from "@/components/shared/resource-status-strip";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <section className="p-4" data-testid="not-found-page">
      <div className="mx-auto flex max-w-2xl flex-col gap-3">
        <PageContextBar
          description="The requested path did not match any registered SignalDeck route metadata."
          meta={
            <div className="flex flex-wrap items-center gap-2">
              <ProvenanceBadge detail="catch-all" label="Route owner" />
              <ProvenanceBadge detail="product fallback" label="Shell" tone="verified" />
            </div>
          }
          status={
            <ResourceStatusStrip
              items={[
                { label: "State", tone: "warning", value: "Not found" },
                { label: "Fallback", tone: "neutral", value: "Workflow packages" },
              ]}
            />
          }
          title="Page not found"
        />
        <EmptyStatePanel
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
