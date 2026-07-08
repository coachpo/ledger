import { spawn, spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const backendDir = resolve(__dirname, "..", "..", "backend");
const fakeProviderPort = process.env.SIGNALDECK_FAKE_PROVIDER_PORT ?? "18081";
const fakeProviderBaseUrl =
  process.env.SIGNALDECK_FAKE_PROVIDER_BASE_URL ??
  `http://127.0.0.1:${fakeProviderPort}/v1`;
const children = new Set();
const e2eDatabaseName = `signaldeck_e2e_${process.pid}_${Date.now()}`;
let backendEnv = process.env;
let e2eDatabaseCreated = false;
let shuttingDown = false;

const databaseManagerScript = String.raw`
import os
import re
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import DEFAULT_DATABASE_URL


def quote_identifier(identifier):
    return '"' + identifier.replace('"', '""') + '"'


command, database_name = sys.argv[1], sys.argv[2]
if not re.fullmatch(r"signaldeck_e2e_[A-Za-z0-9_]+", database_name):
    raise RuntimeError(f"Refusing to manage non-e2e database: {database_name}")

base_database_url = make_url(os.environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL)
if base_database_url.get_backend_name() not in {"postgresql", "postgres"}:
    raise RuntimeError("Playwright e2e requires a PostgreSQL DATABASE_URL.")

admin_database_url = base_database_url.set(database="postgres")
target_database_url = base_database_url.set(database=database_name)
engine = create_engine(admin_database_url, isolation_level="AUTOCOMMIT", future=True)
try:
    with engine.connect() as connection:
        if command == "create":
            connection.execute(text(f"CREATE DATABASE {quote_identifier(database_name)}"))
            print(target_database_url.render_as_string(hide_password=False))
        elif command == "drop":
            connection.execute(
                text(f"DROP DATABASE IF EXISTS {quote_identifier(database_name)} WITH (FORCE)")
            )
        else:
            raise RuntimeError(f"Unsupported database command: {command}")
finally:
    engine.dispose()
`;

function exitCodeFor(code, signal) {
  if (typeof code === "number") {
    return code;
  }
  return signal ? 1 : 0;
}

function runDatabaseManager(command) {
  const result = spawnSync(
    "uv",
    ["run", "--frozen", "python", "-c", databaseManagerScript, command, e2eDatabaseName],
    {
      cwd: backendDir,
      env: process.env,
      encoding: "utf8",
    },
  );
  if (result.status !== 0) {
    throw new Error(
      `Failed to ${command} Playwright e2e database.\n${result.stderr || result.stdout}`,
    );
  }
  return result.stdout.trim();
}

function createE2eDatabase() {
  // E2E owns a disposable DB so stale local rows cannot leak into Playwright.
  const databaseUrl = runDatabaseManager("create");
  e2eDatabaseCreated = true;
  return databaseUrl;
}

function dropE2eDatabase() {
  if (!e2eDatabaseCreated) {
    return;
  }
  try {
    runDatabaseManager("drop");
  } catch (error) {
    console.warn(error);
  } finally {
    e2eDatabaseCreated = false;
  }
}

function stopAll(exitCode = 0) {
  if (shuttingDown) {
    return;
  }
  shuttingDown = true;
  for (const child of children) {
    child.kill();
  }
  dropE2eDatabase();
  process.exit(exitCode);
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
  const e2eDatabaseUrl = createE2eDatabase();
  backendEnv = {
    ...process.env,
    DATABASE_URL: e2eDatabaseUrl,
    OPENAI_API_KEY: "sk-e2e-fake-provider",
    OPENAI_BASE_URL: fakeProviderBaseUrl,
    QUOTE_PROVIDER_BACKEND: process.env.QUOTE_PROVIDER_BACKEND ?? "deterministic",
    SIGNALDECK_API_TOKEN: "",
    SIGNALDECK_FAKE_PROVIDER_BASE_URL: fakeProviderBaseUrl,
    SIGNALDECK_FAKE_PROVIDER_PORT: fakeProviderPort,
  };
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
