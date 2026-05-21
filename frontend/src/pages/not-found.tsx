import { Link } from "react-router";
import { ArrowLeft, SearchX } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export function NotFoundPage() {
  return (
    <section className="p-4" data-testid="not-found-page">
      <Card className="mx-auto max-w-2xl">
        <CardContent className="flex flex-col items-center gap-4 px-6 py-12 text-center">
          <div className="flex size-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
            <SearchX aria-hidden="true" className="size-6" />
          </div>
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
              SignalDeck route
            </p>
            <h1 className="text-2xl font-semibold tracking-tight">Page not found</h1>
            <p className="max-w-md text-sm text-muted-foreground">
              The workspace path you requested is not registered in SignalDeck. Return to a known route to continue your workflow.
            </p>
          </div>
          <Button asChild size="sm">
            <Link to="/workflow-packages">
              <ArrowLeft aria-hidden="true" className="size-4" />
              Open workflow packages
            </Link>
          </Button>
        </CardContent>
      </Card>
    </section>
  );
}
