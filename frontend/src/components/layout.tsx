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
      <SidebarHeader className="h-14 justify-center border-b border-sidebar-border px-4 py-0">
        <div className="flex items-center gap-3">
          <div className="flex size-9 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <img alt="" aria-hidden="true" className="size-5 shrink-0" src="/favicon.svg" />
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
            {showExpandedContent ? <SidebarGroupLabel>{group.label}</SidebarGroupLabel> : null}
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => (
                  <SidebarMenuItem key={item.to}>
                    <SidebarMenuButton
                      asChild
                      className={!showExpandedContent ? "justify-center" : undefined}
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
                        <span className={!showExpandedContent ? "sr-only" : undefined}>
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

export function Layout() {
  const location = useLocation();
  const routeMetadata = getRouteMetadataForPathname(location.pathname);
  const breadcrumbMetadata = routeMetadata.breadcrumb;
  const usesFullHeightShell = routeMetadata.shellMode === "fullHeight";

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-border bg-background/95 px-4 backdrop-blur">
          <SidebarTrigger />
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
                      <BreadcrumbPage>{breadcrumbMetadata.title}</BreadcrumbPage>
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
          data-testid={routeMetadata.testId}
        >
          {usesFullHeightShell ? (
            <div className="h-full [&>*]:h-full [&>*]:w-full">
              <Outlet />
            </div>
          ) : (
            <ScrollArea className="h-full">
              <div className="min-h-full [&>*]:mx-auto [&>*]:w-full [&>*]:max-w-7xl">
                <Outlet />
              </div>
            </ScrollArea>
          )}
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
