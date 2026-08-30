import { expect, test, type Page } from "@playwright/test";
import { openFilters } from "../utils/helpers";

/** Count nodes represented on the map: individual markers plus the totals
 * shown on cluster badges (markers merge into clusters at low zooms). */
async function mapNodeCount(page: Page): Promise<number> {
  return page.evaluate(() => {
    const singles = document.querySelectorAll(".map-marker").length;
    const clustered = Array.from(
      document.querySelectorAll<HTMLElement>("[data-testid='cluster-count']"),
    ).reduce((sum, badge) => {
      const count = Number.parseInt(
        (badge.textContent ?? "").replace(/[^\d]/g, ""),
        10,
      );
      return sum + (Number.isNaN(count) ? 0 : count);
    }, 0);
    return singles + clustered;
  });
}

test.describe("map", () => {
  test("renders markers and filter options work (incl. show labels)", async ({
    page,
  }) => {
    await page.goto("/map");

    const markers = page.locator(".map-marker");
    const clusters = page.locator("[data-testid='cluster-count']");
    await expect(markers.first()).toBeVisible();
    await expect.poll(() => mapNodeCount(page)).toBe(7);
    await expect(page.getByText("7 nodes on map")).toBeVisible();

    // Densely spaced nodes merge into count badges; clicking one zooms in
    // and spreads its children into individual markers (nodes outside the
    // zoomed viewport are culled from the DOM, so count them only when the
    // whole network is on screen).
    await expect(clusters.first()).toBeVisible();
    await clusters.first().click();
    await expect.poll(() => markers.count()).toBeGreaterThanOrEqual(2);

    await openFilters(page);

    await page
      .locator('select:has(option[value="repeater"])')
      .selectOption("repeater");
    await expect.poll(() => mapNodeCount(page)).toBe(5);
    await expect(page.getByText("5 shown")).toBeVisible();

    // Zoom into a cluster so at least one marker is unclustered before the
    // label visibility check (clustered markers are not in the DOM).
    await clusters.first().click();
    await expect.poll(() => markers.count()).toBeGreaterThanOrEqual(2);
    await page.getByLabel("Show Labels").check();
    await expect(page.locator(".show-labels").first()).toBeVisible();
    await expect(page.locator(".map-label").first()).toBeVisible();

    await page.getByRole("button", { name: "Clear Filters" }).click();
    await expect.poll(() => mapNodeCount(page)).toBe(7);
    await expect(page.locator(".show-labels")).toHaveCount(0);
    await expect(page.getByLabel("Show Labels")).not.toBeChecked();
  });

  test("marker popup links to node detail", async ({ page }) => {
    await page.goto("/map");

    // Zoom into a cluster first: its markers separate near the middle of the
    // map, clear of the sticky navbar and the announcement banners that push
    // the initial markers toward the page top.
    const clusters = page.locator("[data-testid='cluster-count']");
    await expect(clusters.first()).toBeVisible();
    await clusters.first().click();

    const firstMarker = page.locator(".map-marker").first();
    await expect(firstMarker).toBeVisible();
    await firstMarker.click();

    const popup = page.locator(".leaflet-popup");
    await expect(popup).toBeVisible();
    await popup.getByRole("link", { name: "View Details" }).click();
    await expect(page).toHaveURL(/\/nodes\/[0-9a-f]{64}/);
  });
});
