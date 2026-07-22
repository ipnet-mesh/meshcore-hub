import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DefinitionField, DefinitionGrid } from "@/components/Definition";

describe("DefinitionField", () => {
  it("renders the label above the value", () => {
    render(<DefinitionField label="Channel">5 (chan)</DefinitionField>);
    expect(screen.getByText("Channel")).toBeInTheDocument();
    expect(screen.getByText("5 (chan)")).toBeInTheDocument();
  });
});

describe("DefinitionGrid", () => {
  it("uses the default two-column grid classes", () => {
    const { container } = render(
      <DefinitionGrid>
        <span>x</span>
      </DefinitionGrid>,
    );
    expect(container.firstChild).toHaveClass("grid");
    expect(container.firstChild).toHaveClass("md:grid-cols-2");
  });

  it("allows a custom className override", () => {
    const { container } = render(
      <DefinitionGrid className="grid grid-cols-3">
        <span>x</span>
      </DefinitionGrid>,
    );
    expect(container.firstChild).toHaveClass("grid-cols-3");
    expect(container.firstChild).not.toHaveClass("md:grid-cols-2");
  });
});
