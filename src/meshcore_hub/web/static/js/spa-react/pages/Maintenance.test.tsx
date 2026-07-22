import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "@/test/renderWithProviders";
import { Maintenance } from "@/pages/Maintenance";

describe("Maintenance", () => {
  it("renders the maintenance hero with title and description", () => {
    renderWithProviders(<Maintenance />);
    expect(screen.getByText("🔧")).toBeInTheDocument();
    expect(screen.getByText("maintenance.title")).toBeInTheDocument();
    expect(screen.getByText("maintenance.description")).toBeInTheDocument();
  });
});
