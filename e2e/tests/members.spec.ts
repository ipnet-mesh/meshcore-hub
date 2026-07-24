import { expect, test } from "@playwright/test";
import { MEMBER_STATE } from "../utils/helpers";

const BRAVO_KEY = "b2b0" + "0".repeat(60);

test.use({ storageState: MEMBER_STATE });

test.describe("members", () => {
  test("lists operators and members", async ({ page }) => {
    await page.goto("/members");

    // Level 2: the group headings (level 1 is the page title "Members").
    await expect(
      page.getByRole("heading", { name: "Operators", level: 2 }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Members", level: 2 }),
    ).toBeVisible();
    await expect(page.getByText("Op North")).toBeVisible();
    await expect(page.getByText("Mem South")).toBeVisible();
    expect(await page.getByTestId("member-card").count()).toBeGreaterThanOrEqual(4);
  });

  test("clicking a member shows the profile page", async ({ page }) => {
    await page.goto("/members");

    await page
      .getByTestId("member-card")
      .filter({ hasText: "Mem South" })
      .first()
      .click();
    await expect(page).toHaveURL(/\/profile\/[0-9a-f-]{36}/);
    await expect(page.getByText("Mem South").first()).toBeVisible();
    await expect(page.locator('nav[aria-label="Breadcrumb"]')).toBeVisible();

    // A member viewing another user's profile must NOT see the admin edit
    // button.
    await expect(page.getByTestId("profile-admin-edit")).toHaveCount(0);
  });

  test("clicking a member node shows the node detail page", async ({ page }) => {
    await page.goto("/members");

    const card = page
      .getByTestId("member-card")
      .filter({ hasText: "Mem South" })
      .first();
    await card
      .locator(`[data-testid="member-node-badge"][data-node-key="${BRAVO_KEY}"]`)
      .click();
    await expect(page).toHaveURL(new RegExp(`/nodes/${BRAVO_KEY}`));
    await expect(page.getByText("Bravo Node").first()).toBeVisible();
  });
});
