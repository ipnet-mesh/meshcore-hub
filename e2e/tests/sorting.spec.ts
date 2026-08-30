import { expect, test } from "@playwright/test";
import { expectListLoaded } from "../utils/helpers";

test.describe("sortable tables", () => {
  test("nodes sort by name ascending then descending", async ({ page }) => {
    await page.goto("/nodes");
    await expectListLoaded(page);

    await page.getByTestId("sort-header-name").click();
    await expect(page).toHaveURL(/sort=name/);
    await expect(page).toHaveURL(/order=asc/);
    await expect(
      page.locator('th:has([data-testid="sort-header-name"])'),
    ).toHaveAttribute("aria-sort", "ascending");
    await expect(page.getByTestId("list-row").first()).toContainText("Alpha Node");
    await expect(page.getByTestId("list-row").last()).toContainText("South Observer 2");

    await page.getByTestId("sort-header-name").click();
    await expect(page).toHaveURL(/order=desc/);
    await expect(
      page.locator('th:has([data-testid="sort-header-name"])'),
    ).toHaveAttribute("aria-sort", "descending");
    await expect(page.getByTestId("list-row").first()).toContainText("South Observer 2");
  });

  test("messages sort by time oldest first then newest first", async ({
    page,
  }) => {
    await page.goto("/messages");
    await expectListLoaded(page);

    // Default is time desc; the first click flips to ascending.
    await page.getByTestId("sort-header-time").click();
    await expect(page).toHaveURL(/sort=time/);
    await expect(page).toHaveURL(/order=asc/);
    await expect(page.getByTestId("list-row").first()).toContainText("Ops channel traffic");

    await page.getByTestId("sort-header-time").click();
    await expect(page).toHaveURL(/order=desc/);
    await expect(page.getByTestId("list-row").first()).toContainText("Hello from the e2e mesh");
  });

  test("advertisements sort by node name", async ({ page }) => {
    await page.goto("/advertisements");
    await expectListLoaded(page);

    await page.getByTestId("sort-header-node_name").click();
    await expect(page).toHaveURL(/sort=node_name/);
    await expect(page).toHaveURL(/order=asc/);
    await expect(page.getByTestId("list-row").first()).toContainText("Alpha Node");
  });
});
