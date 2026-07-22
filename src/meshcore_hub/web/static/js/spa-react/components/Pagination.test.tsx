import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { Pagination } from "@/components/Pagination";

function renderWithRouter(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe("Pagination", () => {
  it("renders nothing when totalPages <= 1", () => {
    const { container } = renderWithRouter(
      <Pagination page={1} totalPages={1} basePath="/nodes" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("disables previous on the first page and enables next", () => {
    renderWithRouter(<Pagination page={1} totalPages={3} basePath="/nodes" />);
    expect(screen.getByText("common.previous").closest("button")).toBeDisabled();
    expect(screen.getByText("common.next").closest("a")).not.toBeNull();
  });

  it("disables next on the last page", () => {
    renderWithRouter(<Pagination page={3} totalPages={3} basePath="/nodes" />);
    expect(screen.getByText("common.next").closest("button")).toBeDisabled();
    expect(screen.getByText("common.previous").closest("a")).not.toBeNull();
  });

  it("marks the current page button as active", () => {
    renderWithRouter(<Pagination page={2} totalPages={3} basePath="/nodes" />);
    expect(screen.getByText("2").closest("button")).toHaveClass("btn-active");
  });

  it("renders ellipsis for far-away pages", () => {
    renderWithRouter(<Pagination page={5} totalPages={20} basePath="/nodes" />);
    expect(screen.getAllByText("...").length).toBeGreaterThanOrEqual(1);
  });

  it("preserves extra params in page URLs", () => {
    renderWithRouter(
      <Pagination
        page={2}
        totalPages={5}
        basePath="/nodes"
        params={{ search: "foo", tag: ["a", "b"] }}
      />,
    );
    const nextHref = screen.getByText("common.next").closest("a")?.getAttribute("href");
    expect(nextHref).toContain("page=3");
    expect(nextHref).toContain("search=foo");
    expect(nextHref).toContain("tag=a");
    expect(nextHref).toContain("tag=b");
  });
});
