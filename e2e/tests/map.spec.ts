import { expect, test } from "@playwright/test";
import { openFilters } from "../utils/helpers";

test.describe("map", () => {
  test("renders markers and filter options work (incl. show labels)", async ({
    page,
  }) => {
    await page.goto("/map");

    const markers = page.locator(".map-marker");
    await expect(markers.first()).toBeVisible();
    await expect(markers).toHaveCount(7);
    await expect(page.getByText("7 nodes on map")).toBeVisible();

    await openFilters(page);

    await page
      .locator('select:has(option[value="repeater"])')
      .selectOption("repeater");
    await expect(markers).toHaveCount(5);
    await expect(page.getByText("5 shown")).toBeVisible();

    await page.getByLabel("Show Labels").check();
    await expect(page.locator(".show-labels").first()).toBeVisible();
    await expect(page.locator(".map-label").first()).toBeVisible();

    await page.getByRole("button", { name: "Clear Filters" }).click();
    await expect(markers).toHaveCount(7);
    await expect(page.locator(".show-labels")).toHaveCount(0);
    await expect(page.getByLabel("Show Labels")).not.toBeChecked();
  });

  test("marker popup links to node detail", async ({ page }) => {
    await page.goto("/map");
    await expect(page.locator(".map-marker").first()).toBeVisible();

    await page.locator(".map-marker").first().click();
    const popup = page.locator(".leaflet-popup");
    await expect(popup).toBeVisible();
    await popup.getByRole("link", { name: "View Details" }).click();
    await expect(page).toHaveURL(/\/nodes\/[0-9a-f]{64}/);
  });
});
