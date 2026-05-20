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

function isNavItemActive(pathname: string, item: NavItem) {
  return item.to === "/"
    ? pathname === "/"
    : pathname === item.to || pathname.startsWith(`${item.to}/`);
}

function getPageMeta(pathname: string) {
  if (pathname === "/") {
    return { section: "Dashboard", title: "Dashboard" };
  }

  if (pathname === "/portfolios") {
    return { section: "Portfolios", title: "Portfolios" };
  }

  if (pathname.startsWith("/portfolios/")) {
    return { section: "Portfolios", sectionHref: "/portfolios", title: "Portfolio Detail" };
  }

  if (pathname === "/templates") {
    return { section: "Templates", title: "Templates" };
  }

  if (pathname === "/templates/new") {
    return { section: "Templates", sectionHref: "/templates", title: "New Template" };
  }

  if (pathname.startsWith("/templates/") && pathname.endsWith("/edit")) {
    return { section: "Templates", sectionHref: "/templates", title: "Edit Template" };
  }

  if (pathname === "/reports") {
    return { section: "Reports", title: "Reports" };
  }

  if (pathname.startsWith("/reports/")) {
    return { section: "Reports", sectionHref: "/reports", title: "Report Detail" };
  }

  if (pathname === "/extensions") {
    return { section: "Extensions", title: "Extensions" };
  }

  if (pathname === "/workflow-packages") {
    return { section: "Workflow Packages", title: "Workflow Packages" };
  }

  if (pathname === "/workflow-packages/new") {
    return {
      section: "Workflow Packages",
      sectionHref: "/workflow-packages",
      title: "New Workflow Package",
    };
  }

  if (pathname.startsWith("/workflow-packages/") && pathname.endsWith("/run")) {
    return {
      section: "Workflow Packages",
      sectionHref: "/workflow-packages",
      title: "Launch Workflow Package",
    };
  }

  if (pathname.startsWith("/workflow-packages/")) {
    return {
      section: "Workflow Packages",
      sectionHref: "/workflow-packages",
      title: "Workflow Package Detail",
    };
  }

  if (pathname === "/model-connections") {
    return { section: "Model Connections", title: "Model Connections" };
  }

  if (pathname === "/model-connections/new") {
    return {
      section: "Model Connections",
      sectionHref: "/model-connections",
      title: "New Model Connection",
    };
  }

  if (pathname.startsWith("/model-connections/") && pathname.endsWith("/edit")) {
    return {
      section: "Model Connections",
      sectionHref: "/model-connections",
      title: "Edit Model Connection",
    };
  }

  if (pathname === "/runs") {
    return { section: "Runs", title: "Runs" };
  }

  if (pathname.startsWith("/runs/")) {
    return { section: "Runs", sectionHref: "/runs", title: "Run Detail" };
  }

  return { section: "Workspace", title: "Workspace" };
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
  const pageMeta = getPageMeta(location.pathname);
  const isTemplateEditorRoute =
    location.pathname === "/templates/new" ||
    (location.pathname.startsWith("/templates/") && location.pathname.endsWith("/edit"));
  const isWorkflowPackageEditorRoute =
    location.pathname === "/workflow-packages/new" ||
    location.pathname.startsWith("/workflow-packages/");
  const isRunDetailWorkspaceRoute = /^\/runs\/[^/]+$/.test(location.pathname);

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-border bg-background/95 px-4 backdrop-blur">
          <SidebarTrigger />
          <div className="min-w-0 flex-1">
            <Breadcrumb>
              <BreadcrumbList>
                {pageMeta.sectionHref ? (
                  <>
                    <BreadcrumbItem>
                      <BreadcrumbLink asChild>
                        <Link to={pageMeta.sectionHref}>{pageMeta.section}</Link>
                      </BreadcrumbLink>
                    </BreadcrumbItem>
                    <BreadcrumbSeparator />
                    <BreadcrumbItem>
                      <BreadcrumbPage>{pageMeta.title}</BreadcrumbPage>
                    </BreadcrumbItem>
                  </>
                ) : (
                  <BreadcrumbItem>
                    <BreadcrumbPage>{pageMeta.title}</BreadcrumbPage>
                  </BreadcrumbItem>
                )}
              </BreadcrumbList>
            </Breadcrumb>
          </div>
          <ThemeToggle />
        </header>

        <main className="min-h-0 min-w-0 flex-1 overflow-hidden">
          {isTemplateEditorRoute || isWorkflowPackageEditorRoute || isRunDetailWorkspaceRoute ? (
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
