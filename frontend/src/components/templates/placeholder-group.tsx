import { useState } from "react";
import { ChevronDown, ChevronRight, Copy } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

export interface PlaceholderItem {
  path: string;
  type: string;
}

type PlaceholderGroupProps = {
  description?: string;
  title: string;
  items: PlaceholderItem[];
  onInsert: (path: string) => void;
};

export function PlaceholderGroup({
  description,
  title,
  items,
  onInsert,
}: PlaceholderGroupProps) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen} className="min-w-[260px]">
      <CollapsibleTrigger asChild>
        <button className="flex w-full items-center gap-1 py-1 text-left text-xs font-medium text-foreground hover:text-primary">
          {isOpen ? (
            <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground" />
          )}
          {title}
          <Badge variant="outline" className="ml-1 h-4 px-1 text-[9px]">
            {items.length}
          </Badge>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="flex flex-col pb-1 pl-4">
        {description ? (
          <p className="px-1 pb-1 text-[10px] leading-4 text-muted-foreground">{description}</p>
        ) : null}
        {items.map((item) => (
          <div
            key={item.path}
            className="group flex cursor-pointer items-center gap-1.5 rounded px-1 py-0.5 hover:bg-accent"
            onClick={() => onInsert(item.path)}
          >
            <code className="flex-1 truncate text-[11px] text-primary">{item.path}</code>
            <Badge variant="outline" className="h-3.5 shrink-0 px-1 text-[8px] uppercase leading-none">
              {item.type}
            </Badge>
            <Copy className="h-2.5 w-2.5 shrink-0 opacity-0 transition-opacity group-hover:opacity-60" />
          </div>
        ))}
      </CollapsibleContent>
    </Collapsible>
  );
}
