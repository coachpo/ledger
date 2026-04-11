import { Link } from "react-router";
import { Bot, Users } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export function OrchestrationIndexPage() {
  return (
    <div className="max-w-5xl p-4">
      <div className="flex flex-col gap-6">
        <div className="flex flex-col gap-1">
          <h1 className="text-xl font-semibold tracking-tight">Orchestration</h1>
          <p className="text-sm text-muted-foreground">
            Configure reusable roles and characters for orchestration-aware templates and
            backtests.
          </p>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Bot className="size-4" />
                Roles
              </CardTitle>
              <CardDescription>
                Define shared system prompts and orchestration responsibilities.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild size="sm">
                <Link to="/orchestration/roles">Manage Roles</Link>
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Users className="size-4" />
                Characters
              </CardTitle>
              <CardDescription>
                Map named personas onto reusable roles for prompt-time mention targets.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild size="sm">
                <Link to="/orchestration/characters">Manage Characters</Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
