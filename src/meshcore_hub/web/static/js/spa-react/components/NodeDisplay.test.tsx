import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { NodeDisplay, NodeLink } from "@/components/NodeDisplay";

const PUBKEY = "a".repeat(64);

describe("NodeDisplay", () => {
  it("shows the name and an emoji when name is provided", () => {
    const { container } = render(
      <NodeDisplay name="Hub 🔌" publicKey={PUBKEY} advType="repeater" />,
    );
    expect(screen.getByText("Hub 🔌")).toHaveClass("font-medium");
    expect(container.querySelector(".text-lg")).not.toBeNull();
  });

  it("falls back to truncated public key when name is null", () => {
    render(<NodeDisplay name={null} publicKey={PUBKEY} advType={null} />);
    expect(screen.getByText(`${PUBKEY.slice(0, 16)}...`)).toBeInTheDocument();
  });

  it("shows description when provided", () => {
    render(
      <NodeDisplay name="X" description="A node" publicKey={PUBKEY} advType={null} />,
    );
    expect(screen.getByText("A node")).toBeInTheDocument();
  });

  it("omits description when not provided", () => {
    const { container } = render(
      <NodeDisplay name="X" publicKey={PUBKEY} advType={null} />,
    );
    expect(container.querySelector(".opacity-70")).toBeNull();
  });

  it("NodeLink wraps display in a router Link to the node", () => {
    const { container } = render(
      <MemoryRouter>
        <NodeLink name="N" publicKey={PUBKEY} advType={null} />
      </MemoryRouter>,
    );
    const link = container.querySelector("a");
    expect(link).toHaveAttribute("href", `/nodes/${PUBKEY}`);
  });
});
