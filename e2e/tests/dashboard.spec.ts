import { expect, test } from "@playwright/test";

test.describe("dashboard", () => {
  test("all widgets render", async ({ page }) => {
    await page.goto("/dashboard");
    const main = page.locator("main");

    await expect(main.getByRole("heading", { name: "Dashboard" })).toBeVisible();

    for (const title of [
      "Nodes",
      "Adverts",
      "Messages",
      "Packets",
      "Packet Types",
      "Path Bytes",
      "Route Health",
      "Route Trends",
      "Recent Adverts",
      "Recent Channel Messages",
    ]) {
      await expect(main.getByText(title, { exact: true }).first()).toBeVisible();
    }

    expect(await page.locator("canvas").count()).toBeGreaterThanOrEqual(5);

    await expect(main.getByText("Alpha Site")).toBeVisible();
    await expect(main.getByText("Bravo Site").first()).toBeVisible();

    await expect(main.getByText("Alpha Node").first()).toBeVisible();
    await expect(
      main.locator('a[href^="/nodes/"]').first(),
    ).toBeVisible();
  });
});
