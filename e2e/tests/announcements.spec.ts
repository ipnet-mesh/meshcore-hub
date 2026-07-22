import { expect, test } from "@playwright/test";

test.describe("announcements", () => {
  test("system announcement renders markdown bold", async ({ page }) => {
    await page.goto("/");

    // SYSTEM_ANNOUNCEMENT=**Outage** window scheduled is shipped as raw
    // markdown in __APP_CONFIG__ and rendered client-side by <Markdown>.
    // **Outage** must become a <strong> element end-to-end.
    const banner = page.locator("#system-banner");
    await expect(banner).toBeVisible();
    await expect(banner.locator("strong")).toHaveText("Outage");
    await expect(banner).toContainText("window scheduled");
  });

  test("network announcement dismiss persists across reload", async ({ page }) => {
    await page.goto("/");

    const banner = page.locator("#flash-banner");
    await expect(banner).toBeVisible();
    await expect(banner.locator("strong")).toHaveText("Maintenance");

    await page.getByRole("button", { name: "Dismiss" }).click();
    await expect(banner).not.toBeVisible();

    // The dismiss flag is persisted in sessionStorage — reloading must NOT
    // bring the banner back.
    await page.reload();
    await expect(banner).not.toBeVisible();
  });
});
