"use client";

import * as TabsPrimitive from "@radix-ui/react-tabs";
import type * as React from "react";

import { cn } from "./utils";

function Tabs({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Root>) {
  return (
    <TabsPrimitive.Root
      data-slot="tabs"
      className={cn("flex flex-col gap-2 data-[orientation=vertical]:items-stretch", className)}
      {...props}
    />
  );
}

function TabsList({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      data-slot="tabs-list"
      className={cn(
        "inline-flex h-9 w-fit items-center justify-center rounded-xl border border-border/60 bg-ui-surface-grouped/80 p-[3px] text-muted-foreground shadow-inner shadow-black/[0.02] data-[orientation=vertical]:h-auto data-[orientation=vertical]:shrink-0 data-[orientation=vertical]:flex-col data-[orientation=vertical]:items-stretch data-[orientation=vertical]:justify-start dark:shadow-black/20",
        className,
      )}
      {...props}
    />
  );
}

function TabsTrigger({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      data-slot="tabs-trigger"
      className={cn(
        "inline-flex h-[calc(100%-1px)] flex-1 items-center justify-center gap-1.5 rounded-xl border border-transparent px-2.5 py-1 text-sm font-medium whitespace-nowrap text-muted-foreground outline-none transition-[background-color,border-color,color,box-shadow] duration-[var(--ui-motion-duration-base)] ease-[var(--ui-motion-ease-standard)] focus-visible:border-ring focus-visible:ring-0 focus-visible:[box-shadow:var(--ui-focus-shadow)] disabled:pointer-events-none disabled:opacity-50 data-[state=active]:border-border/50 data-[state=active]:bg-ui-surface-elevated data-[state=active]:text-foreground data-[state=active]:shadow-ui-xs data-[orientation=vertical]:h-auto data-[orientation=vertical]:w-full data-[orientation=vertical]:flex-none data-[orientation=vertical]:justify-start [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
        className,
      )}
      {...props}
    />
  );
}

function TabsContent({
  className,
  ...props
}: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return (
    <TabsPrimitive.Content
      data-slot="tabs-content"
      className={cn("min-w-0 flex-1 outline-none", className)}
      {...props}
    />
  );
}

export { Tabs, TabsContent, TabsList, TabsTrigger };
