import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Messages } from "@/pages/Messages";
import { renderWithProviders } from "@/test/renderWithProviders";
import * as api from "@/utils/api";

const MESSAGES = {
  items: [
    {
      message_type: "channel",
      text: "Hello world",
      channel_idx: 17,
      received_at: "2024-01-01T00:00:00Z",
      signature: null,
    },
  ],
  total: 1,
};

function mockMessagesApi() {
  vi.spyOn(api, "apiGet").mockImplementation(async (path) => {
    if (path.includes("/api/v1/messages")) return MESSAGES;
    if (path.includes("/api/v1/nodes")) return { items: [], total: 0 };
    if (path.includes("/api/v1/channels")) return { items: [] };
    throw new Error(`Unexpected: ${path}`);
  });
}

describe("Messages", () => {
  it("shows a loading spinner before data resolves", () => {
    vi.spyOn(api, "apiGet").mockReturnValue(new Promise(() => {}));
    renderWithProviders(<Messages />);
    expect(document.querySelector(".loading-spinner")).not.toBeNull();
  });

  it("renders messages after data resolves", async () => {
    mockMessagesApi();
    renderWithProviders(<Messages />);
    await waitFor(() => {
      expect(screen.getAllByText("Hello world").length).toBeGreaterThanOrEqual(1);
    });
  });

  it("shows an error alert on fetch failure", async () => {
    vi.spyOn(api, "apiGet").mockRejectedValue(new Error("disconnected"));
    const { container } = renderWithProviders(<Messages />);
    await waitFor(() => {
      expect(container.querySelector('[data-tip="disconnected"]')).not.toBeNull();
    });
  });

  it("renders an empty state when no messages exist", async () => {
    vi.spyOn(api, "apiGet").mockImplementation(async (path) => {
      if (path.includes("/api/v1/messages")) return { items: [], total: 0 };
      if (path.includes("/api/v1/nodes")) return { items: [], total: 0 };
      if (path.includes("/api/v1/channels")) return { items: [] };
      throw new Error(`Unexpected: ${path}`);
    });
    renderWithProviders(<Messages />);
    await waitFor(() => {
      expect(screen.queryByText("Hello world")).not.toBeInTheDocument();
    });
  });
});
