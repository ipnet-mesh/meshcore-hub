import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/charts/Charts", () => ({
  ActivityChart: () => null,
  TrendLineChart: () => null,
  StackedBarChart: () => null,
  RoutesTrendChart: () => null,
  RouteDetailStrip: () => null,
}));

import { HomePage as Home } from "@/pages/Home";
import { renderWithProviders } from "@/test/renderWithProviders";
import { makeConfig } from "@/test/makeConfig";
import * as api from "@/utils/api";

const STATS = {
  node_count: 42,
  message_count: 100,
  packet_count: 500,
  channel_count: 3,
  observer_count: 5,
  route_count: 2,
};

function mockHomeApi() {
  vi.spyOn(api, "apiGet").mockImplementation(async (path) => {
    if (path.includes("/dashboard/stats")) return STATS;
    if (path.includes("/dashboard/activity")) return { data: [] };
    if (path.includes("/dashboard/message-activity")) return { data: [] };
    throw new Error(`Unexpected: ${path}`);
  });
}

describe("Home", () => {
  it("shows a loading state before data resolves", () => {
    vi.spyOn(api, "apiGet").mockReturnValue(new Promise(() => {}));
    renderWithProviders(<Home />);
    expect(document.querySelector(".loading-spinner")).not.toBeNull();
  });

  it("renders stat cards after data resolves", async () => {
    mockHomeApi();
    renderWithProviders(<Home />);
    await waitFor(() => {
      expect(document.querySelector(".loading-spinner")).toBeNull();
    });
  });

  it("renders without error when all features are disabled", async () => {
    mockHomeApi();
    renderWithProviders(<Home />, {
      config: makeConfig({ features: { dashboard: false, nodes: false, map: false } }),
    });
    await waitFor(() => {
      expect(document.querySelector(".loading-spinner")).not.toBeNull();
    });
  });
});
