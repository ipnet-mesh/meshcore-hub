import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Advertisements } from "@/pages/Advertisements";
import { renderWithProviders } from "@/test/renderWithProviders";
import * as api from "@/utils/api";

const ADVERTS = {
  items: [
    {
      public_key: "c".repeat(64),
      name: "AdNode",
      adv_type: "repeater",
      route_type: "flood",
      first_seen: "2024-01-01T00:00:00Z",
      last_seen: "2024-01-01T12:00:00Z",
    },
  ],
  total: 1,
};

function mockAdvertsApi() {
  vi.spyOn(api, "apiGet").mockImplementation(async (path) => {
    if (path.includes("/api/v1/advertisements")) return ADVERTS;
    if (path.includes("/api/v1/nodes")) return { items: [], total: 0 };
    throw new Error(`Unexpected: ${path}`);
  });
}

describe("Advertisements", () => {
  it("shows a loading spinner before data resolves", () => {
    vi.spyOn(api, "apiGet").mockReturnValue(new Promise(() => {}));
    renderWithProviders(<Advertisements />);
    expect(document.querySelector(".loading-spinner")).not.toBeNull();
  });

  it("renders advertisement rows after data resolves", async () => {
    mockAdvertsApi();
    renderWithProviders(<Advertisements />);
    await waitFor(() => {
      expect(screen.getAllByText("AdNode").length).toBeGreaterThanOrEqual(1);
    });
  });

  it("shows an error alert on fetch failure", async () => {
    vi.spyOn(api, "apiGet").mockRejectedValue(new Error("timeout"));
    const { container } = renderWithProviders(<Advertisements />);
    await waitFor(() => {
      expect(container.querySelector('[data-tip="timeout"]')).not.toBeNull();
    });
  });

  it("renders an empty state when no adverts exist", async () => {
    vi.spyOn(api, "apiGet").mockImplementation(async (path) => {
      if (path.includes("/api/v1/advertisements")) return { items: [], total: 0 };
      if (path.includes("/api/v1/nodes")) return { items: [], total: 0 };
      throw new Error(`Unexpected: ${path}`);
    });
    renderWithProviders(<Advertisements />);
    await waitFor(() => {
      expect(screen.queryByText("AdNode")).not.toBeInTheDocument();
    });
  });
});
