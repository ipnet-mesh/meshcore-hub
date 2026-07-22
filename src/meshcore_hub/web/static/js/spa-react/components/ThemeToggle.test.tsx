import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { ThemeToggle } from "@/components/ThemeToggle";

describe("ThemeToggle", () => {
  beforeEach(() => {
    document.documentElement.removeAttribute("data-theme");
    localStorage.clear();
  });

  it("initializes unchecked when no data-theme attribute is set", () => {
    render(<ThemeToggle />);
    expect(screen.getByTestId("theme-toggle")).not.toBeChecked();
  });

  it("toggling sets data-theme to light and persists to localStorage", () => {
    render(<ThemeToggle />);
    const checkbox = screen.getByTestId("theme-toggle");
    fireEvent.click(checkbox);
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(localStorage.getItem("meshcore-theme")).toBe("light");
    expect(checkbox).toBeChecked();
  });

  it("toggling back switches to dark", () => {
    render(<ThemeToggle />);
    const checkbox = screen.getByTestId("theme-toggle");
    fireEvent.click(checkbox);
    fireEvent.click(checkbox);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(localStorage.getItem("meshcore-theme")).toBe("dark");
  });

  it("renders both sun and moon svg icons", () => {
    const { container } = render(<ThemeToggle />);
    expect(container.querySelectorAll("svg").length).toBeGreaterThanOrEqual(2);
  });
});
