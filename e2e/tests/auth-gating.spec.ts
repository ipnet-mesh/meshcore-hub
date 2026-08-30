import { expect, test } from "@playwright/test";
import { MEMBER_STATE } from "../utils/helpers";

test.describe("anonymous gating", () => {
  test("home shows a login button and no user menu", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("link", { name: "Login", exact: true })).toBeVisible();
    await expect(page.getByTestId("user-menu")).toHaveCount(0);
  });

  test("routes page hides every mutation affordance", async ({ page }) => {
    await page.goto("/routes");

    await expect(page.getByTestId("route-card").first()).toBeVisible();
    await expect(page.getByTestId("add-route")).toHaveCount(0);
    await expect(page.getByTestId("edit-route")).toHaveCount(0);
    await expect(page.getByTestId("delete-route")).toHaveCount(0);
  });

  test("channels page hides admin buttons and restricted channels", async ({
    page,
  }) => {
    await page.goto("/channels");

    // Anonymous visitors only see community channels.
    await expect(page.getByTestId("channel-card")).toHaveCount(3);
    await expect(
      page.locator('[data-testid="channel-card"][data-channel-name="E2E General"]'),
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="channel-card"][data-channel-name="E2E Staff"]'),
    ).toHaveCount(0);
    await expect(page.getByTestId("add-channel")).toHaveCount(0);
    await expect(page.getByTestId("channel-edit")).toHaveCount(0);
    await expect(page.getByTestId("channel-delete")).toHaveCount(0);
  });
});

test.describe("member gating", () => {
  test.use({ storageState: MEMBER_STATE });

  test("members get no route mutation buttons", async ({ page }) => {
    await page.goto("/routes");

    await expect(page.getByTestId("route-card").first()).toBeVisible();
    await expect(page.getByTestId("add-route")).toHaveCount(0);
    await expect(page.getByTestId("edit-route")).toHaveCount(0);
    await expect(page.getByTestId("delete-route")).toHaveCount(0);
    await expect(page.getByTestId("routes-mine-toggle")).toHaveCount(0);
  });

  test("members see community and member channels without admin buttons", async ({
    page,
  }) => {
    await page.goto("/channels");

    await expect(page.getByTestId("channel-card")).toHaveCount(4);
    await expect(
      page.locator('[data-testid="channel-card"][data-channel-name="E2E Members"]'),
    ).toBeVisible();
    await expect(
      page.locator('[data-testid="channel-card"][data-channel-name="E2E Crew"]'),
    ).toHaveCount(0);
    await expect(
      page.locator('[data-testid="channel-card"][data-channel-name="E2E Staff"]'),
    ).toHaveCount(0);
    await expect(page.getByTestId("add-channel")).toHaveCount(0);
    await expect(page.getByTestId("channel-edit")).toHaveCount(0);
    await expect(page.getByTestId("channel-delete")).toHaveCount(0);
  });
});
