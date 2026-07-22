import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Channels } from "@/pages/Channels";
import { renderWithProviders } from "@/test/renderWithProviders";
import { makeConfig } from "@/test/makeConfig";
import * as api from "@/utils/api";

const CHANNELS = {
  items: [
    {
      id: "1",
      name: "Public",
      channel_hash: "11",
      visibility: "community",
      enabled: true,
      masked_key: "***",
      key_hex: null,
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-01T00:00:00Z",
    },
    {
      id: "2",
      name: "Ops",
      channel_hash: "22",
      visibility: "operator",
      enabled: true,
      masked_key: "***",
      key_hex: null,
      created_at: "2024-01-01T00:00:00Z",
      updated_at: "2024-01-01T00:00:00Z",
    },
  ],
  total: 2,
};

function mockChannelsApi() {
  vi.spyOn(api, "apiGet").mockResolvedValue(CHANNELS);
}

describe("Channels", () => {
  it("shows a loading spinner before data resolves", () => {
    vi.spyOn(api, "apiGet").mockReturnValue(new Promise(() => {}));
    renderWithProviders(<Channels />);
    expect(document.querySelector(".loading-spinner")).not.toBeNull();
  });

  it("renders channel cards after data resolves", async () => {
    mockChannelsApi();
    renderWithProviders(<Channels />);
    await waitFor(() => {
      expect(screen.getByText("Public")).toBeInTheDocument();
      expect(screen.getByText("Ops")).toBeInTheDocument();
    });
  });

  it("shows an error alert on fetch failure", async () => {
    vi.spyOn(api, "apiGet").mockRejectedValue(new Error("channels down"));
    renderWithProviders(<Channels />);
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("channels down");
    });
  });

  it("renders an empty state when no channels exist", async () => {
    vi.spyOn(api, "apiGet").mockResolvedValue({ items: [], total: 0 });
    renderWithProviders(<Channels />);
    await waitFor(() => {
      expect(screen.queryByText("Public")).not.toBeInTheDocument();
    });
  });
});
