import { ArrowRight, Bot, Cpu, ShieldCheck, Workflow } from "lucide-react";
import { Link } from "react-router";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const studioSections = [
  {
    description: "Draft and inspect agent specs. Seeded rows stay read-only while managed rows stay editable.",
    href: "/studio/agents",
    icon: Bot,
    testId: "studio-index-agents-link",
    title: "Agents",
  },
  {
    description: "Manage workflow graph definitions and inspect key-based workflow routes.",
    href: "/studio/workflows",
    icon: Workflow,
    testId: "studio-index-workflows-link",
    title: "Workflows",
  },
  {
    description: "Draft managed personas in Studio while keeping imported and seeded persona projections read-only.",
    href: "/studio/personas",
    icon: ShieldCheck,
    testId: "studio-index-personas-link",
    title: "Personas",
  },
  {
    description: "Configure connector, tool, and bundle capabilities that power Studio execution.",
    href: "/studio/capabilities",
    icon: Cpu,
    testId: "studio-index-capabilities-link",
    title: "Capabilities",
  },
] as const;

export function StudioIndexPage() {
  return (
    <div className="space-y-4 p-4" data-testid="studio-index-page">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold tracking-tight">Studio</h1>
        <p className="text-sm text-muted-foreground">
          Browse the v2 Studio catalog, inspect runtime runs, and edit managed resources without changing legacy orchestration routes.
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        {studioSections.map((section) => (
          <Card key={section.href} data-testid={`studio-index-card-${section.title.toLowerCase()}`}>
            <CardHeader className="space-y-2">
              <div className="flex items-center gap-2">
                <div className="rounded-md bg-primary/10 p-2 text-primary">
                  <section.icon className="size-4" />
                </div>
                <CardTitle className="text-base">{section.title}</CardTitle>
              </div>
              <CardDescription>{section.description}</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild data-testid={section.testId} size="sm" variant="secondary">
                <Link to={section.href}>
                  Open {section.title}
                  <ArrowRight className="ml-1 size-3.5" />
                </Link>
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card data-testid="studio-index-runs-card">
        <CardHeader>
          <CardTitle className="text-base">Runtime runs</CardTitle>
          <CardDescription>
            Run detail routes live at <code>/studio/runs/:runId</code> and surface final output, resolved personas, capabilities, and trace widgets for a single Studio execution.
          </CardDescription>
        </CardHeader>
      </Card>
    </div>
  );
}
