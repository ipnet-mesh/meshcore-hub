import { expect, test, type Page } from "@playwright/test";
import { ADMIN_STATE } from "../utils/helpers";

test.use({ storageState: ADMIN_STATE });

const CREATED_NAME = "E2E Created";
const CREATED_KEY = "cafebabecafebabecafebabecafebabecafebabecafebabecafebabecafebabe";

function card(page: Page, name: string) {
  return page.locator(
    `[data-testid="channel-card"][data-channel-name="${name}"]`,
  );
}

test.describe.serial("channels (admin)", () => {
  test("seeded channels render grouped by visibility with QR codes", async ({
    page,
  }) => {
    await page.goto("/channels");

    await expect(page.getByTestId("channel-card")).toHaveCount(6);
    await expect(page.getByTestId("add-channel")).toBeVisible();

    for (const name of ["E2E General", "E2E Ops", "E2E Retired"]) {
      await expect(card(page, name)).toBeVisible();
    }
    // Sections: community holds the two enabled channels plus the retired one.
    await expect(
      page.getByRole("heading", { name: "Community", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Member", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Operator", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Admin", exact: true }),
    ).toBeVisible();

    // Every seeded channel exposes its full key and a QR code to admins.
    await expect(card(page, "E2E General").locator('[data-testid="channel-qr"] svg')).toBeVisible();

    // Disabled channels are badged.
    await expect(card(page, "E2E Retired").getByText("Disabled")).toBeVisible();

    // Admin controls exist on every card.
    await expect(page.getByTestId("channel-edit")).toHaveCount(6);
    await expect(page.getByTestId("channel-delete")).toHaveCount(6);
  });

  test("adding a channel creates a card with a QR code", async ({ page }) => {
    await page.goto("/channels");

    await page.getByTestId("add-channel").click();
    const modal = page.locator("dialog.modal-open");
    await expect(modal).toBeVisible();
    await expect(modal.locator("h3")).toHaveText("Add Channel");

    await page.getByTestId("channel-name").fill(CREATED_NAME);
    await page.getByTestId("channel-key").fill(CREATED_KEY);
    await page.getByTestId("channel-visibility").selectOption("member");
    await page.getByTestId("channel-save").click();

    await expect(modal).toHaveCount(0);
    const created = card(page, CREATED_NAME);
    await expect(created).toBeVisible();
    await expect(created.locator('[data-testid="channel-qr"] svg')).toBeVisible();
    await expect(created).toContainText(CREATED_KEY);

    // Cancelling the delete confirm keeps the channel.
    await created.getByTestId("channel-delete").click();
    const confirm = page.locator("dialog.modal-open");
    await expect(
      confirm.getByRole("heading", { name: "Delete Channel" }),
    ).toBeVisible();
    await confirm.getByRole("button", { name: "Cancel" }).click();
    await expect(confirm).toHaveCount(0);
    await expect(created).toBeVisible();
  });

  test("editing a channel moves it between visibility sections", async ({
    page,
  }) => {
    await page.goto("/channels");

    const created = card(page, CREATED_NAME);
    await created.getByTestId("channel-edit").click();

    const modal = page.locator("dialog.modal-open");
    await expect(modal.locator("h3")).toHaveText("Edit Channel");
    // The name is locked and the key is not re-entered on edit.
    await expect(page.getByTestId("channel-name")).toBeDisabled();
    await expect(page.getByTestId("channel-name")).toHaveValue(CREATED_NAME);
    await expect(page.getByTestId("channel-key")).toHaveCount(0);

    await page.getByTestId("channel-visibility").selectOption("operator");
    await page.getByTestId("channel-enabled").uncheck();
    await page.getByTestId("channel-save").click();

    await expect(modal).toHaveCount(0);
    await expect(created).toBeVisible();
    await expect(created.getByText("Disabled")).toBeVisible();
    // It now sits under the Operator section.
    const operatorSection = page.locator("h2", { hasText: "Operator" }).locator("..");
    await expect(operatorSection.getByTestId("channel-card")).toHaveCount(2);
  });

  test("deleting a channel confirms and removes the card", async ({ page }) => {
    await page.goto("/channels");

    const created = card(page, CREATED_NAME);
    await created.getByTestId("channel-delete").click();

    const confirm = page.locator("dialog.modal-open");
    await expect(
      confirm.getByRole("heading", { name: "Delete Channel" }),
    ).toBeVisible();
    await expect(
      confirm.getByText(`Are you sure you want to delete channel ${CREATED_NAME}?`),
    ).toBeVisible();

    await confirm.getByRole("button", { name: "Delete" }).click();
    await expect(confirm).toHaveCount(0);
    await expect(created).toHaveCount(0);
    await expect(page.getByTestId("channel-card")).toHaveCount(5);
  });

  test("card click and Enter key navigate to the channel messages", async ({
    page,
  }) => {
    await page.goto("/channels");

    await card(page, "E2E General").click();
    await expect(page).toHaveURL(/\/messages\?channel_idx=\d+/);

    await page.goto("/channels");
    const cardEl = card(page, "E2E Ops");
    await cardEl.focus();
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/messages\?channel_idx=\d+/);
  });
});
