import { expect, test } from "@playwright/test";

test.describe("empty states", () => {
  test("nodes search with no matches shows the empty state", async ({ page }) => {
    await page.goto("/nodes?search=NoMatchToBeFound");
    await expect(page.getByText("No nodes found")).toBeVisible();
    await expect(page.getByTestId("list-row")).toHaveCount(0);
  });

  test("advertisements search with no matches shows the empty state", async ({
    page,
  }) => {
    await page.goto("/advertisements?search=NoMatchToBeFound");
    await expect(page.getByText("No adverts found")).toBeVisible();
    await expect(page.getByTestId("list-row")).toHaveCount(0);
  });

  test("messages filtered to an unknown channel show the empty state", async ({
    page,
  }) => {
    await page.goto("/messages?channel_idx=99999");
    await expect(page.getByText("No messages found")).toBeVisible();
    await expect(page.getByTestId("list-row")).toHaveCount(0);
  });

  test("packets search with no matches shows the empty state", async ({
    page,
  }) => {
    await page.goto("/packets?search=NoMatchToBeFound");
    await expect(page.getByText("No packets found")).toBeVisible();
    await expect(page.getByTestId("list-row")).toHaveCount(0);
  });
});
