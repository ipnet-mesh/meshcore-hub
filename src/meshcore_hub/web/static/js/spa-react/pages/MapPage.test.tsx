import { screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

vi.mock("react-leaflet", () => ({
  MapContainer: ({ children }: { children: ReactNode }) => (
    <div data-testid="mock-map">{children}</div>
  ),
  TileLayer: () => null,
  Marker: () => null,
  Popup: () => null,
  useMap: () => ({ fitBounds: () => {}, latLngToContainerPoint: () => ({ x: 0, y: 0 }) }),
}));

vi.mock("leaflet", () => ({
  divIcon: () => ({}),
  latLngBounds: () => ({}),
  point: () => ({}),
}));

import { MapPage } from "@/pages/MapPage";
import { renderWithProviders } from "@/test/renderWithProviders";
import * as api from "@/utils/api";

const MAP_DATA = {
  nodes: [
    {
      public_key: "a".repeat(64),
      name: "MapNode",
      adv_type: "chat",
      lat: 40.7,
      lon: -74.0,
      last_seen: "2024-01-01T00:00:00Z",
      is_adopted: false,
      role: null,
      owner: null,
    },
  ],
  center: null,
  adopted_center: null,
  debug: { total_nodes: 1, nodes_with_coords: 1, error: null },
  profiles: [],
};

describe("MapPage", () => {
  it("shows a loading state before data resolves", () => {
    vi.spyOn(api, "apiGet").mockReturnValue(new Promise(() => {}));
    renderWithProviders(<MapPage />);
    expect(document.querySelector(".loading-spinner")).not.toBeNull();
  });

  it("renders the map after data resolves", async () => {
    vi.spyOn(api, "apiGet").mockResolvedValue(MAP_DATA);
    renderWithProviders(<MapPage />);
    await waitFor(() => {
      expect(screen.getByTestId("mock-map")).toBeInTheDocument();
    });
  });

  it("shows an error on fetch failure", async () => {
    vi.spyOn(api, "apiGet").mockRejectedValue(new Error("map error"));
    const { container } = renderWithProviders(<MapPage />);
    await waitFor(() => {
      expect(container.querySelector(".alert-error")).not.toBeNull();
    });
  });
});
