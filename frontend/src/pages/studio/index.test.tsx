import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import { Layout } from "@/components/layout";
import { ThemeProvider } from "@/components/theme-provider";

import { StudioIndexPage } from "./index";

Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: {
    getItem: () => null,
    removeItem: () => undefined,
    setItem: () => undefined,
  },
});

describe("StudioIndexPage", () => {
  it("renders the Studio nav entry and breadcrumb inside the main layout", () => {
    render(
      <ThemeProvider>
        <MemoryRouter initialEntries={["/studio"]}>
          <Routes>
            <Route element={<Layout />}>
              <Route path="/studio" element={<StudioIndexPage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </ThemeProvider>,
    );

    expect(screen.getByTestId("nav-studio")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /studio/i })).toBeInTheDocument();
    expect(screen.getByTestId("studio-index-page")).toBeInTheDocument();
    expect(screen.getByTestId("studio-index-agents-link")).toBeInTheDocument();
  });
});
