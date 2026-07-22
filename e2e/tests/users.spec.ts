import { expect, test } from "@playwright/test";
import { MEMBER_STATE } from "../utils/helpers";

test.use({ storageState: MEMBER_STATE });

test.describe("users", () => {
  test("user profile menu works", async ({ page }) => {
    await page.goto("/");

    await page.getByTestId("user-menu").click();
    await expect(page.getByText("PW Member")).toBeVisible();
    await expect(page.getByText("member", { exact: true })).toBeVisible();
    await expect(page.getByTestId("user-menu-profile")).toBeVisible();
    await expect(page.getByTestId("user-menu-logout")).toBeVisible();
  });

  test("profile edit works and persists", async ({ page }) => {
    await page.goto("/profile");

    await expect(page.locator('input[name="name"]')).toBeVisible();
    await page.locator('input[name="name"]').fill("PW Member Edited");
    await page.locator('input[name="callsign"]').fill("E2EEDIT");
    await page
      .locator('input[name="description"]')
      .fill("Updated by Playwright");
    await page
      .locator('input[name="url"]')
      .fill("https://example.com/pw-member");

    await page.getByRole("button", { name: "Save Profile" }).click();
    await expect(page.getByRole("alert")).toContainText(
      "Profile updated successfully",
    );

    await page.reload();
    await expect(page.locator('input[name="name"]')).toHaveValue(
      "PW Member Edited",
    );
    await expect(page.locator('input[name="callsign"]')).toHaveValue("E2EEDIT");
    await expect(page.locator('input[name="description"]')).toHaveValue(
      "Updated by Playwright",
    );
    await expect(page.locator('input[name="url"]')).toHaveValue(
      "https://example.com/pw-member",
    );
  });
});
