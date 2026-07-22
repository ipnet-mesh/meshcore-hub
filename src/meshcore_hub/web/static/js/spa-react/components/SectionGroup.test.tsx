import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SectionGroup } from "@/components/SectionGroup";

describe("SectionGroup", () => {
  it("renders the title heading and children in the default grid", () => {
    const { container } = render(
      <SectionGroup title="Community">
        <span>card</span>
      </SectionGroup>,
    );
    expect(
      screen.getByRole("heading", { name: "Community" }),
    ).toBeInTheDocument();
    expect(screen.getByText("card")).toBeInTheDocument();
    expect(container.querySelector("div")).toHaveClass("lg:grid-cols-3");
  });

  it("allows a custom grid className", () => {
    const { container } = render(
      <SectionGroup title="t" className="grid grid-cols-2">
        <span>c</span>
      </SectionGroup>,
    );
    expect(container.querySelector(".grid-cols-2")).not.toBeNull();
    expect(container.querySelector(".lg\\:grid-cols-3")).toBeNull();
  });
});
