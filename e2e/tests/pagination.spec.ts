import { expect, test } from "@playwright/test";
import { expectListLoaded } from "../utils/helpers";

test.describe("pagination", () => {
  test("packet groups paginate across pages", async ({ page }) => {
    await page.goto("/packets");
    await expectListLoaded(page);

    // 40 seeded groups, page size 20.
    await expect(page.getByTestId("list-row")).toHaveCount(20);
    await expect(page.getByTestId("pagination")).toBeVisible();
    await expect(
      page.locator('[data-testid="pagination-page"][data-page="1"]'),
    ).toHaveClass(/btn-active/);
    await expect(page.getByTestId("pagination-prev")).toBeDisabled();
    await expect(page.getByTestId("pagination-next")).toBeEnabled();

    await page
      .locator('[data-testid="pagination-page"][data-page="2"]')
      .click();
    await expect(page).toHaveURL(/page=2/);
    await expectListLoaded(page);
    await expect(page.getByTestId("list-row")).toHaveCount(20);
    await expect(
      page.locator('[data-testid="pagination-page"][data-page="2"]'),
    ).toHaveClass(/btn-active/);
    await expect(page.getByTestId("pagination-next")).toBeDisabled();
    await expect(page.getByTestId("pagination-prev")).toBeEnabled();

    await page.getByTestId("pagination-prev").click();
    await expect(page).toHaveURL(/page=1/);
  });

  test("pagination links preserve active filters", async ({ page }) => {
    await page.goto("/packets?event_type=trace_data");
    await expectListLoaded(page);

    // 30 filler groups -> two pages.
    await expect(page.getByTestId("list-row")).toHaveCount(20);
    const next = page.getByTestId("pagination-next");
    await expect(next).toHaveAttribute(
      "href",
      /page=2/,
    );
    await expect(next).toHaveAttribute("href", /event_type=trace_data/);

    await next.click();
    await expect(page).toHaveURL(/page=2/);
    await expect(page).toHaveURL(/event_type=trace_data/);
    await expect(page.getByTestId("list-row")).toHaveCount(10);
  });

  test("out-of-range pages render the empty state", async ({ page }) => {
    await page.goto("/packets?page=9");
    await expect(page.getByText("No packets found")).toBeVisible();
    await expect(page.getByTestId("list-row")).toHaveCount(0);
  });
});
