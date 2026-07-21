import { render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TimeAgo } from "@/components/TimeAgo";

vi.mock("@/utils/format", async () => {
  const actual =
    await vi.importActual<Record<string, unknown>>("@/utils/format");
  return {
    ...actual,
    formatRelativeTime: () => "2 hours ago",
    useFormatDateTime: () => ({
      formatDateTime: () => "Jan 1, 2026 12:00",
    }),
  };
});

describe("TimeAgo", () => {
  it("renders relative text with the full time as title and datetime", () => {
    const { container } = render(<TimeAgo iso="2026-01-01T12:00:00Z" />);
    const time = container.querySelector("time");
    expect(time).not.toBeNull();
    expect(time).toHaveAttribute("datetime", "2026-01-01T12:00:00Z");
    expect(time).toHaveAttribute("title", "Jan 1, 2026 12:00");
    expect(time).toHaveTextContent("2 hours ago");
  });

  it("applies a custom className", () => {
    const { container } = render(
      <TimeAgo iso="2026-01-01T12:00:00Z" className="text-xs" />,
    );
    expect(container.querySelector("time")).toHaveClass("text-xs");
  });

  it("renders nothing when iso is null", () => {
    const { container } = render(<TimeAgo iso={null} />);
    expect(container.querySelector("time")).toBeNull();
  });
});
