import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ObserverIcons,
  ObserverFilterBadges,
  getDisabledObserverAreas,
  setDisabledObserverAreas,
  toggleObserverArea,
} from "@/components/ObserverBadges";

describe("ObserverIcons", () => {
  it("renders nothing when observers is empty", () => {
    const { container } = render(<ObserverIcons observers={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders the count and a tooltip with resolved names", () => {
    render(
      <ObserverIcons
        observers={[
          { tag_name: "Alpha", public_key: "aaa" },
          { name: "Beta", public_key: "bbb" },
        ]}
      />,
    );
    const badge = screen.getByText("2");
    expect(badge.closest("[title]")).toHaveAttribute("title", "Alpha, Beta");
  });
});

describe("observer area localStorage helpers", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("getDisabledObserverAreas returns an empty set by default", () => {
    expect(getDisabledObserverAreas().size).toBe(0);
  });

  it("setDisabled/getDisabled round-trip persists areas", () => {
    setDisabledObserverAreas(new Set(["north", "south"]));
    const result = getDisabledObserverAreas();
    expect(result.has("north")).toBe(true);
    expect(result.has("south")).toBe(true);
  });

  it("toggleObserverArea adds and removes an area", () => {
    const afterAdd = toggleObserverArea("north", 3);
    expect(afterAdd.has("north")).toBe(true);
    const afterRemove = toggleObserverArea("north", 3);
    expect(afterRemove.has("north")).toBe(false);
  });

  it("blocks disabling the last remaining area", () => {
    setDisabledObserverAreas(new Set(["north", "south"]));
    const result = toggleObserverArea("west", 3);
    expect(result.has("west")).toBe(false);
    expect(result.size).toBe(2);
  });
});

describe("ObserverFilterBadges", () => {
  it("renders nothing when areas is empty", () => {
    const { container } = render(
      <ObserverFilterBadges areas={[]} disabled={new Set()} onToggle={() => {}} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders enabled and disabled badges and calls onToggle on click", () => {
    const onToggle = vi.fn();
    render(
      <ObserverFilterBadges
        areas={["North", "South"]}
        disabled={new Set(["South"])}
        onToggle={onToggle}
      />,
    );
    const badges = screen.getAllByTestId("observer-area");
    expect(badges).toHaveLength(2);
    expect(badges[0]).toHaveAttribute("data-area", "North");
    fireEvent.click(badges[0]);
    expect(onToggle).toHaveBeenCalledWith("North");
  });
});
