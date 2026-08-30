import { expect, test } from "@playwright/test";
import { ADMIN_STATE, MEMBER_STATE, OPERATOR_STATE } from "../utils/helpers";

const ALPHA_KEY = "a1fa" + "0".repeat(60);
const BRAVO_KEY = "b2b0" + "0".repeat(60);
const CHARLIE_KEY = "c3c0" + "0".repeat(60);
const DELTA_KEY = "d4d0" + "0".repeat(60);

test.describe("node detail (anonymous)", () => {
  test.use({ permissions: ["clipboard-read", "clipboard-write"] });

  test("node with coordinates renders the mini-map and contact QR", async ({
    page,
  }) => {
    await page.goto(`/nodes/${ALPHA_KEY}`);

    await expect(page.locator('nav[aria-label="Breadcrumb"]')).toBeVisible();
    await expect(page.getByRole("heading", { name: "Alpha Node" })).toBeVisible();
    await expect(page.getByTestId("node-mini-map")).toBeVisible();
    await expect(page.getByTestId("contact-qr").locator("svg")).toBeVisible();

    // The public key is copyable.
    const copyable = page.locator('code[title="Click to copy"]').first();
    await copyable.click();
    await expect(page.getByText("Copied!").first()).toBeVisible();
  });

  test("node without coordinates falls back to the QR card", async ({
    page,
  }) => {
    await page.goto(`/nodes/${DELTA_KEY}`);

    await expect(page.getByTestId("node-mini-map")).toHaveCount(0);
    await expect(page.getByTestId("contact-qr").locator("svg")).toBeVisible();
    await expect(page.getByText("Scan to add as contact")).toBeVisible();
  });

  test("short prefix resolves and redirects to the full key", async ({
    page,
  }) => {
    await page.goto("/n/a1fa");
    await expect(page).toHaveURL(new RegExp(`/nodes/${ALPHA_KEY}`));
    await expect(page.getByRole("heading", { name: "Alpha Node" })).toBeVisible();

    await page.goto(`/nodes/${ALPHA_KEY.slice(0, 8)}`);
    await expect(page).toHaveURL(new RegExp(`/nodes/${ALPHA_KEY}`));
  });

  test("unknown prefix shows the not-found state", async ({ page }) => {
    await page.goto("/nodes/zzzz");
    await expect(page.getByText("Node not found:")).toBeVisible();
    await expect(page.getByTestId("adopt-button")).toHaveCount(0);
  });
});

test.describe.serial("node tags (admin)", () => {
  test.use({ storageState: ADMIN_STATE });

  test("tags can be added, validated, edited and deleted", async ({ page }) => {
    await page.goto(`/nodes/${DELTA_KEY}`);

    // Add a tag.
    await page.getByTestId("tag-key").fill("description");
    await page.getByTestId("tag-value").fill("E2E marker");
    await page.getByTestId("tag-add").click();
    const row = page.locator('[data-testid="tag-row"][data-tag-key="description"]');
    await expect(row).toBeVisible();
    await expect(row).toContainText("E2E marker");

    // Invalid number values are rejected client-side.
    await page.getByTestId("tag-key").fill("score");
    await page.getByTestId("tag-type").selectOption("number");
    await page.getByTestId("tag-value").fill("not-a-number");
    await page.getByTestId("tag-add").click();
    await expect(page.getByText("Value must be a valid number")).toBeVisible();
    await expect(
      page.locator('[data-testid="tag-row"][data-tag-key="score"]'),
    ).toHaveCount(0);

    // Edit the tag value.
    await row.getByTestId("tag-edit").click();
    const modal = page.getByTestId("tag-edit-modal");
    await expect(modal).toBeVisible();
    await expect(page.getByTestId("tag-edit-value")).toHaveValue("E2E marker");
    await page.getByTestId("tag-edit-value").fill("E2E updated");
    await page.getByTestId("tag-edit-save").click();
    await expect(modal).toHaveCount(0);
    await expect(row).toContainText("E2E updated");

    // Cancelling the edit modal leaves the tag unchanged.
    await row.getByTestId("tag-edit").click();
    await expect(modal).toBeVisible();
    await page.getByTestId("tag-edit-cancel").click();
    await expect(modal).toHaveCount(0);
    await expect(row).toContainText("E2E updated");

    // Cancelling the delete confirm keeps the tag.
    await row.getByTestId("tag-delete").click();
    const confirm = page.locator("dialog.modal-open");
    await expect(
      confirm.getByRole("heading", { name: "Delete Tag" }),
    ).toBeVisible();
    await confirm.getByRole("button", { name: "Cancel" }).click();
    await expect(confirm).toHaveCount(0);
    await expect(row).toBeVisible();

    // Confirming the delete removes the tag.
    await row.getByTestId("tag-delete").click();
    await confirm.getByRole("button", { name: "Delete" }).click();
    await expect(confirm).toHaveCount(0);
    await expect(row).toHaveCount(0);
  });
});

test.describe.serial("adoption (admin)", () => {
  test.use({ storageState: ADMIN_STATE });

  test("adopt shows ownership and release restores the unadopted state", async ({
    page,
  }) => {
    await page.goto(`/nodes/${DELTA_KEY}`);

    const adoption = page.getByTestId("adoption-card");
    await expect(adoption).toBeVisible();
    await expect(adoption.getByText("not been adopted")).toBeVisible();
    await expect(page.getByTestId("adopt-button")).toBeVisible();

    await page.getByTestId("adopt-button").click();
    await expect(page).toHaveURL(/message=.*adopted/);
    await expect(page.getByTestId("adoption-owner")).toHaveText("PW Admin");
    await expect(page.getByTestId("release-button")).toBeVisible();

    // The owner name links to the adopting profile.
    await expect(page.getByTestId("adoption-owner")).toHaveAttribute(
      "href",
      /^\/profile\//,
    );

    // Cancelling the release confirm keeps the adoption.
    await page.getByTestId("release-button").click();
    const confirm = page.locator("dialog.modal-open");
    await expect(
      confirm.getByRole("heading", { name: "Release" }),
    ).toBeVisible();
    await confirm.getByRole("button", { name: "Cancel" }).click();
    await expect(confirm).toHaveCount(0);
    await expect(page.getByTestId("adoption-owner")).toBeVisible();

    // Confirming the release returns the node to the unadopted state.
    await page.getByTestId("release-button").click();
    await confirm.getByRole("button", { name: "Release" }).click();
    await expect(page).toHaveURL(/message=.*released/);
    await expect(page.getByTestId("adopt-button")).toBeVisible();
    await expect(page.getByTestId("adoption-owner")).toHaveCount(0);
  });
});

test.describe("node detail (member is read-only)", () => {
  test.use({ storageState: MEMBER_STATE });

  test("members cannot edit tags or adopt nodes", async ({ page }) => {
    await page.goto(`/nodes/${DELTA_KEY}`);

    await expect(page.getByTestId("tag-form")).toHaveCount(0);
    await expect(page.getByTestId("tag-edit")).toHaveCount(0);
    await expect(page.getByTestId("tag-delete")).toHaveCount(0);
    await expect(page.getByTestId("adopt-button")).toHaveCount(0);
    // Read-only tags (the seeded name tag) still render.
    await expect(
      page.locator("td.font-mono", { hasText: "name" }).first(),
    ).toBeVisible();
  });

  test("members see the owner of an adopted node without release rights", async ({
    page,
  }) => {
    await page.goto(`/nodes/${BRAVO_KEY}`);

    const adoption = page.getByTestId("adoption-card");
    await expect(adoption).toBeVisible();
    await expect(page.getByTestId("adoption-owner")).toHaveText("Mem South");
    await expect(page.getByTestId("release-button")).toHaveCount(0);
  });
});

test.describe.serial("adoption grants tag editing (operator)", () => {
  test.use({ storageState: OPERATOR_STATE });

  test("operators can edit tags only on nodes they adopt", async ({ page }) => {
    await page.goto(`/nodes/${CHARLIE_KEY}`);

    // Before adoption the operator is read-only.
    await expect(page.getByTestId("tag-form")).toHaveCount(0);
    await expect(page.getByTestId("adopt-button")).toBeVisible();

    await page.getByTestId("adopt-button").click();
    await expect(page.getByTestId("adoption-owner")).toHaveText("PW Operator");
    await expect(page.getByTestId("tag-form")).toBeVisible();

    // Tags added while adopted can be cleaned up again.
    await page.getByTestId("tag-key").fill("opnote");
    await page.getByTestId("tag-value").fill("checked by operator");
    await page.getByTestId("tag-add").click();
    const row = page.locator('[data-testid="tag-row"][data-tag-key="opnote"]');
    await expect(row).toBeVisible();

    await row.getByTestId("tag-delete").click();
    const confirm = page.locator("dialog.modal-open");
    await confirm.getByRole("button", { name: "Delete" }).click();
    await expect(row).toHaveCount(0);

    // Releasing the node removes the editing capability again.
    await page.getByTestId("release-button").click();
    await confirm.getByRole("button", { name: "Release" }).click();
    await expect(page.getByTestId("adopt-button")).toBeVisible();
    await expect(page.getByTestId("tag-form")).toHaveCount(0);
  });
});
