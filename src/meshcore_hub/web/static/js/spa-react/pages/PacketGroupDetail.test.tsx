import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PacketGroupDetail } from "@/pages/PacketGroupDetail";
import { renderWithProviders } from "@/test/renderWithProviders";
import * as api from "@/utils/api";

const GROUP = {
  packet_hash: "grouphash",
  event_type: "advert",
  channel_idx: 17,
  first_seen: "2024-01-01T00:00:00Z",
  redacted: false,
  raw_hex: "deadbeef",
  decoded: { type: "test" },
  receptions: [
    {
      packet_id: "p1",
      observed_by: "obs1",
      observer_name: "Observer1",
      snr: -5.0,
      observed_at: "2024-01-01T00:00:00Z",
      path: ["a", "b"],
    },
  ],
};

function mockGroupApi() {
  vi.spyOn(api, "apiGet").mockImplementation(async (path) => {
    if (path.includes("/api/v1/packet-groups/")) return GROUP;
    if (path.includes("/api/v1/channels")) return { items: [] };
    if (path.includes("/api/v1/nodes")) return { items: [], total: 0 };
    throw new Error(`Unexpected: ${path}`);
  });
}

describe("PacketGroupDetail", () => {
  it("shows a loading state before data resolves", () => {
    vi.spyOn(api, "apiGet").mockReturnValue(new Promise(() => {}));
    renderWithProviders(<PacketGroupDetail />, {
      route: "/packets/hash/abc",
      routePath: "/packets/hash/:hash",
    });
    expect(document.querySelector(".loading-spinner")).not.toBeNull();
  });

  it("renders group detail after data resolves", async () => {
    mockGroupApi();
    renderWithProviders(<PacketGroupDetail />, {
      route: "/packets/hash/abc",
      routePath: "/packets/hash/:hash",
    });
    await waitFor(() => {
      expect(screen.getAllByText("grouphash").length).toBeGreaterThanOrEqual(1);
    });
    expect(
      screen.getByRole("heading", { name: "grouphash" }).querySelector("svg"),
    ).not.toBeNull();
  });

  it("shows an error on fetch failure", async () => {
    vi.spyOn(api, "apiGet").mockImplementation(async (path) => {
      if (path.includes("/api/v1/channels")) return { items: [] };
      throw new Error("group fetch failed");
    });
    const { container } = renderWithProviders(<PacketGroupDetail />, {
      route: "/packets/hash/abc",
      routePath: "/packets/hash/:hash",
    });
    await waitFor(() => {
      expect(
        container.querySelector('[data-tip="group fetch failed"]'),
      ).not.toBeNull();
    });
  });
});
