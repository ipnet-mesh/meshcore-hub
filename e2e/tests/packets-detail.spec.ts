import { expect, test } from "@playwright/test";

test.describe("raw packet detail", () => {
  test("renders fields, raw hex and decoded payload", async ({ page }) => {
    const response = await page.request.get("/api/v1/packets?limit=1&order=desc");
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    const packet = body.items[0];
    expect(packet?.id).toBeTruthy();

    await page.goto(`/packets/${packet.id}`);

    await expect(page.locator('nav[aria-label="Breadcrumb"]')).toBeVisible();
    await expect(
      page.getByRole("heading", { name: packet.packet_hash as string }),
    ).toBeVisible();

    // Definition grid fields.
    await expect(page.getByText("Packet Hash", { exact: true })).toBeVisible();
    await expect(page.locator("code", { hasText: packet.packet_hash }).first()).toBeVisible();
    await expect(
      page.getByText(packet.event_type as string, { exact: true }).first(),
    ).toBeVisible();

    // Raw hex and decoded payload blocks.
    await expect(page.getByText("Raw", { exact: true })).toBeVisible();
    await expect(page.getByText("Decoded", { exact: true })).toBeVisible();
  });

  test("unknown packet id shows the not-found state", async ({ page }) => {
    await page.goto(
      "/packets/00000000-0000-4000-8000-000000000000",
    );
    await expect(page.getByText(/not found/i).first()).toBeVisible();
  });
});
