import { Navigate, useParams } from "react-router";

export function LegacySkillsListRedirect() {
  return <Navigate replace to="/capabilities" />;
}

export function LegacySkillsNewRedirect() {
  return <Navigate replace to="/capabilities/new" />;
}

export function LegacySkillsEditRedirect() {
  const { skillId } = useParams<{ skillId: string }>();

  return <Navigate replace to={`/capabilities/${skillId ?? ""}/edit`} />;
}
