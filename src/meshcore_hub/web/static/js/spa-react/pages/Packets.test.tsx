import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Packets } from "@/pages/Packets";
import { renderWithProviders } from "@/test/renderWithProviders";
import * as api from "@/utils/api";

const GROUPS = {
  items: [
    {
      packet_hash: "hash1",
      event_type: "advert",
      channel_idx: 17,
      path_hash_bytes: null,
      reception_count: 3,
      observer_count: 2,
      first_seen: "2024-01-01T00:00:00Z",
      redacted: false,
      receptions: [{ packet_id: "p1" }],
    },
  ],
  total: 1,
};

function mockPacketsApi() {
  vi.spyOn(api, "apiGet").mockImplementation(async (path) => {
    if (path.includes("/api/v1/packet-groups")) return GROUPS;
    if (path.includes("/api/v1/channels")) return { items: [] };
    throw new Error(`Unexpected: ${path}`);
  });
}

describe("Packets", () => {
  it("shows a loading spinner before data resolves", () => {
    vi.spyOn(api, "apiGet").mockReturnValue(new Promise(() => {}));
    renderWithProviders(<Packets />);
    expect(document.querySelector(".loading-spinner")).not.toBeNull();
  });

  it("renders packet group rows after data resolves", async () => {
    mockPacketsApi();
    renderWithProviders(<Packets />);
    await waitFor(() => {
      expect(screen.getByText("hash1")).toBeInTheDocument();
    });
    expect(
      screen.getByRole("heading", { name: "entities.packets" }).querySelector("svg"),
    ).not.toBeNull();
  });

  it("shows an error alert on fetch failure", async () => {
    vi.spyOn(api, "apiGet").mockRejectedValue(new Error("network error"));
    const { container } = renderWithProviders(<Packets />);
    await waitFor(() => {
      expect(container.querySelector('[data-tip="network error"]')).not.toBeNull();
    });
  });

  it("renders an empty state when no packets exist", async () => {
    vi.spyOn(api, "apiGet").mockImplementation(async (path) => {
      if (path.includes("/api/v1/packet-groups")) return { items: [], total: 0 };
      if (path.includes("/api/v1/channels")) return { items: [] };
      throw new Error(`Unexpected: ${path}`);
    });
    renderWithProviders(<Packets />);
    await waitFor(() => {
      expect(screen.queryByText("hash1")).not.toBeInTheDocument();
    });
  });
});
