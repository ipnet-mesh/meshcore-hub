import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EmptyState, EmptyRow } from "@/components/EmptyState";

describe("EmptyState", () => {
  it("renders its children", () => {
    render(<EmptyState>No nodes found</EmptyState>);
    expect(screen.getByText("No nodes found")).toBeInTheDocument();
  });
});

describe("EmptyRow", () => {
  it("renders a table cell spanning the given columns", () => {
    const { container } = render(
      <table>
        <tbody>
          <EmptyRow colSpan={5}>Nothing here</EmptyRow>
        </tbody>
      </table>,
    );
    const td = container.querySelector("td");
    expect(td).not.toBeNull();
    expect(td!.getAttribute("colspan")).toBe("5");
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
  });
});
