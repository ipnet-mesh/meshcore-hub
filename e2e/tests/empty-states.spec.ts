import { expect, test } from "@playwright/test";

test.describe("empty states", () => {
  // The empty text renders twice (mobile EmptyState + desktop EmptyRow), so
  // scope every assertion to the desktop table cell.
  test("nodes search with no matches shows the empty state", async ({ page }) => {
    await page.goto("/nodes?search=NoMatchToBeFound");
    await expect(
      page.getByRole("cell", { name: "No nodes found", exact: true }),
    ).toBeVisible();
    await expect(page.getByTestId("list-row")).toHaveCount(0);
  });

  test("advertisements search with no matches shows the empty state", async ({
    page,
  }) => {
    await page.goto("/advertisements?search=NoMatchToBeFound");
    await expect(
      page.getByRole("cell", { name: "No adverts found", exact: true }),
    ).toBeVisible();
    await expect(page.getByTestId("list-row")).toHaveCount(0);
  });

  test("messages filtered to an unknown channel show the empty state", async ({
    page,
  }) => {
    await page.goto("/messages?channel_idx=99999");
    await expect(
      page.getByRole("cell", { name: "No messages found", exact: true }),
    ).toBeVisible();
    await expect(page.getByTestId("list-row")).toHaveCount(0);
  });

  test("packets search with no matches shows the empty state", async ({
    page,
  }) => {
    await page.goto("/packets?search=NoMatchToBeFound");
    await expect(
      page.getByRole("cell", { name: "No packets found", exact: true }),
    ).toBeVisible();
    await expect(page.getByTestId("list-row")).toHaveCount(0);
  });
});
