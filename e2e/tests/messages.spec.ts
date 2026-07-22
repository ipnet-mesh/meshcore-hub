import { expect, test } from "@playwright/test";
import { countApiCalls, expectListLoaded, openFilters } from "../utils/helpers";

test.describe("messages", () => {
  test("filter options work", async ({ page }) => {
    await page.goto("/messages");
    await expectListLoaded(page);
    const table = page.locator("table");
    await expect(page.getByTestId("list-row")).toHaveCount(4);

    await openFilters(page);
    await page.locator('select[name="message_type"]').selectOption("channel");
    await page.getByRole("button", { name: "Filter" }).click();
    await expect(page).toHaveURL(/message_type=channel/);
    await expect(page.getByTestId("list-row")).toHaveCount(3);

    // The channel select auto-submits on change.
    await openFilters(page);
    await page
      .locator('select[name="channel_idx"]')
      .selectOption({ label: "E2E General" });
    await expect(page).toHaveURL(/channel_idx=\d+/);
    await expect(page.getByTestId("list-row")).toHaveCount(1);
    await expect(table.getByText("Ops channel traffic")).toBeVisible();

    await page.goto("/messages");
    await expectListLoaded(page);
    await expect(page.getByTestId("list-row")).toHaveCount(4);
  });

  test("auto-refresh works and can be paused", async ({ page }) => {
    await page.goto("/messages");
    await expectListLoaded(page);

    const toggle = page.getByTestId("auto-refresh-toggle");
    await expect(toggle).toBeChecked();

    const active = await countApiCalls(page, "/api/v1/messages?", 5000);
    expect(active).toBeGreaterThanOrEqual(2);

    await toggle.click();
    await expect(toggle).not.toBeChecked();
    const paused = await countApiCalls(page, "/api/v1/messages?", 4500);
    expect(paused).toBe(0);
  });

  test("table row actions and observer toggle work", async ({ page }) => {
    await page.goto("/messages");
    await expectListLoaded(page);
    const table = page.locator("table");

    await expect(table.locator("span.observer-badge").first()).toBeVisible();

    // Click a plain-text cell (Time) so the row handler navigates.
    await page.getByTestId("list-row").first().locator("td").nth(1).click();
    await expect(page).toHaveURL(/\/packets\/hash\//);

    await page.goto("/messages");
    await expectListLoaded(page);
    await expect(page.getByTestId("list-row")).toHaveCount(4);

    const north = page
      .locator('[data-testid="observer-area"][data-area="North"]')
      .first();
    await north.click();
    await expect(north).toHaveClass(/badge-ghost/);
    await expect(page.getByTestId("list-row")).toHaveCount(2);
  });
});
