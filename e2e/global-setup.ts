import { execFile } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { chromium } from "@playwright/test";

const execFileAsync = promisify(execFile);

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");
const COMPOSE_FILE = path.join(HERE, "docker-compose.test.yml");
const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:18080";
const SESSION_SECRET = process.env.E2E_SESSION_SECRET ?? "test-session-secret";
const PYTHON = process.env.E2E_PYTHON ?? path.join(ROOT, ".venv", "bin", "python");
const AUTH_DIR = path.join(HERE, ".auth");

const READY_TIMEOUT_MS = 120_000;
const DATA_TIMEOUT_MS = 60_000;

async function seedDatabase(): Promise<void> {
  try {
    await execFileAsync(
      "docker",
      [
        "compose",
        "-f",
        COMPOSE_FILE,
        "exec",
        "-T",
        "collector",
        "python",
        "/seed_data.py",
      ],
      { cwd: ROOT },
    );
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(
      "Failed to seed the e2e database. Is the stack running? Start it with " +
        "`make e2e-up` (or `docker compose -f e2e/docker-compose.test.yml " +
        "up -d`).\n" +
        detail,
    );
  }
}

async function poll(
  url: string,
  predicate: (body: unknown) => boolean,
  timeoutMs: number,
  description: string,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let lastError = "";
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) {
        const body = (await response.json()) as unknown;
        if (predicate(body)) {
          return;
        }
        lastError = `unexpected response body: ${JSON.stringify(body)}`;
      } else {
        lastError = `HTTP ${response.status}`;
      }
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await new Promise((resolve) => setTimeout(resolve, 2000));
  }
  throw new Error(
    `Timed out waiting for ${description} at ${url} (${lastError}). ` +
      "Is the e2e stack running? Start it with `make e2e-up`.",
  );
}

async function waitForStack(): Promise<void> {
  await poll(
    `${BASE_URL}/health/ready`,
    (body) => (body as { status?: string }).status === "ready",
    READY_TIMEOUT_MS,
    "the web service to become ready",
  );
  await poll(
    `${BASE_URL}/api/v1/nodes?limit=1`,
    (body) =>
      typeof (body as { total?: number }).total === "number" &&
      (body as { total: number }).total > 0,
    DATA_TIMEOUT_MS,
    "seeded data to be visible via the API",
  );
}

async function mintSessionCookie(
  sub: string,
  name: string,
  email: string,
  roles: string,
): Promise<string> {
  const { stdout } = await execFileAsync(PYTHON, [
    path.join(HERE, "mint_session.py"),
    SESSION_SECRET,
    sub,
    name,
    email,
    roles,
  ]);
  const cookie = stdout.trim();
  if (!cookie) {
    throw new Error("mint_session.py produced an empty cookie");
  }
  return cookie;
}

async function writeStorageState(cookie: string, file: string): Promise<void> {
  const browser = await chromium.launch();
  try {
    const context = await browser.newContext();
    await context.addCookies([
      {
        name: "meshcore-session",
        value: cookie,
        domain: new URL(BASE_URL).hostname,
        path: "/",
        httpOnly: true,
        secure: false,
        sameSite: "Lax",
      },
    ]);
    await context.storageState({ path: file });
  } finally {
    await browser.close();
  }
}

export default async function globalSetup(): Promise<void> {
  await seedDatabase();
  await waitForStack();

  fs.mkdirSync(AUTH_DIR, { recursive: true });
  const adminCookie = await mintSessionCookie(
    "pw-admin",
    "PW Admin",
    "pw-admin@example.com",
    "admin,member",
  );
  const memberCookie = await mintSessionCookie(
    "pw-member",
    "PW Member",
    "pw-member@example.com",
    "member",
  );
  await writeStorageState(adminCookie, path.join(AUTH_DIR, "admin.json"));
  await writeStorageState(memberCookie, path.join(AUTH_DIR, "member.json"));
}
