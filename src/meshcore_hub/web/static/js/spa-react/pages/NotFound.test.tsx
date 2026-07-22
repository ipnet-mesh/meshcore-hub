import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "@/test/renderWithProviders";
import { NotFound } from "@/pages/NotFound";

describe("NotFound", () => {
  it("renders the 404 hero", () => {
    renderWithProviders(<NotFound />);
    expect(screen.getByText("404")).toBeInTheDocument();
    expect(screen.getByText("common.page_not_found")).toBeInTheDocument();
  });

  it("has links to home and nodes", () => {
    renderWithProviders(<NotFound />);
    const homeLink = screen.getByText("common.go_home").closest("a");
    expect(homeLink).toHaveAttribute("href", "/");
    const nodesLink = screen
      .getByText(/common.view_entity/)
      .closest("a");
    expect(nodesLink).toHaveAttribute("href", "/nodes");
  });
});
