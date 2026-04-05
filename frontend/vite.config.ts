/// <reference types="vitest" />

import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

const __dirname = dirname(fileURLToPath(import.meta.url));
const frameworkChunkPattern =
  /[/\\]node_modules[/\\](react|react-dom|scheduler|react-router|react-router-dom)[/\\]/;
const dataChunkPattern =
  /[/\\]node_modules[/\\]@tanstack[/\\](react-query|react-table)[/\\]/;
const uiChunkPattern =
  /[/\\]node_modules[/\\](@radix-ui|@floating-ui|cmdk|lucide-react|react-resizable-panels|sonner|class-variance-authority|clsx|tailwind-merge)[/\\]/;
const chartsChunkPattern = /[/\\]node_modules[/\\]recharts[/\\]/;
const formsChunkPattern = /[/\\]node_modules[/\\](react-hook-form|zod)[/\\]|[/\\]node_modules[/\\]@hookform[/\\]resolvers[/\\]/;
const dateChunkPattern =
  /[/\\]node_modules[/\\](react-day-picker|date-fns)[/\\]/;
const vendorChunkPattern = /[/\\]node_modules[/\\]/;

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": resolve(__dirname, "./src"),
    },
  },
  build: {
    rolldownOptions: {
      output: {
        manualChunks(id) {
          if (frameworkChunkPattern.test(id)) {
            return "framework";
          }

          if (dataChunkPattern.test(id)) {
            return "data";
          }

          if (uiChunkPattern.test(id)) {
            return "ui";
          }

          if (chartsChunkPattern.test(id)) {
            return "charts";
          }

          if (formsChunkPattern.test(id)) {
            return "forms";
          }

          if (dateChunkPattern.test(id)) {
            return "date";
          }

          if (vendorChunkPattern.test(id)) {
            return "vendor";
          }
        },
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
