import { expect, test } from "@playwright/test";
import { countApiCalls, expectListLoaded, openFilters } from "../utils/helpers";

const ALPHA_KEY = "a1fa" + "0".repeat(60);

test.use({ permissions: ["clipboard-read", "clipboard-write"] });

test.describe("nodes", () => {
  test("filter options work", async ({ page }) => {
    await page.goto("/nodes");
    await expectListLoaded(page);
    // Scope to the desktop table: rows also exist as hidden mobile cards.
    const table = page.locator("table");
    const initialCount = await page.getByTestId("list-row").count();
    expect(initialCount).toBeGreaterThanOrEqual(4);

    await openFilters(page);

    await page.locator('input[name="search"]').fill("Alpha");
    await page.getByRole("button", { name: "Filter" }).click();
    await expect(page).toHaveURL(/search=Alpha/);
    await expect(page.getByTestId("list-row")).toHaveCount(1);
    await expect(table.getByText("Alpha Node").first()).toBeVisible();

    await page.getByRole("link", { name: "Clear" }).click();
    await expect(page).not.toHaveURL(/search=/);
    await expect(page.getByTestId("list-row")).toHaveCount(initialCount);

    await openFilters(page);
    await page.locator('select[name="adv_type"]').selectOption("repeater");
    await page.getByRole("button", { name: "Filter" }).click();
    await expect(page).toHaveURL(/adv_type=repeater/);
    await expect(table.getByText("Alpha Node")).toHaveCount(0);
    await expect(table.getByText("Bravo Node").first()).toBeVisible();
  });

  test("auto-refresh works and can be paused", async ({ page }) => {
    await page.goto("/nodes");
    await expectListLoaded(page);

    const toggle = page.getByTestId("auto-refresh-toggle");
    await expect(toggle).toBeVisible();
    await expect(toggle).toBeChecked();

    const active = await countApiCalls(page, "/api/v1/nodes?", 5000);
    expect(active).toBeGreaterThanOrEqual(2);

    await toggle.click();
    await expect(toggle).not.toBeChecked();
    const paused = await countApiCalls(page, "/api/v1/nodes?", 4500);
    expect(paused).toBe(0);
  });

  test("table row actions work", async ({ page }) => {
    await page.goto("/nodes");
    await expectListLoaded(page);
    const table = page.locator("table");

    await table.getByRole("link", { name: "Alpha Node" }).first().click();
    await expect(page).toHaveURL(new RegExp(`/nodes/${ALPHA_KEY}`));
    await expect(page.getByText("Alpha Node").first()).toBeVisible();
    await page.goBack();
    await expectListLoaded(page);

    const copyable = table.locator('code[title="Click to copy"]').first();
    await copyable.click();
    await expect(page.getByText("Copied!").first()).toBeVisible();
  });
});
