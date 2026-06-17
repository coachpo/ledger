import { Link } from "react-router";
import { ArrowLeft, SearchX } from "lucide-react";

import { CanonicalErrorPage } from "@/components/shared/canonical-error-page";
import { ProvenanceBadge } from "@/components/shared/provenance-badge";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <CanonicalErrorPage
      action={
        <Button asChild size="sm">
          <Link to="/workflow-packages">
            <ArrowLeft data-icon="inline-start" />
            Open workflow packages
          </Link>
        </Button>
      }
      contentClassName="min-h-0 justify-start"
      contentTestId="not-found-content"
      description="The requested path did not match any registered SignalDeck route metadata."
      descriptionTestId="not-found-description"
      icon={<SearchX className="size-4" />}
      meta={
        <>
          <ProvenanceBadge detail="catch-all" label="Route owner" />
          <ProvenanceBadge
            detail="product fallback"
            label="Shell"
            tone="verified"
          />
        </>
      }
      metaTestId="not-found-meta"
      panelDescription="The workspace path you requested is not registered in SignalDeck. Return to a known route to continue your workflow."
      panelTestId="not-found-panel"
      panelTitle="Unknown route"
      rootClassName="min-h-[calc(100vh-3rem)]"
      statusItems={[
        { label: "State", tone: "warning", value: "Not found" },
        {
          label: "Fallback",
          tone: "neutral",
          value: "Workflow packages",
        },
      ]}
      statusTestId="not-found-status"
      testId="not-found-page"
      title="Page not found"
      tone="warning"
    />
  );
}
