import { Link, NavLink, Outlet, useLocation } from "react-router";
import {
  Bot,
  Briefcase,
  ClipboardList,
  FileText,
  FlaskConical,
  LayoutDashboard,
  Sparkles,
  TrendingUp,
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
  { icon: TrendingUp, label: "Backtests", testId: "nav-backtests", to: "/backtests" },
  { icon: FlaskConical, label: "Tryout", testId: "nav-tryout", to: "/tryout" },
  { icon: Sparkles, label: "Studio", testId: "nav-studio", to: "/studio" },
  { icon: Bot, label: "Orchestration", testId: "nav-orchestration", to: "/orchestration" },
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

  if (pathname === "/backtests") {
    return { section: "Backtests", title: "Backtests" };
  }

  if (pathname === "/backtests/new") {
    return { section: "Backtests", sectionHref: "/backtests", title: "New Backtest" };
  }

  if (pathname.startsWith("/backtests/")) {
    return { section: "Backtests", sectionHref: "/backtests", title: "Backtest Detail" };
  }

  if (pathname === "/tryout") {
    return { section: "Tryout", title: "Tryout" };
  }

  if (pathname === "/studio") {
    return { section: "Studio", title: "Studio" };
  }

  if (pathname === "/studio/agents") {
    return { section: "Studio", sectionHref: "/studio", title: "Agents" };
  }

  if (pathname === "/studio/agents/new") {
    return { section: "Studio", sectionHref: "/studio/agents", title: "New Agent" };
  }

  if (pathname.startsWith("/studio/agents/") && pathname.endsWith("/edit")) {
    return { section: "Studio", sectionHref: "/studio/agents", title: "Edit Agent" };
  }

  if (pathname === "/studio/workflows") {
    return { section: "Studio", sectionHref: "/studio", title: "Workflows" };
  }

  if (pathname === "/studio/workflows/new") {
    return { section: "Studio", sectionHref: "/studio/workflows", title: "New Workflow" };
  }

  if (pathname.startsWith("/studio/workflows/") && pathname.endsWith("/edit")) {
    return { section: "Studio", sectionHref: "/studio/workflows", title: "Edit Workflow" };
  }

  if (pathname === "/studio/personas") {
    return { section: "Studio", sectionHref: "/studio", title: "Personas" };
  }

  if (pathname === "/studio/personas/new") {
    return { section: "Studio", sectionHref: "/studio/personas", title: "New Persona" };
  }

  if (pathname.startsWith("/studio/personas/") && pathname.endsWith("/edit")) {
    return { section: "Studio", sectionHref: "/studio/personas", title: "Inspect Persona" };
  }

  if (pathname === "/studio/capabilities") {
    return { section: "Studio", sectionHref: "/studio", title: "Capabilities" };
  }

  if (pathname === "/studio/capabilities/new") {
    return { section: "Studio", sectionHref: "/studio/capabilities", title: "New Capability" };
  }

  if (pathname.startsWith("/studio/capabilities/") && pathname.endsWith("/edit")) {
    return { section: "Studio", sectionHref: "/studio/capabilities", title: "Edit Capability" };
  }

  if (pathname.startsWith("/studio/runs/")) {
    return { section: "Studio", sectionHref: "/studio", title: "Run Detail" };
  }

  if (pathname === "/orchestration") {
    return { section: "Orchestration", title: "Orchestration" };
  }

  if (pathname === "/orchestration/roles") {
    return { section: "Orchestration", sectionHref: "/orchestration", title: "Roles" };
  }

  if (pathname === "/orchestration/roles/new") {
    return { section: "Orchestration", sectionHref: "/orchestration/roles", title: "New Role" };
  }

  if (pathname.startsWith("/orchestration/roles/") && pathname.endsWith("/edit")) {
    return { section: "Orchestration", sectionHref: "/orchestration/roles", title: "Edit Role" };
  }

  if (pathname === "/orchestration/characters") {
    return { section: "Orchestration", sectionHref: "/orchestration", title: "Characters" };
  }

  if (pathname === "/orchestration/characters/new") {
    return {
      section: "Orchestration",
      sectionHref: "/orchestration/characters",
      title: "New Character",
    };
  }

  if (pathname.startsWith("/orchestration/characters/") && pathname.endsWith("/edit")) {
    return {
      section: "Orchestration",
      sectionHref: "/orchestration/characters",
      title: "Edit Character",
    };
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
              <p className="text-xs text-muted-foreground">Portfolio workspace</p>
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
