import { Link, NavLink, Outlet, useLocation } from "react-router";

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "./ui/breadcrumb";
import { ScrollArea } from "./ui/scroll-area";
import { ThemeToggle } from "./theme-toggle";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "./ui/sidebar";
import { useSidebar } from "./ui/sidebar-context";

import { assembleNavGroups, type NavItem } from "@/extensions/runtime-helpers";
import { useExtensions } from "@/hooks/use-extensions";
import { getRouteMetadataForPathname } from "@/routes.metadata";

function isNavItemActive(pathname: string, item: NavItem) {
  return item.to === "/"
    ? pathname === "/"
    : pathname === item.to || pathname.startsWith(`${item.to}/`);
}

function AppSidebar() {
  const location = useLocation();
  const extensionsQuery = useExtensions();
  const navGroups = assembleNavGroups(extensionsQuery.data);
  const { isMobile, open, setOpenMobile } = useSidebar();
  const showExpandedContent = open || isMobile;

  return (
    <Sidebar variant="inset">
      <SidebarHeader className="h-12 justify-center border-b border-sidebar-border px-3 py-0">
        <div className="flex items-center gap-2">
          <div className="flex size-8 items-center justify-center rounded-lg bg-sidebar-primary/10 text-sidebar-primary">
            <img
              alt=""
              aria-hidden="true"
              className="size-4 shrink-0"
              src="/favicon.svg"
            />
          </div>
          {showExpandedContent ? (
            <div className="min-w-0">
              <p className="text-sm font-semibold tracking-tight">SignalDeck</p>
            </div>
          ) : null}
        </div>
      </SidebarHeader>
      <SidebarContent>
        {navGroups.map((group) => (
          <SidebarGroup key={group.label}>
            {showExpandedContent ? (
              <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
            ) : null}
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => (
                  <SidebarMenuItem key={item.to}>
                    <SidebarMenuButton
                      asChild
                      className={
                        !showExpandedContent ? "justify-center" : undefined
                      }
                      isActive={isNavItemActive(location.pathname, item)}
                      tooltip={!showExpandedContent ? item.label : undefined}
                    >
                      <NavLink
                        data-testid={item.testId}
                        end={item.to === "/"}
                        onClick={() => setOpenMobile(false)}
                        to={item.to}
                      >
                        <item.icon className="size-4 shrink-0" />
                        <span
                          className={
                            !showExpandedContent ? "sr-only" : undefined
                          }
                        >
                          {item.label}
                        </span>
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>
    </Sidebar>
  );
}

function routeWidthWrapperClassName(widthMode: string) {
  switch (widthMode) {
    case "compact":
      return "min-h-full min-w-0 max-w-full [&>*]:mx-auto [&>*]:min-w-0 [&>*]:w-full [&>*]:max-w-4xl";
    case "readable":
      return "min-h-full min-w-0 max-w-full [&>*]:mx-auto [&>*]:min-w-0 [&>*]:w-full [&>*]:max-w-5xl";
    case "wide":
    default:
      return "min-h-full min-w-0 max-w-full [&>*]:min-w-0 [&>*]:w-full";
  }
}

export function Layout() {
  const location = useLocation();
  const routeMetadata = getRouteMetadataForPathname(location.pathname);
  const breadcrumbMetadata = routeMetadata.breadcrumb;
  const usesFullHeightShell = routeMetadata.shellMode === "fullHeight";

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <header className="sticky top-0 z-20 flex h-12 items-center gap-2 border-b border-border bg-background/95 px-3 backdrop-blur">
          <SidebarTrigger className="shrink-0" />
          <div className="min-w-0 flex-1">
            <Breadcrumb>
              <BreadcrumbList>
                {breadcrumbMetadata.parent ? (
                  <>
                    <BreadcrumbItem>
                      <BreadcrumbLink asChild>
                        <Link to={breadcrumbMetadata.parent.href}>
                          {breadcrumbMetadata.parent.title}
                        </Link>
                      </BreadcrumbLink>
                    </BreadcrumbItem>
                    <BreadcrumbSeparator />
                    <BreadcrumbItem>
                      <BreadcrumbPage>
                        {breadcrumbMetadata.title}
                      </BreadcrumbPage>
                    </BreadcrumbItem>
                  </>
                ) : (
                  <BreadcrumbItem>
                    <BreadcrumbPage>{breadcrumbMetadata.title}</BreadcrumbPage>
                  </BreadcrumbItem>
                )}
              </BreadcrumbList>
            </Breadcrumb>
          </div>
          <ThemeToggle />
        </header>

        <main
          className="min-h-0 min-w-0 flex-1 overflow-hidden"
          data-route-shell-mode={routeMetadata.shellMode}
          data-route-width-mode={usesFullHeightShell ? "full" : routeMetadata.widthMode}
          data-testid={routeMetadata.testId}
        >
          {usesFullHeightShell ? (
            <div className="h-full [&>*]:h-full [&>*]:w-full">
              <Outlet />
            </div>
          ) : (
            <ScrollArea className="h-full min-w-0 [&_[data-slot=scroll-area-viewport]>div]:!block [&_[data-slot=scroll-area-viewport]>div]:!min-w-0 [&_[data-slot=scroll-area-viewport]>div]:w-full [&_[data-slot=scroll-area-viewport]>div]:max-w-full">
              <div className={routeWidthWrapperClassName(routeMetadata.widthMode)}>
                <Outlet />
              </div>
            </ScrollArea>
          )}
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
