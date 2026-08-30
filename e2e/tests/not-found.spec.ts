import { expect, test } from "@playwright/test";

test.describe("spa 404 page", () => {
  test("unknown routes render the not-found page with a way back", async ({
    page,
  }) => {
    await page.goto("/does-not-exist");

    const hero = page.getByTestId("not-found");
    await expect(hero).toBeVisible();
    await expect(hero.getByText("404")).toBeVisible();
    await expect(
      hero.getByRole("heading", { name: "Page not found" }),
    ).toBeVisible();
    await expect(
      hero.getByText("The page you're looking for doesn't exist or has been moved."),
    ).toBeVisible();

    await page.getByTestId("go-home").click();
    await expect(page).toHaveURL("/$");
  });

  test("unknown nested paths also land on the 404 page", async ({ page }) => {
    await page.goto("/dashboard/nested/unknown");
    await expect(page.getByTestId("not-found")).toBeVisible();
  });
});
