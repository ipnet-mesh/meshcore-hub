import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CallsignBadge, CountBadge, RoleBadge } from "@/components/Badges";

describe("badge recipes", () => {
  it("CountBadge renders a large badge", () => {
    render(<CountBadge>42 things</CountBadge>);
    const el = screen.getByText("42 things");
    expect(el).toHaveClass("badge");
    expect(el).toHaveClass("badge-lg");
  });

  it("RoleBadge renders a primary small badge", () => {
    render(<RoleBadge role="operator" />);
    const el = screen.getByText("operator");
    expect(el).toHaveClass("badge-primary");
    expect(el).toHaveClass("badge-sm");
  });

  it("CallsignBadge renders a neutral small badge", () => {
    render(<CallsignBadge callsign="AB1CDE" />);
    const el = screen.getByText("AB1CDE");
    expect(el).toHaveClass("badge-neutral");
    expect(el).toHaveClass("badge-sm");
  });
});
