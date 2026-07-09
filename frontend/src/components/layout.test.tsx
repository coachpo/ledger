import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import { ThemeProvider } from "@/components/theme-provider";
import { router } from "@/routes";

const localStorageState = new Map<string, string>();

Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: {
    getItem: (key: string) => localStorageState.get(key) ?? null,
    removeItem: (key: string) => localStorageState.delete(key),
    setItem: (key: string, value: string) => localStorageState.set(key, value),
  },
});

beforeEach(() => {
  localStorageState.clear();
  document.documentElement.classList.remove("dark");
});

function renderLayout(initialEntry: string) {
  const testRouter = createMemoryRouter(router.routes, {
    initialEntries: [initialEntry],
  });

  return render(
    <ThemeProvider>
      <QueryClientProvider
        client={
          new QueryClient({
            defaultOptions: { queries: { retry: false } },
          })
        }
      >
        <RouterProvider router={testRouter} />
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

async function sidebarGroup(label: string): Promise<HTMLElement> {
  const labelElement = await screen.findByText(label);
  const group = labelElement.closest<HTMLElement>('[data-sidebar="group"]');

  if (!group) {
    throw new Error(`Sidebar group not found for ${label}`);
  }

  return group;
}

describe("Layout", () => {
  it("renders the static sidebar groups without extension state", async () => {
    const { container } = renderLayout("/");

    expect(await screen.findByTestId("nav-dashboard")).toBeVisible();
    expect(
      Array.from(container.querySelectorAll('[data-sidebar="group-label"]')).map(
        (label) => label.textContent,
      ),
    ).toEqual(["Agent Platform", "Finance Workspace"]);
    expect(screen.getByTestId("nav-templates")).toBeVisible();
    expect(screen.getByTestId("nav-reports")).toBeVisible();
    expect(screen.queryByTestId("nav-extensions")).not.toBeInTheDocument();
  });

  it("keeps finance sidebar items visible as static navigation", async () => {
    renderLayout("/");

    const financeGroup = await sidebarGroup("Finance Workspace");
    expect(
      within(financeGroup)
        .getAllByRole("link")
        .map((link) => link.getAttribute("href")),
    ).toEqual(["/templates", "/reports"]);
  });

  it("maps width modes onto scroll routes", async () => {
    renderLayout("/reports/example-report");

    const routedMain = await screen.findByTestId("route-report-detail");
    const wrapper = Array.from(
      routedMain.querySelectorAll<HTMLElement>("div"),
    ).find(
      (element) =>
        element.className.includes("min-h-full") &&
        element.className.includes("max-w-full"),
    );

    expect(wrapper).toHaveClass(
      "min-h-full",
      "min-w-0",
      "max-w-full",
      "[&>*]:min-w-0",
      "[&>*]:w-full",
    );
    expect(wrapper?.parentElement).toHaveAttribute(
      "data-slot",
      "layout-scroll-viewport",
    );
  });

  it("marks full-height routed mains", async () => {
    renderLayout("/workflow-packages/88/run");

    const routedMain = await screen.findByTestId(
      "route-workflow-package-launch",
    );

    expect(routedMain).toHaveAttribute("data-route-shell-mode", "fullHeight");
    expect(routedMain).toHaveAttribute("data-route-width-mode", "full");
  });

  it("keeps metadata-owned shell chrome visible in dark mode", async () => {
    localStorageState.set("signaldeck-theme", "dark");
    renderLayout("/workflow-packages");

    expect(document.documentElement).toHaveClass("dark");
    expect(await screen.findByRole("banner")).toBeVisible();
    expect(
      await screen.findByTestId("route-workflow-packages-list"),
    ).toHaveAttribute("data-route-shell-mode", "scroll");
  });
});
