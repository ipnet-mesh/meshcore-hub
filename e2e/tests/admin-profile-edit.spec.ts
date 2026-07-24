import { expect, test } from "@playwright/test";
import { ADMIN_STATE } from "../utils/helpers";

test.use({ storageState: ADMIN_STATE });

test.describe.serial("admin profile edit", () => {
  test("admin can edit another user's profile", async ({ page }) => {
    await page.goto("/members");

    // Navigate to Mem South's profile (not the admin's own).
    await page
      .getByTestId("member-card")
      .filter({ hasText: "Mem South" })
      .first()
      .click();
    await expect(page).toHaveURL(/\/profile\//);

    // Admin sees the edit button (owner does NOT — sub mismatch).
    await expect(page.getByTestId("profile-admin-edit")).toBeVisible();

    // Click edit — form appears pre-filled with the target profile's values.
    await page.getByTestId("profile-admin-edit").click();
    await expect(page.getByTestId("profile-form")).toBeVisible();
    await expect(page.getByTestId("profile-name")).toHaveValue("Mem South");

    // Edit callsign and save.
    await page.getByTestId("profile-callsign").fill("ADMEDIT");
    await page.getByTestId("profile-save").click();

    // Read-only view returns with updated callsign badge.
    await expect(page.getByTestId("profile-admin-edit")).toBeVisible();
    await expect(page.getByText("ADMEDIT")).toBeVisible();
  });

  test("admin does not see admin edit button on own profile", async ({
    page,
  }) => {
    // Navigate to own profile via members page.
    await page.goto("/members");
    await page
      .getByTestId("member-card")
      .filter({ hasText: "PW Admin" })
      .first()
      .click();
    await expect(page).toHaveURL(/\/profile\//);

    // Admin IS the owner here — should see the owner edit link, not the
    // admin edit button.
    await expect(page.getByTestId("profile-admin-edit")).toHaveCount(0);
  });
});
