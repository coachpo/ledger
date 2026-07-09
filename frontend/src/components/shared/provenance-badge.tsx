import { Badge } from "@/components/ui/badge";
import { cn } from "@/components/ui/utils";

type ProvenanceBadgeTone = "neutral" | "verified" | "warning" | "destructive";

export type ProvenanceBadgeProps = {
  className?: string;
  detail?: string;
  label: string;
  tone?: ProvenanceBadgeTone;
};

const provenanceBadgeVariantByTone: Record<ProvenanceBadgeTone, "secondary" | "outline" | "destructive"> = {
  neutral: "outline",
  verified: "secondary",
  warning: "outline",
  destructive: "destructive",
};

const provenanceBadgeClassByTone: Record<ProvenanceBadgeTone, string> = {
  neutral: "",
  verified: "",
  warning: "border-muted-foreground/40 bg-muted text-foreground",
  destructive: "",
};

export function ProvenanceBadge({
  className,
  detail,
  label,
  tone = "neutral",
}: ProvenanceBadgeProps) {
  return (
    <Badge
      aria-label={detail ? `${label}: ${detail}` : label}
      className={cn(provenanceBadgeClassByTone[tone], className)}
      data-tone={tone}
      variant={provenanceBadgeVariantByTone[tone]}
    >
      <span>{label}</span>
      {detail ? <span className="text-muted-foreground">{detail}</span> : null}
    </Badge>
  );
}
