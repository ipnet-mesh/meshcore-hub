import { expect, test } from "@playwright/test";

const NAV_TARGETS = [
  "/",
  "/dashboard",
  "/nodes",
  "/advertisements",
  "/routes",
  "/channels",
  "/messages",
  "/packets",
  "/map",
  "/members",
  "/pages/about",
];

test.describe("global", () => {
  test("all navigation links work", async ({ page }) => {
    await page.goto("/");
    // Scope to the desktop menu: MobileNav renders the same links (hidden >= lg).
    const navLinks = page.locator(".navbar-center [data-testid='nav-link']");
    await expect(navLinks.first()).toBeVisible();

    await expect(navLinks).toHaveCount(NAV_TARGETS.length);
    for (const href of NAV_TARGETS) {
      await expect(
        page.locator(`.navbar-center [data-nav-href="${href}"]`),
      ).toHaveCount(1);
    }

    for (const href of NAV_TARGETS) {
      const link = page.locator(`.navbar-center [data-nav-href="${href}"]`);
      await link.click();
      await expect(page).toHaveURL(new RegExp(href === "/" ? "/$" : href));
      await expect(link).toHaveClass(/active/);
    }
  });

  test("dark/light toggle works and persists", async ({ page }) => {
    await page.goto("/");
    // The checkbox itself is visually hidden by daisyUI's swap; click the label.
    const toggle = page.getByTestId("theme-toggle");
    const toggleControl = page.locator("label.swap");
    const html = page.locator("html");

    await expect(html).toHaveAttribute("data-theme", "dark");
    await expect(toggle).not.toBeChecked();

    await toggleControl.click();
    await expect(html).toHaveAttribute("data-theme", "light");
    await expect(toggle).toBeChecked();

    await page.reload();
    await expect(html).toHaveAttribute("data-theme", "light");

    await page.locator("label.swap").click();
    await expect(html).toHaveAttribute("data-theme", "dark");

    await page.reload();
    await expect(html).toHaveAttribute("data-theme", "dark");
  });
});
