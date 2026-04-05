import type { ReportRead } from "@/lib/types/report";

export type GroupByOption = "none" | "tags" | "source" | "month" | "ticker" | "portfolio";

export const GROUP_BY_LABELS: Record<GroupByOption, string> = {
  none: "None",
  tags: "Tags",
  source: "Source",
  month: "Month",
  ticker: "Ticker",
  portfolio: "Portfolio",
};

export type SortField = "name" | "createdAt" | "source";
export type SortDirection = "asc" | "desc";

export function filterReports(reports: ReportRead[], query: string): ReportRead[] {
  const q = query.trim().toLowerCase();
  if (!q) return reports;

  return reports.filter((r) => {
    if (r.name.toLowerCase().includes(q)) return true;
    if (r.slug.toLowerCase().includes(q)) return true;
    if (r.metadata.author?.toLowerCase().includes(q)) return true;
    if (r.metadata.tags.some((t) => t.toLowerCase().includes(q))) return true;
    if (r.metadata.analysis?.ticker?.toLowerCase().includes(q)) return true;
    return false;
  });
}

export function groupReports(
  reports: ReportRead[],
  groupBy: GroupByOption,
): Map<string, ReportRead[]> {
  if (groupBy === "none") {
    const sorted = [...reports].sort(
      (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
    );
    return new Map([["All Reports", sorted]]);
  }

  const groups = new Map<string, ReportRead[]>();

  for (const report of reports) {
    const keys = getGroupKeys(report, groupBy);
    for (const key of keys) {
      const existing = groups.get(key);
      if (existing) {
        existing.push(report);
      } else {
        groups.set(key, [report]);
      }
    }
  }

  for (const [, items] of groups) {
    items.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime());
  }

  const sortedEntries = [...groups.entries()].sort(([a], [b]) => {
    const aIsDefault = isDefaultGroup(a);
    const bIsDefault = isDefaultGroup(b);
    if (aIsDefault && !bIsDefault) return 1;
    if (!aIsDefault && bIsDefault) return -1;
    return a.localeCompare(b);
  });

  return new Map(sortedEntries);
}

function isDefaultGroup(label: string): boolean {
  return label === "Untagged" || label === "Unknown";
}

function getGroupKeys(report: ReportRead, groupBy: GroupByOption): string[] {
  switch (groupBy) {
    case "tags": {
      const tags = report.metadata.tags;
      return tags.length > 0 ? tags : ["Untagged"];
    }
    case "source": {
      const labels: Record<string, string> = {
        compiled: "Compiled",
        uploaded: "Uploaded",
        external: "External",
      };
      return [labels[report.source] ?? "Unknown"];
    }
    case "month": {
      try {
        const date = new Date(report.createdAt);
        const label = new Intl.DateTimeFormat("en-US", {
          month: "long",
          year: "numeric",
        }).format(date);
        return [label];
      } catch {
        return ["Unknown"];
      }
    }
    case "ticker": {
      const ticker = report.metadata.analysis?.ticker;
      return ticker ? [ticker] : ["Unknown"];
    }
    case "portfolio": {
      const slug = report.metadata.analysis?.portfolioSlug;
      return slug ? [slug] : ["Unknown"];
    }
    default:
      return ["All Reports"];
  }
}

export function sortReports(
  reports: ReportRead[],
  field: SortField,
  direction: SortDirection,
): ReportRead[] {
  const sorted = [...reports];
  const dir = direction === "asc" ? 1 : -1;

  sorted.sort((a, b) => {
    switch (field) {
      case "name":
        return a.name.localeCompare(b.name) * dir;
      case "createdAt":
        return (new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime()) * dir;
      case "source":
        return a.source.localeCompare(b.source) * dir;
      default:
        return 0;
    }
  });

  return sorted;
}
