import { expect, test } from "@playwright/test";
import { ADMIN_STATE } from "../utils/helpers";

test.use({ storageState: ADMIN_STATE });

const ROUTE_LABEL = "E2E From \u2192 E2E To";

test.describe.serial("routes (admin)", () => {
  test("add route displays the modal and all options are persisted", async ({
    page,
  }) => {
    await page.goto("/routes");

    const seededCard = page.locator(
      '[data-testid="route-card"][data-route-label="Alpha Site \u2192 Bravo Site"]',
    );
    await expect(seededCard).toBeVisible();

    // Admin sees edit/delete on all routes, including legacy (NULL created_by) ones.
    await expect(seededCard.getByTestId("edit-route")).toBeVisible();
    await expect(seededCard.getByTestId("delete-route")).toBeVisible();

    await page.getByTestId("add-route").click();
    const modal = page.locator('[data-testid="route-modal"]');
    await expect(modal).toBeVisible();
    await expect(page.locator("dialog h3")).toHaveText("Add Route");

    await page.getByTestId("route-from").fill("E2E From");
    await page.getByTestId("route-to").fill("E2E To");
    await page.getByTestId("route-description").fill("Created by Playwright");
    await page.getByTestId("route-visibility").selectOption("operator");
    await page.locator('[data-testid="route-width"][data-width="2"]').click();
    await expect(
      page.locator('[data-testid="route-width"][data-width="2"]'),
    ).toHaveClass(/btn-primary/);

    await page.getByTestId("route-path-search").fill("Alpha");
    await page.getByTestId("node-search-result").first().click();
    await expect(page.getByTestId("route-path-chip")).toHaveCount(1);

    await page.getByTestId("route-path-search").fill("Bravo");
    await page.getByTestId("node-search-result").first().click();
    await expect(page.getByTestId("route-path-chip")).toHaveCount(2);
    await expect(modal.getByText("Alpha Node")).toBeVisible();
    await expect(modal.getByText("Bravo Node")).toBeVisible();

    await page.getByTestId("route-observer-search").fill("North");
    await page.getByTestId("node-search-result").first().click();
    await expect(modal.getByText(/North Observer/).first()).toBeVisible();

    await page.getByTestId("route-window").fill("72");
    await page.getByTestId("route-threshold").fill("4");
    await page.getByTestId("route-clear-threshold").fill("8");
    await page.getByTestId("route-max-span").fill("6");
    await page.getByTestId("route-max-path-length").fill("5");
    await page.getByTestId("route-enabled").setChecked(false);
    await page.getByTestId("route-reversible").setChecked(false);

    await page.getByTestId("route-save").click();
    await expect(modal).toHaveCount(0);

    const card = page.locator(
      `[data-testid="route-card"][data-route-label="${ROUTE_LABEL}"]`,
    );
    await expect(card).toBeVisible();

    await card.getByTestId("edit-route").click();
    await expect(modal).toBeVisible();
    await expect(page.locator("dialog h3")).toHaveText("Edit Route");

    await expect(page.getByTestId("route-from")).toHaveValue("E2E From");
    await expect(page.getByTestId("route-to")).toHaveValue("E2E To");
    await expect(page.getByTestId("route-description")).toHaveValue(
      "Created by Playwright",
    );
    await expect(page.getByTestId("route-visibility")).toHaveValue("operator");
    await expect(
      page.locator('[data-testid="route-width"][data-width="2"]'),
    ).toHaveClass(/btn-primary/);
    await expect(page.getByTestId("route-path-chip")).toHaveCount(2);
    await expect(modal.getByText("Alpha Node")).toBeVisible();
    await expect(modal.getByText("Bravo Node")).toBeVisible();
    await expect(modal.getByText(/North Observer/).first()).toBeVisible();
    await expect(page.getByTestId("route-window")).toHaveValue("72");
    await expect(page.getByTestId("route-threshold")).toHaveValue("4");
    await expect(page.getByTestId("route-clear-threshold")).toHaveValue("8");
    await expect(page.getByTestId("route-max-span")).toHaveValue("6");
    await expect(page.getByTestId("route-max-path-length")).toHaveValue("5");
    await expect(page.getByTestId("route-enabled")).not.toBeChecked();
    await expect(page.getByTestId("route-reversible")).not.toBeChecked();

    await page.getByTestId("route-cancel").click();
    await expect(modal).toHaveCount(0);
  });

  test("saving with fewer than 2 path nodes is rejected", async ({ page }) => {
    await page.goto("/routes");
    await page.getByTestId("add-route").click();

    await page.getByTestId("route-from").fill("Bad");
    await page.getByTestId("route-to").fill("Route");
    await page.getByTestId("route-path-search").fill("Alpha");
    await page.getByTestId("node-search-result").first().click();
    await expect(page.getByTestId("route-path-chip")).toHaveCount(1);

    // The alert blocks the page until dismissed, so accept it the moment it
    // appears (handling it only after the awaited click would deadlock).
    const dialogPromise = page.waitForEvent("dialog");
    void dialogPromise.then((dialog) => dialog.accept());
    await page.getByTestId("route-save").click();
    expect((await dialogPromise).message()).toBe(
      "At least 2 path nodes are required.",
    );

    await expect(page.locator('[data-testid="route-modal"]')).toBeVisible();
    await page.getByTestId("route-cancel").click();
  });

  test("delete route shows a confirm dialog and removes the route", async ({
    page,
  }) => {
    await page.goto("/routes");

    const card = page.locator(
      `[data-testid="route-card"][data-route-label="${ROUTE_LABEL}"]`,
    );
    await expect(card).toBeVisible();
    await card.getByTestId("delete-route").click();

    const confirm = page.locator("dialog.modal-open");
    await expect(confirm).toBeVisible();
    await expect(
      confirm.getByRole("heading", { name: "Delete Route" }),
    ).toBeVisible();
    await expect(
      confirm.getByText(/Are you sure you want to delete route/),
    ).toBeVisible();

    await confirm.getByRole("button", { name: "Delete" }).click();
    await expect(card).toHaveCount(0);
  });
});
