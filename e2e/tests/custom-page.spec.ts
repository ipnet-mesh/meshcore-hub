import { expect, test } from "@playwright/test";

test.describe("custom pages", () => {
  test("markdown content is rendered", async ({ page }) => {
    await page.goto("/pages/about");

    const prose = page.locator(".prose");
    await expect(prose).toBeVisible();
    await expect(
      prose.getByRole("heading", { name: "About the E2E Network" }),
    ).toBeVisible();
    await expect(prose.getByText("rendered from markdown")).toBeVisible();
    await expect(
      prose.getByText("Fetched by the SPA from /spa/pages/about"),
    ).toBeVisible();
  });

  test("custom page appears in the navigation", async ({ page }) => {
    await page.goto("/");

    const link = page.locator('[data-testid="nav-link"][data-nav-href="/pages/about"]');
    await expect(link.first()).toBeVisible();
    await link.first().click();
    await expect(page).toHaveURL(/\/pages\/about/);
    await expect(page.locator(".prose")).toBeVisible();
  });
});
