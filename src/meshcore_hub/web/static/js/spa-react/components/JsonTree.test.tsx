import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { JsonTree } from "@/components/JsonTree";

describe("JsonTree primitives", () => {
  it("renders string values quoted with the success color", () => {
    const { container } = render(<JsonTree value="hello" />);
    expect(container.querySelector(".text-success")).not.toBeNull();
    expect(container.textContent).toContain('"hello"');
  });

  it("renders numbers with the warning color", () => {
    const { container } = render(<JsonTree value={42} />);
    expect(container.querySelector(".text-warning")).not.toBeNull();
    expect(container.textContent).toContain("42");
  });

  it("renders booleans with the info color", () => {
    const { container } = render(<JsonTree value={true} />);
    expect(container.querySelector(".text-info")).not.toBeNull();
  });

  it("renders null italicized", () => {
    const { container } = render(<JsonTree value={null} />);
    expect(container.querySelector(".italic")).not.toBeNull();
    expect(container.textContent).toContain("null");
  });
});

describe("JsonTree containers", () => {
  it("renders empty objects and arrays inline", () => {
    const { container } = render(<JsonTree value={{ a: {}, b: [] }} openDepth={2} />);
    expect(container.textContent).toContain("{}");
    expect(container.textContent).toContain("[]");
  });

  it("toggles a node via the caret button", () => {
    const { container } = render(
      <JsonTree value={{ nested: { inner: 1 } }} openDepth={2} />,
    );
    const children = container.querySelector(".json-children");
    expect(children).not.toHaveClass("hidden");
    fireEvent.click(container.querySelector(".json-toggle")!);
    expect(container.querySelector(".json-children")).toHaveClass("hidden");
  });

  it("expandAll and collapseAll buttons control all nodes", () => {
    const { container } = render(
      <JsonTree value={{ a: { b: { c: 1 } } }} openDepth={0} />,
    );
    expect(container.querySelector(".json-children")).toHaveClass("hidden");
    fireEvent.click(screen.getByText("packets.expand_all"));
    expect(container.querySelectorAll(".json-children.hidden").length).toBe(0);
    fireEvent.click(screen.getByText("packets.collapse_all"));
    expect(container.querySelectorAll(".json-children.hidden").length).toBeGreaterThan(0);
  });

  it("respects openDepth to auto-expand the top level", () => {
    const { container } = render(<JsonTree value={{ a: 1 }} openDepth={1} />);
    expect(container.querySelector(".json-children")).not.toHaveClass("hidden");
  });
});
