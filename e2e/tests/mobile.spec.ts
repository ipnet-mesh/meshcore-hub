import { expect, test } from "@playwright/test";

test.use({ viewport: { width: 375, height: 667 } });

test.describe("mobile layout", () => {
  test("hamburger menu opens and navigates", async ({ page }) => {
    await page.goto("/");

    const menu = page.getByTestId("mobile-nav-menu");
    await expect(menu).not.toBeVisible();

    await page.getByTestId("mobile-nav-toggle").click();
    await expect(menu).toBeVisible();
    await expect(menu.getByTestId("nav-link").first()).toBeVisible();

    await menu.locator('[data-testid="nav-link"][data-nav-href="/messages"]').click();
    await expect(page).toHaveURL("/messages");
    // The desktop table (and its list-rows) is hidden at mobile widths; the
    // mobile cards and sort select render instead.
    await expect(page.getByTestId("mobile-sort-select")).toBeVisible();
    await expect(
      page.getByText("Hello from the e2e mesh").first(),
    ).toBeVisible();
  });

  test("nodes list renders mobile cards with the sort select", async ({
    page,
  }) => {
    await page.goto("/nodes");

    // Desktop table is hidden on small screens; mobile cards render instead.
    await expect(page.locator("table")).toBeHidden();
    await expect(page.getByTestId("mobile-sort-select")).toBeVisible();

    const sortSelect = page.getByTestId("mobile-sort-select");
    await sortSelect.selectOption("name:asc");
    await expect(page).toHaveURL(/sort=name/);
    await expect(page).toHaveURL(/order=asc/);

    const firstCard = page.locator("a.card").first();
    await expect(firstCard).toContainText("Alpha Node");
  });
});
