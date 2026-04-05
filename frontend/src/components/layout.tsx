import { Link, NavLink, Outlet, useLocation } from "react-router";
import {
  Briefcase,
  ClipboardList,
  FileText,
  LayoutDashboard,
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
  to: string;
};

const navItems: NavItem[] = [
  { icon: LayoutDashboard, label: "Dashboard", to: "/" },
  { icon: Briefcase, label: "Portfolios", to: "/portfolios" },
  { icon: FileText, label: "Templates", to: "/templates" },
  { icon: ClipboardList, label: "Reports", to: "/reports" },
  { icon: TrendingUp, label: "Backtests", to: "/backtests" },
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
