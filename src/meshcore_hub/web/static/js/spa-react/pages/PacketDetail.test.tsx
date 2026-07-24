import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PacketDetail } from "@/pages/PacketDetail";
import { renderWithProviders } from "@/test/renderWithProviders";
import * as api from "@/utils/api";

const PACKET = {
  packet_hash: "abc123",
  event_type: "advert",
  channel_idx: 17,
  observed_by: "nodekey1",
  observer_name: "Observer1",
  observer_tag_name: null,
  source_pubkey_prefix: "deadbeef",
  packet_type: 1,
  payload_type: 2,
  route_type: "direct",
  snr: -5.5,
  path_len: 3,
  received_at: "2024-01-01T00:00:00Z",
  redacted: false,
  raw_hex: "deadbeef",
  decoded: { foo: "bar" },
};

function mockPacketApi(packet?: unknown, error?: Error) {
  vi.spyOn(api, "apiGet").mockImplementation(async (path) => {
    if (path.includes("/api/v1/channels")) return { items: [] };
    if (error) throw error;
    return packet ?? PACKET;
  });
}

function renderPage() {
  return renderWithProviders(<PacketDetail />, {
    route: "/packets/test-id",
    routePath: "/packets/:id",
  });
}

describe("PacketDetail", () => {
  it("shows a loading spinner before data resolves", () => {
    vi.spyOn(api, "apiGet").mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(document.querySelector(".loading-spinner")).not.toBeNull();
  });

  it("renders packet fields after data resolves", async () => {
    mockPacketApi();
    renderPage();
    await waitFor(() => {
      expect(screen.getAllByText("abc123").length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.getByText("Observer1")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "abc123" }).querySelector("svg"),
    ).not.toBeNull();
  });

  it("shows not-found state on a 404 error", async () => {
    const err = new Error("API error: 404 Not Found");
    mockPacketApi(undefined, err);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/entity_not_found/)).toBeInTheDocument();
    });
  });

  it("shows a warning badge on non-404 errors", async () => {
    mockPacketApi(undefined, new Error("boom"));
    const { container } = renderPage();
    await waitFor(() => {
      expect(container.querySelector('[data-tip="boom"]')).not.toBeNull();
    });
  });
});
