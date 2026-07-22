import { expect, test } from "@playwright/test";

const HERO_TARGETS = [
  "/dashboard",
  "/nodes",
  "/advertisements",
  "/routes",
  "/channels",
  "/messages",
  "/packets",
  "/map",
  "/members",
];

test.describe("home", () => {
  test("renders hero, stats and activity panels", async ({ page }) => {
    await page.goto("/");

    await expect(page.locator("h1.hero-title")).toHaveText("Test Network");
    await expect(
      page.getByText("Welcome to the Test Network mesh network dashboard."),
    ).toBeVisible();

    const stats = page.locator(".stat");
    await expect(stats.first()).toBeVisible();
    expect(await stats.count()).toBeGreaterThanOrEqual(4);
    await expect(page.getByText("All discovered nodes")).toBeVisible();

    await expect(
      page.getByRole("heading", { name: "Network Activity" }),
    ).toBeVisible();
    expect(await page.locator("canvas").count()).toBeGreaterThanOrEqual(1);
  });

  test("hero navigation links work", async ({ page }) => {
    await page.goto("/");
    const cards = page.getByTestId("hero-card");
    await expect(cards.first()).toBeVisible();

    for (const href of HERO_TARGETS) {
      const card = page.locator(
        `[data-testid="hero-card"][data-hero-href="${href}"]`,
      );
      await expect(card).toBeVisible();
      await card.click();
      await expect(page).toHaveURL(new RegExp(href));
      await page.goto("/");
    }
  });
});
