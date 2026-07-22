import path from "node:path";
import { fileURLToPath } from "node:url";
import { expect, type Page } from "@playwright/test";

const AUTH_DIR = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  ".auth",
);
export const ADMIN_STATE = path.join(AUTH_DIR, "admin.json");
export const MEMBER_STATE = path.join(AUTH_DIR, "member.json");

export async function expectListLoaded(page: Page): Promise<void> {
  await expect(page.getByTestId("list-row").first()).toBeVisible();
}

export async function openFilters(page: Page): Promise<void> {
  const toggle = page.locator("#filter-toggle");
  if (!(await toggle.isChecked())) {
    await toggle.click();
  }
}

export async function countApiCalls(
  page: Page,
  urlFragment: string,
  durationMs: number,
): Promise<number> {
  let count = 0;
  const onRequest = (request: { url: () => string }): void => {
    if (request.url().includes(urlFragment)) {
      count += 1;
    }
  };
  page.on("request", onRequest);
  await page.waitForTimeout(durationMs);
  page.off("request", onRequest);
  return count;
}
