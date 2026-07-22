import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Nodes } from "@/pages/Nodes";
import { renderWithProviders } from "@/test/renderWithProviders";
import { makeConfig } from "@/test/makeConfig";
import * as api from "@/utils/api";

const KEY = "a".repeat(64);
const NODES = {
  items: [
    {
      public_key: KEY,
      name: "TestNode",
      adv_type: "chat",
      last_seen: "2024-01-01T00:00:00Z",
      tags: [],
    },
  ],
  total: 1,
  limit: 50,
  offset: 0,
};

function mockNodesApi() {
  vi.spyOn(api, "apiGet").mockImplementation(async (path) => {
    if (path.includes("/api/v1/nodes")) return NODES;
    if (path.includes("/api/v1/user/profiles")) return { items: [] };
    throw new Error(`Unexpected: ${path}`);
  });
}

describe("Nodes", () => {
  it("shows a loading spinner before data resolves", () => {
    vi.spyOn(api, "apiGet").mockReturnValue(new Promise(() => {}));
    renderWithProviders(<Nodes />);
    expect(document.querySelector(".loading-spinner")).not.toBeNull();
  });

  it("renders node rows after data resolves", async () => {
    mockNodesApi();
    renderWithProviders(<Nodes />);
    await waitFor(() => {
      expect(screen.getAllByText("TestNode").length).toBeGreaterThanOrEqual(1);
    });
  });

  it("shows an error alert on fetch failure", async () => {
    vi.spyOn(api, "apiGet").mockRejectedValue(new Error("server down"));
    const { container } = renderWithProviders(<Nodes />);
    await waitFor(() => {
      expect(container.querySelector('[data-tip="server down"]')).not.toBeNull();
    });
  });

  it("renders an empty state when no nodes exist", async () => {
    vi.spyOn(api, "apiGet").mockResolvedValue({
      items: [],
      total: 0,
      limit: 50,
      offset: 0,
    });
    renderWithProviders(<Nodes />);
    await waitFor(() => {
      expect(screen.queryByText("TestNode")).not.toBeInTheDocument();
    });
  });

  it("renders without error when OIDC is enabled", async () => {
    mockNodesApi();
    renderWithProviders(<Nodes />, {
      config: makeConfig({ oidc_enabled: true, user: { sub: "u1", name: "Admin" } }),
    });
    await waitFor(() => {
      expect(screen.getAllByText("TestNode").length).toBeGreaterThanOrEqual(1);
    });
  });
});
