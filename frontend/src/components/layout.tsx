import { Link, NavLink, Outlet, useLocation } from "react-router";
import {
  Bot,
  Braces,
  Briefcase,
  ClipboardList,
  FileText,
  LayoutDashboard,
  PlayCircle,
  Server,
  Sparkles,
  Workflow,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

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

type NavItem = {
  icon: LucideIcon;
  label: string;
  testId: string;
  to: string;
};

const navItems: NavItem[] = [
  { icon: LayoutDashboard, label: "Dashboard", testId: "nav-dashboard", to: "/" },
  { icon: Briefcase, label: "Portfolios", testId: "nav-portfolios", to: "/portfolios" },
  { icon: FileText, label: "Templates", testId: "nav-templates", to: "/templates" },
  { icon: ClipboardList, label: "Reports", testId: "nav-reports", to: "/reports" },
  { icon: Bot, label: "Agents", testId: "nav-agents", to: "/agents" },
  { icon: Sparkles, label: "Skills", testId: "nav-skills", to: "/skills" },
  { icon: Server, label: "MCP Servers", testId: "nav-mcp-servers", to: "/mcp-servers" },
  {
    icon: Braces,
    label: "Output Schemas",
    testId: "nav-output-schemas",
    to: "/output-schemas",
  },
  { icon: Workflow, label: "Workflows", testId: "nav-workflows", to: "/workflows" },
  { icon: PlayCircle, label: "Runs", testId: "nav-runs", to: "/runs" },
];

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

  if (pathname === "/agents") {
    return { section: "Agents", title: "Agents" };
  }

  if (pathname === "/skills") {
    return { section: "Skills", title: "Skills" };
  }

  if (pathname === "/mcp-servers") {
    return { section: "MCP Servers", title: "MCP Servers" };
  }

  if (pathname === "/output-schemas") {
    return { section: "Output Schemas", title: "Output Schemas" };
  }

  if (pathname === "/output-schemas/new") {
    return { section: "Output Schemas", sectionHref: "/output-schemas", title: "New Output Schema" };
  }

  if (pathname.startsWith("/output-schemas/") && pathname.endsWith("/edit")) {
    return { section: "Output Schemas", sectionHref: "/output-schemas", title: "Edit Output Schema" };
  }

  if (pathname === "/workflows") {
    return { section: "Workflows", title: "Workflows" };
  }

  if (pathname === "/workflows/new") {
    return { section: "Workflows", sectionHref: "/workflows", title: "New Workflow" };
  }

  if (pathname.startsWith("/workflows/") && pathname.endsWith("/edit")) {
    return { section: "Workflows", sectionHref: "/workflows", title: "Edit Workflow" };
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
  const { isMobile, open, setOpenMobile } = useSidebar();
  const showExpandedContent = open || isMobile;

  return (
    <Sidebar variant="inset">
      <SidebarHeader className="h-14 justify-center border-b border-sidebar-border px-4 py-0">
        <div className="flex items-center gap-3">
          <div className="flex size-9 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Briefcase className="size-5 shrink-0" />
          </div>
          {showExpandedContent ? (
            <div className="min-w-0">
              <p className="text-sm font-semibold tracking-tight">Ledger</p>
              <p className="text-xs text-muted-foreground">Portfolio + agent workspace</p>
            </div>
          ) : null}
        </div>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          {showExpandedContent ? <SidebarGroupLabel>Workspace</SidebarGroupLabel> : null}
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map((item) => (
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
          {isTemplateEditorRoute ? (
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
