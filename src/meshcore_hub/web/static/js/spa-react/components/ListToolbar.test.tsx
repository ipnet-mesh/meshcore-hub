import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ListToolbar } from "@/components/ListToolbar";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: "en" },
  }),
}));

const autoRefresh = {
  paused: false,
  onToggle: () => {},
  intervalSeconds: 30,
};

describe("ListToolbar", () => {
  it("renders the total badge when total is provided", () => {
    render(<ListToolbar total={42} autoRefresh={autoRefresh} />);
    expect(screen.getByText("common.total")).toBeInTheDocument();
  });

  it("hides the total badge when total is null", () => {
    render(<ListToolbar total={null} autoRefresh={autoRefresh} />);
    expect(screen.queryByText("common.total")).not.toBeInTheDocument();
  });

  it("renders a warning badge only when there is an error", () => {
    const { container, rerender } = render(
      <ListToolbar total={null} autoRefresh={autoRefresh} />,
    );
    expect(container.querySelector(".badge-warning")).toBeNull();
    rerender(
      <ListToolbar total={null} error="boom" autoRefresh={autoRefresh} />,
    );
    expect(container.querySelector(".badge-warning")).not.toBeNull();
  });

  it("renders the auto-refresh toggle when interval is positive", () => {
    const { container } = render(
      <ListToolbar total={null} autoRefresh={autoRefresh} />,
    );
    expect(container.querySelector('input[type="checkbox"]')).not.toBeNull();
  });

  it("omits the auto-refresh toggle when interval is not positive", () => {
    const { container } = render(
      <ListToolbar
        total={null}
        autoRefresh={{ ...autoRefresh, intervalSeconds: 0 }}
      />,
    );
    expect(container.querySelector('input[type="checkbox"]')).toBeNull();
  });

  it("renders the filter toggle only when provided", () => {
    const { container, rerender } = render(
      <ListToolbar total={null} autoRefresh={autoRefresh} />,
    );
    expect(container.querySelector("#filter-toggle")).toBeNull();
    rerender(
      <ListToolbar
        total={null}
        autoRefresh={autoRefresh}
        filterToggle={{ open: false, onChange: () => {} }}
      />,
    );
    expect(container.querySelector("#filter-toggle")).not.toBeNull();
  });
});
