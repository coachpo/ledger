import { Archive, Plus, SquarePen } from "lucide-react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import { useArchiveSkill, useSkills } from "@/hooks/use-skills";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import { PlatformResourceBadges, sortByKey } from "../platform-resource-shared";

export function SkillsListPage() {
  const navigate = useNavigate();
  const skillsQuery = useSkills();
  const archiveMutation = useArchiveSkill();
  const skills = sortByKey(skillsQuery.data?.items ?? []);

  const handleArchive = async (skillId: number) => {
    try {
      await archiveMutation.mutateAsync(skillId);
      toast.success("Skill archived");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to archive skill");
    }
  };

  return (
    <div className="space-y-4 p-4" data-testid="platform-skills-page">
      <div
        className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"
        data-testid="skills-list"
      >
        <div className="space-y-1">
          <h1 className="text-xl font-semibold tracking-tight">Skills</h1>
          <p className="text-sm text-muted-foreground">
            Manage reusable skill definitions and their tool bindings for the primary workspace.
          </p>
        </div>
        <Button data-testid="skills-new" size="sm" onClick={() => navigate("/skills/new")}>
          <Plus data-icon="inline-start" />
          New Skill
        </Button>
      </div>

      {skillsQuery.isPending ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            Loading skills...
          </CardContent>
        </Card>
      ) : null}

      {skillsQuery.isError ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            {skillsQuery.error instanceof Error ? skillsQuery.error.message : "Failed to load skills."}
          </CardContent>
        </Card>
      ) : null}

      {!skillsQuery.isPending && !skillsQuery.isError && skills.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No skills exist yet.
          </CardContent>
        </Card>
      ) : null}

      {!skillsQuery.isPending && !skillsQuery.isError && skills.length > 0 ? (
        <div className="grid gap-3">
          {skills.map((skill) => (
            <Card key={skill.id} data-testid={`skills-row-${skill.key}`}>
              <CardHeader className="gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="space-y-2">
                  <div className="space-y-1">
                    <CardTitle className="text-base">{skill.name}</CardTitle>
                    <CardDescription>{skill.key}</CardDescription>
                  </div>
                  <PlatformResourceBadges status={skill.status} version={skill.version} />
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    data-testid={`skills-open-${skill.key}`}
                    size="sm"
                    variant="outline"
                    onClick={() => navigate(`/skills/${skill.id}/edit`)}
                  >
                    <SquarePen data-icon="inline-start" />
                    Edit
                  </Button>
                  {skill.status !== "archived" ? (
                    <Button
                      data-testid={`skills-archive-${skill.key}`}
                      disabled={archiveMutation.isPending}
                      size="sm"
                      variant="outline"
                      onClick={() => void handleArchive(skill.id)}
                    >
                      <Archive data-icon="inline-start" />
                      Archive
                    </Button>
                  ) : null}
                </div>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                <p>{skill.description || "No description provided."}</p>
                <p>{skill.toolDefinitions.length} tool definition(s)</p>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}
    </div>
  );
}
