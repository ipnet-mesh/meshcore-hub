import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { SortableTableHeader, MobileSortSelect } from "@/components/SortableTable";

function renderWithRouter(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

function renderInTable(ui: React.ReactElement) {
  return renderWithRouter(
    <table>
      <thead>
        <tr>{ui}</tr>
      </thead>
    </table>,
  );
}

describe("SortableTableHeader", () => {
  it("links to asc when the column is not currently sorted", () => {
    const { container } = renderInTable(
      <SortableTableHeader
        label="Name"
        sortKey="name"
        currentSort="date"
        currentOrder="desc"
        basePath="/nodes"
      />,
    );
    const href = container.querySelector("a")?.getAttribute("href") ?? "";
    expect(href).toContain("sort=name");
    expect(href).toContain("order=asc");
  });

  it("flips asc to desc with the up indicator", () => {
    const { container } = renderInTable(
      <SortableTableHeader
        label="Name"
        sortKey="name"
        currentSort="name"
        currentOrder="asc"
        basePath="/nodes"
      />,
    );
    const link = container.querySelector("a");
    expect(link?.getAttribute("href")).toContain("order=desc");
    expect(link?.textContent).toContain("▴");
  });

  it("flips desc back to asc with the down indicator", () => {
    const { container } = renderInTable(
      <SortableTableHeader
        label="Name"
        sortKey="name"
        currentSort="name"
        currentOrder="desc"
        basePath="/nodes"
      />,
    );
    const link = container.querySelector("a");
    expect(link?.getAttribute("href")).toContain("order=asc");
    expect(link?.textContent).toContain("▾");
  });

  it("preserves existing params in the generated sort URL", () => {
    const { container } = renderInTable(
      <SortableTableHeader
        label="Name"
        sortKey="name"
        currentSort="date"
        currentOrder="asc"
        basePath="/nodes"
        params={{ search: "foo", tag: ["a", "b"] }}
      />,
    );
    const href = container.querySelector("a")?.getAttribute("href") ?? "";
    expect(href).toContain("search=foo");
    expect(href).toContain("tag=a");
    expect(href).toContain("tag=b");
  });

  it("stops propagation on header link click", () => {
    const parentClick = vi.fn();
    const { container } = render(
      <MemoryRouter>
        <table>
          <thead>
            <tr onClick={parentClick}>
              <SortableTableHeader
                label="X"
                sortKey="x"
                currentSort=""
                currentOrder=""
                basePath="/"
              />
            </tr>
          </thead>
        </table>
      </MemoryRouter>,
    );
    fireEvent.click(container.querySelector("a")!);
    expect(parentClick).not.toHaveBeenCalled();
  });
});

describe("MobileSortSelect", () => {
  it("renders options with the current value selected", () => {
    render(
      <MemoryRouter>
        <MobileSortSelect
          currentSort="name"
          currentOrder="asc"
          basePath="/nodes"
          options={[
            { value: "name:asc", label: "Name asc" },
            { value: "name:desc", label: "Name desc" },
          ]}
        />
      </MemoryRouter>,
    );
    expect(screen.getByRole("combobox")).toHaveValue("name:asc");
    expect(screen.getByText("Name desc")).toBeInTheDocument();
  });
});
