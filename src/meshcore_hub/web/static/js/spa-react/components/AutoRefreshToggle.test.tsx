import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AutoRefreshToggle } from "@/components/AutoRefreshToggle";

describe("AutoRefreshToggle", () => {
  it("renders nothing when the interval is 0", () => {
    const { container } = render(
      <AutoRefreshToggle
        paused={false}
        onToggle={() => {}}
        intervalSeconds={0}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows the interval and a checked toggle while running", () => {
    const onToggle = vi.fn();
    render(
      <AutoRefreshToggle
        paused={false}
        onToggle={onToggle}
        intervalSeconds={30}
      />,
    );
    expect(screen.getByText("30s")).toBeInTheDocument();
    const checkbox = screen.getByRole("checkbox");
    expect(checkbox).toBeChecked();
    fireEvent.click(checkbox);
    expect(onToggle).toHaveBeenCalledOnce();
  });

  it("shows an unchecked toggle while paused", () => {
    render(
      <AutoRefreshToggle paused onToggle={() => {}} intervalSeconds={30} />,
    );
    expect(screen.getByRole("checkbox")).not.toBeChecked();
  });
});
