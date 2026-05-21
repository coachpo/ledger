import { Link, isRouteErrorResponse, useRouteError } from "react-router";
import { AlertTriangle, Home } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

type RouteErrorDetails = {
  description: string;
  eyebrow: string;
  title: string;
};

function routeErrorDetails(error: unknown): RouteErrorDetails {
  if (isRouteErrorResponse(error)) {
    if (error.status === 404) {
      return {
        description:
          "The route request could not find the resource it expected. Return to a known workspace route to continue.",
        eyebrow: "Route error 404",
        title: "Route resource not found",
      };
    }

    return {
      description:
        "SignalDeck could not finish loading this route. Return to a known workspace route or retry after the service recovers.",
      eyebrow: `Route error ${error.status}`,
      title: error.statusText || "Route failed to load",
    };
  }

  if (error instanceof Error) {
    return {
      description:
        "SignalDeck hit an unexpected routed failure before this workspace could render safely.",
      eyebrow: "Route error",
      title: "Route failed to render",
    };
  }

  return {
    description:
      "SignalDeck received an unknown routed failure before this workspace could render safely.",
    eyebrow: "Route error",
    title: "Route failed to load",
  };
}

export function RouteErrorPage() {
  const error = useRouteError();
  const details = routeErrorDetails(error);

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6" data-testid="route-error-page">
      <Card className="w-full max-w-2xl">
        <CardContent className="flex flex-col items-start gap-5 p-8">
          <div className="flex size-12 items-center justify-center rounded-2xl bg-destructive/10 text-destructive">
            <AlertTriangle aria-hidden="true" className="size-6" />
          </div>
          <div className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
              {details.eyebrow}
            </p>
            <h1 className="text-2xl font-semibold tracking-tight">{details.title}</h1>
            <p className="max-w-xl text-sm text-muted-foreground">{details.description}</p>
          </div>
          <Button asChild size="sm">
            <Link to="/workflow-packages">
              <Home aria-hidden="true" className="size-4" />
              Open workflow packages
            </Link>
          </Button>
        </CardContent>
      </Card>
    </main>
  );
}
