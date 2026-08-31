import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Messages } from "@/pages/Messages";
import { renderWithProviders } from "@/test/renderWithProviders";
import { makeConfig } from "@/test/makeConfig";
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

const CHANNELS = {
  items: [
    { channel_hash: "05", name: "CommunityChan", visibility: "community", enabled: true },
    { channel_hash: "06", name: "DisabledChan", visibility: "community", enabled: false },
    { channel_hash: "07", name: "MemberChan", visibility: "member", enabled: true },
  ],
};

function mockMessagesApiWithChannels() {
  vi.spyOn(api, "apiGet").mockImplementation(async (path) => {
    if (path.includes("/api/v1/messages")) return MESSAGES;
    if (path.includes("/api/v1/nodes")) return { items: [], total: 0 };
    if (path.includes("/api/v1/channels")) return CHANNELS;
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
    expect(
      screen.getByRole("heading", { name: "entities.messages" }).querySelector("svg"),
    ).not.toBeNull();
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

  it("defaults the feed link to the public channel", async () => {
    mockMessagesApi();
    renderWithProviders(<Messages />);
    await waitFor(() => {
      expect(screen.getByTestId("feed-link")).toHaveAttribute(
        "href",
        "/feeds/channels/17.xml",
      );
    });
  });

  it("points the feed link at the selected feedable channel", async () => {
    mockMessagesApiWithChannels();
    renderWithProviders(<Messages />, { route: "/messages?channel_idx=5" });
    await waitFor(() => {
      expect(screen.getByTestId("feed-link")).toHaveAttribute(
        "href",
        "/feeds/channels/5.xml",
      );
    });
  });

  it("hides the feed link when a disabled channel is selected", async () => {
    mockMessagesApiWithChannels();
    renderWithProviders(<Messages />, { route: "/messages?channel_idx=6" });
    await waitFor(() => {
      expect(screen.getAllByText("Hello world").length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.queryByTestId("feed-link")).not.toBeInTheDocument();
  });

  it("hides the feed link when a member channel is selected", async () => {
    mockMessagesApiWithChannels();
    renderWithProviders(<Messages />, { route: "/messages?channel_idx=7" });
    await waitFor(() => {
      expect(screen.getAllByText("Hello world").length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.queryByTestId("feed-link")).not.toBeInTheDocument();
  });

  it("hides the feed link when feeds are disabled", async () => {
    mockMessagesApi();
    renderWithProviders(<Messages />, {
      config: makeConfig({ features: { feeds: false } }),
    });
    await waitFor(() => {
      expect(screen.getAllByText("Hello world").length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.queryByTestId("feed-link")).not.toBeInTheDocument();
  });
});
