import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const backendDir = resolve(__dirname, "..", "..", "backend");
const fakeProviderPort = process.env.SIGNALDECK_FAKE_PROVIDER_PORT ?? "18081";
const backendEnv = {
  ...process.env,
  QUOTE_PROVIDER_BACKEND: process.env.QUOTE_PROVIDER_BACKEND ?? "deterministic",
  SIGNALDECK_FAKE_PROVIDER_BASE_URL:
    process.env.SIGNALDECK_FAKE_PROVIDER_BASE_URL ??
    `http://127.0.0.1:${fakeProviderPort}/v1`,
  SIGNALDECK_FAKE_PROVIDER_PORT: fakeProviderPort,
};
const children = new Set();
let shuttingDown = false;

function exitCodeFor(code, signal) {
  if (typeof code === "number") {
    return code;
  }
  return signal ? 1 : 0;
}

function stopAll(exitCode = 0) {
  if (shuttingDown) {
    return;
  }
  shuttingDown = true;
  for (const child of children) {
    child.kill();
  }
  setTimeout(() => process.exit(exitCode), 100).unref();
}

function spawnOwned(label, args) {
  const child = spawn("uv", args, {
    cwd: backendDir,
    env: backendEnv,
    stdio: "inherit",
  });
  children.add(child);
  child.on("error", (error) => {
    console.error(`${label} failed to start:`, error);
    stopAll(1);
  });
  child.on("exit", (code, signal) => {
    children.delete(child);
    if (shuttingDown) {
      return;
    }
    console.error(`${label} exited with code ${code ?? "unknown"} signal ${signal ?? "none"}`);
    stopAll(exitCodeFor(code, signal));
  });
  return child;
}

async function waitForWorkerReady(worker) {
  await delay(750);
  if (worker.exitCode !== null || worker.signalCode !== null) {
    throw new Error("scheduler worker exited before backend startup");
  }
}

async function main() {
  spawnOwned("fake OpenAI-compatible provider", [
    "run",
    "--frozen",
    "python",
    "tests/fake_openai_provider.py",
    "--host",
    "127.0.0.1",
    "--port",
    fakeProviderPort,
  ]);
  await delay(250);
  const worker = spawnOwned("scheduler worker", [
    "run",
    "--frozen",
    "python",
    "-m",
    "app.workers.run_scheduler",
  ]);
  await waitForWorkerReady(worker);
  spawnOwned("backend", [
    "run",
    "--frozen",
    "uvicorn",
    "app.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    "8001",
  ]);
}

process.on("SIGTERM", () => stopAll(0));
process.on("SIGINT", () => stopAll(0));

main().catch((error) => {
  console.error(error);
  stopAll(1);
});
