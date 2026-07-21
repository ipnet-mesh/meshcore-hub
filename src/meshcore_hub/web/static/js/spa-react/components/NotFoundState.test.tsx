import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NotFoundState } from "@/components/NotFoundState";

describe("NotFoundState", () => {
  it("renders an error alert with the message by default", () => {
    const { container } = render(<NotFoundState message="No such node" />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveClass("alert-error");
    expect(alert).toHaveTextContent("No such node");
    expect(container.querySelector("svg")).not.toBeNull();
  });

  it("renders a warning alert without an icon when tone is warning", () => {
    const { container } = render(
      <NotFoundState tone="warning" message="Gone after retention" />,
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveClass("alert-warning");
    expect(alert).toHaveTextContent("Gone after retention");
    expect(container.querySelector("svg")).toBeNull();
  });
});
