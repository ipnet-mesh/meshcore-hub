import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CopyableValue } from "@/components/CopyableValue";
import { copyToClipboard } from "@/utils/clipboard";

vi.mock("@/utils/clipboard", () => ({
  copyToClipboard: vi.fn(),
}));

describe("CopyableValue", () => {
  it("copies the value on click (inline variant)", () => {
    render(<CopyableValue value="abc123" />);
    const el = screen.getByText("abc123");
    expect(el).toHaveClass("font-mono");
    fireEvent.click(el);
    expect(copyToClipboard).toHaveBeenCalledWith(expect.anything(), "abc123");
  });

  it("renders the block variant with block classes", () => {
    render(<CopyableValue value="deadbeef" variant="block" />);
    const el = screen.getByText("deadbeef");
    expect(el).toHaveClass("block");
    expect(el).toHaveClass("break-all");
    expect(el).not.toHaveClass("font-mono");
  });
});
