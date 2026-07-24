import { expect, test } from "@playwright/test";
import { OPERATOR_STATE } from "../utils/helpers";

test.use({ storageState: OPERATOR_STATE });

const ROUTE_LABEL = "Op From \u2192 Op To";

test.describe.serial("routes (operator)", () => {
  test("operator can manage routes; admin visibility tier is hidden", async ({
    page,
  }) => {
    await page.goto("/routes");

    // Operators see the seeded community route and the add button.
    const seededCard = page.locator(
      '[data-testid="route-card"][data-route-label="Alpha Site \u2192 Bravo Site"]',
    );
    await expect(seededCard).toBeVisible();
    await expect(page.getByTestId("add-route")).toBeVisible();

    // The seeded route has NULL created_by — operator must NOT see edit/delete.
    await expect(seededCard.getByTestId("edit-route")).toHaveCount(0);
    await expect(seededCard.getByTestId("delete-route")).toHaveCount(0);

    // The visibility dropdown must NOT offer the admin tier to an operator.
    await page.getByTestId("add-route").click();
    const modal = page.locator('[data-testid="route-modal"]');
    await expect(modal).toBeVisible();
    const visibility = page.getByTestId("route-visibility");
    await expect(visibility.locator("option[value='admin']")).toHaveCount(0);
    await visibility.selectOption("operator");
    await expect(visibility).toHaveValue("operator");

    await page.getByTestId("route-from").fill("Op From");
    await page.getByTestId("route-to").fill("Op To");

    await page.getByTestId("route-path-search").fill("Alpha");
    await page.getByTestId("node-search-result").first().click();
    await page.getByTestId("route-path-search").fill("Bravo");
    await page.getByTestId("node-search-result").first().click();
    await expect(page.getByTestId("route-path-chip")).toHaveCount(2);

    await page.getByTestId("route-save").click();
    await expect(modal).toHaveCount(0);

    const card = page.locator(
      `[data-testid="route-card"][data-route-label="${ROUTE_LABEL}"]`,
    );
    await expect(card).toBeVisible();

    // Operator owns the route they just created — edit/delete should be present.
    await card.getByTestId("edit-route").click();
    await expect(modal).toBeVisible();
    await expect(page.getByTestId("route-from")).toHaveValue("Op From");
    await page.getByTestId("route-cancel").click();

    // Operator can delete the route they created.
    await card.getByTestId("delete-route").click();
    const confirm = page.locator("dialog.modal-open");
    await expect(confirm).toBeVisible();
    await confirm.getByRole("button", { name: "Delete" }).click();
    await expect(card).toHaveCount(0);
  });
});
