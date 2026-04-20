import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const backendDir = resolve(__dirname, "..", "..", "backend");

const child = spawn(
  "uv",
  ["run", "--frozen", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001"],
  {
    cwd: backendDir,
    env: {
      ...process.env,
      QUOTE_PROVIDER_BACKEND: process.env.QUOTE_PROVIDER_BACKEND ?? "deterministic",
    },
    stdio: "inherit",
  }
);

process.on("SIGTERM", () => child.kill());
process.on("SIGINT", () => child.kill());
