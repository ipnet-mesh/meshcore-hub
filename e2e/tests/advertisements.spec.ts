import { expect, test } from "@playwright/test";
import { countApiCalls, expectListLoaded, openFilters } from "../utils/helpers";

const ALPHA_KEY = "a1fa" + "0".repeat(60);

test.use({ permissions: ["clipboard-read", "clipboard-write"] });

test.describe("advertisements", () => {
  test("filter options work", async ({ page }) => {
    await page.goto("/advertisements");
    await expectListLoaded(page);
    const table = page.locator("table");

    await openFilters(page);
    await page.locator('select[name="route_type"]').selectOption("all");
    await page.getByRole("button", { name: "Filter" }).click();
    await expect(page).toHaveURL(/route_type=all/);
    await expect(table.getByText("Charlie Node").first()).toBeVisible();

    await openFilters(page);
    await page.locator('input[name="search"]').fill("Bravo");
    await page.getByRole("button", { name: "Filter" }).click();
    await expect(page).toHaveURL(/search=Bravo/);
    // Two Bravo adverts (one per area); toHaveCount auto-waits out the refetch.
    await expect(page.getByTestId("list-row")).toHaveCount(2);
    await expect(table.getByText("Alpha Node")).toHaveCount(0);
  });

  test("auto-refresh works and can be paused", async ({ page }) => {
    await page.goto("/advertisements");
    await expectListLoaded(page);

    const toggle = page.getByTestId("auto-refresh-toggle");
    await expect(toggle).toBeChecked();

    const active = await countApiCalls(page, "/api/v1/advertisements?", 5000);
    expect(active).toBeGreaterThanOrEqual(2);

    await toggle.click();
    await expect(toggle).not.toBeChecked();
    const paused = await countApiCalls(page, "/api/v1/advertisements?", 4500);
    expect(paused).toBe(0);
  });

  test("table row actions work", async ({ page }) => {
    await page.goto("/advertisements");
    await expectListLoaded(page);
    const table = page.locator("table");

    await table.getByRole("link", { name: "Alpha Node" }).first().click();
    await expect(page).toHaveURL(new RegExp(`/nodes/${ALPHA_KEY}`));
    await page.goBack();
    await expectListLoaded(page);

    // Click a plain-text cell (Time): node links and copyable keys
    // stopPropagation / have their own handlers.
    await page.getByTestId("list-row").first().locator("td").nth(3).click();
    await expect(page).toHaveURL(/\/packets\/hash\//);

    await page.goto("/advertisements");
    await expectListLoaded(page);
    const copyable = table.locator('code[title="Click to copy"]').first();
    await copyable.click();
    await expect(page.getByText("Copied!").first()).toBeVisible();
  });

  test("observer toggles filter the list", async ({ page }) => {
    await page.goto("/advertisements");
    await expectListLoaded(page);

    const north = page.locator('[data-testid="observer-area"][data-area="North"]');
    const south = page.locator('[data-testid="observer-area"][data-area="South"]');
    await expect(north.first()).toBeVisible();
    await expect(south.first()).toBeVisible();
    await expect(page.getByTestId("list-row")).toHaveCount(5);

    await north.first().click();
    await expect(north.first()).toHaveClass(/badge-ghost/);
    await expect(page.getByTestId("list-row")).toHaveCount(3);

    await north.first().click();
    await expect(north.first()).toHaveClass(/badge-primary/);
    await expect(page.getByTestId("list-row")).toHaveCount(5);

    await south.first().click();
    await expect(page.getByTestId("list-row")).toHaveCount(2);
    await north.first().click();
    await expect(north.first()).toHaveClass(/badge-primary/);
    await expect(page.getByTestId("list-row")).toHaveCount(2);
  });
});
