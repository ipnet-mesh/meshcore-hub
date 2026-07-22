import { expect, test } from "@playwright/test";
import { countApiCalls, expectListLoaded, openFilters } from "../utils/helpers";

const ALPHA_KEY = "a1fa" + "0".repeat(60);
const AD01_HASH = "ad01" + "0".repeat(28);

test.describe("packets", () => {
  test("filter options work", async ({ page }) => {
    await page.goto("/packets");
    await expectListLoaded(page);
    await expect(page.getByTestId("list-row")).toHaveCount(10);

    await openFilters(page);
    await page.locator('select[name="event_type"]').selectOption("advertisement");
    await page.getByRole("button", { name: "Filter" }).click();
    await expect(page).toHaveURL(/event_type=advertisement/);
    await expect(page.getByTestId("list-row")).toHaveCount(6);

    await openFilters(page);
    await page.locator('select[name="path_hash_bytes"]').selectOption("2");
    await page.getByRole("button", { name: "Filter" }).click();
    await expect(page).toHaveURL(/path_hash_bytes=2/);
    await expect(page.getByTestId("list-row")).toHaveCount(6);
  });

  test("auto-refresh works and can be paused", async ({ page }) => {
    await page.goto("/packets");
    await expectListLoaded(page);

    const toggle = page.getByTestId("auto-refresh-toggle");
    await expect(toggle).toBeChecked();

    const active = await countApiCalls(page, "/api/v1/packet-groups?", 5000);
    expect(active).toBeGreaterThanOrEqual(2);

    await toggle.click();
    await expect(toggle).not.toBeChecked();
    const paused = await countApiCalls(page, "/api/v1/packet-groups?", 4500);
    expect(paused).toBe(0);
  });

  test("row click opens the packet group detail", async ({ page }) => {
    await page.goto("/packets");
    await expectListLoaded(page);

    await page.getByTestId("list-row").first().click();
    await expect(page).toHaveURL(/\/packets\/hash\//);
    await expect(page.locator('nav[aria-label="Breadcrumb"]')).toBeVisible();
  });

  test("clicking a path node renders the matching-nodes overlay", async ({
    page,
  }) => {
    await page.goto(`/packets/hash/${AD01_HASH}`);

    // Badges render twice (desktop table + hidden mobile cards): scope to visible.
    const pathHops = page.locator('[data-testid="path-hop"]:visible');
    await expect(pathHops.first()).toBeVisible();
    for (const hash of ["A1FA", "B2B0", "C3C0"]) {
      await expect(
        page.locator(`[data-testid="path-hop"][data-hash="${hash}"]:visible`).first(),
      ).toBeVisible();
    }

    await page
      .locator('[data-testid="path-hop"][data-hash="A1FA"]:visible')
      .first()
      .click();
    const popover = page.getByTestId("path-nodes-popover");
    await expect(popover).toBeVisible();
    await expect(popover.getByText("Nodes matching A1FA")).toBeVisible();
    await expect(popover.getByText("Alpha Node")).toBeVisible();

    await popover.getByTestId("path-node-link").first().click();
    await expect(page).toHaveURL(new RegExp(`/nodes/${ALPHA_KEY}`));
    await expect(page.getByText("Alpha Node").first()).toBeVisible();

    await page.goto(`/packets/hash/${AD01_HASH}`);
    await page
      .locator('[data-testid="path-hop"][data-hash="B2B0"]:visible')
      .first()
      .click();
    await expect(page.getByTestId("path-nodes-popover")).toBeVisible();
    await expect(page.getByText("Bravo Node").first()).toBeVisible();
    await page
      .getByTestId("path-nodes-popover")
      .getByRole("button", { name: "close" })
      .click();
    await expect(page.getByTestId("path-nodes-popover")).toHaveCount(0);
  });
});
