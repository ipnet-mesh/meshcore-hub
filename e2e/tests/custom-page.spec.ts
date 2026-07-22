import { expect, test } from "@playwright/test";

test.describe("custom pages", () => {
  test("markdown content is rendered", async ({ page }) => {
    await page.goto("/pages/about");

    const prose = page.locator(".card-body .prose");
    await expect(prose).toBeVisible();
    await expect(
      prose.getByRole("heading", { name: "About the E2E Network" }),
    ).toBeVisible();
    await expect(prose.getByText("rendered from markdown")).toBeVisible();
    await expect(
      prose.getByText("Fetched by the SPA from /spa/pages/about"),
    ).toBeVisible();
  });

  test("custom page appears in the navigation", async ({ page }) => {
    await page.goto("/");

    const link = page.locator('[data-testid="nav-link"][data-nav-href="/pages/about"]');
    await expect(link.first()).toBeVisible();
    await link.first().click();
    await expect(page).toHaveURL(/\/pages\/about/);
    await expect(page.locator(".card-body .prose")).toBeVisible();
  });

  test("heading anchor updates the URL hash on click", async ({ page }) => {
    await page.goto("/pages/about");

    // rehype-slug assigns the id; rehype-autolink-headings (behavior: "wrap")
    // wraps the heading text in an <a href="#getting-started">.
    const anchor = page.locator("h2#getting-started a");
    await expect(anchor).toHaveAttribute("href", "#getting-started");
    await anchor.click();
    await expect(page).toHaveURL(/#getting-started$/);
  });

  test("direct hash navigation scrolls the heading into view", async ({ page }) => {
    // Exercises the async-load scroll effect in CustomPage.tsx: the heading is
    // absent until /spa/pages/about resolves, then scrollIntoView fires.
    await page.goto("/pages/about#getting-started");

    const heading = page.getByRole("heading", { name: "Getting Started" });
    await expect(heading).toBeInViewport();
  });

  test("unknown slug shows a not-found error", async ({ page }) => {
    await page.goto("/pages/does-not-exist");

    const alert = page.locator('[role="alert"]');
    await expect(alert).toBeVisible();
    await expect(alert).toContainText(/not found/i);
  });
});
