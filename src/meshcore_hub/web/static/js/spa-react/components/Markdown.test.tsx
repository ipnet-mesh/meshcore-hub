import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Markdown } from "@/components/Markdown";

describe("Markdown", () => {
  it("renders bold and italic inline markup", () => {
    const { container } = render(<Markdown>{"**bold** and *italic*"}</Markdown>);
    expect(container.querySelector("strong")?.textContent).toBe("bold");
    expect(container.querySelector("em")?.textContent).toBe("italic");
  });

  it("renders GFM tables", () => {
    const md = `
| A | B |
|---|---|
| 1 | 2 |
`;
    const { container } = render(<Markdown>{md}</Markdown>);
    const table = container.querySelector("table");
    expect(table).not.toBeNull();
    expect(container.querySelectorAll("th").length).toBe(2);
    expect(container.querySelectorAll("tbody td").length).toBe(2);
  });

  it("renders fenced code blocks", () => {
    const md = [
      "```python",
      "def hello():",
      "    pass",
      "```",
    ].join("\n");
    const { container } = render(<Markdown>{md}</Markdown>);
    expect(container.querySelector("pre")).not.toBeNull();
    expect(container.querySelector("pre code")?.textContent).toContain("def hello():");
  });

  it("renders links", () => {
    const { container } = render(
      <Markdown>{"[click](https://example.com)"}</Markdown>,
    );
    const link = container.querySelector("a");
    expect(link).toHaveAttribute("href", "https://example.com");
    expect(link?.textContent).toBe("click");
  });

  it("assigns slug ids to headings for deep-linking", () => {
    const md = "# Getting Started\n\n## Sub Section\n";
    const { container } = render(<Markdown>{md}</Markdown>);
    expect(container.querySelector("h1")).toHaveAttribute("id", "getting-started");
    expect(container.querySelector("h2")).toHaveAttribute("id", "sub-section");
  });

  it("wraps headings in anchor links pointing at their id", () => {
    const md = "# Getting Started\n";
    const { container } = render(<Markdown>{md}</Markdown>);
    const link = container.querySelector("h1 a");
    expect(link).toHaveAttribute("href", "#getting-started");
  });

  it("escapes raw HTML (no rehype-raw) for safety", () => {
    const { container } = render(<Markdown>{"<b>bold</b>"}</Markdown>);
    // Raw <b> is escaped, not rendered as an element
    expect(container.querySelector("b")).toBeNull();
    expect(container.textContent).toContain("<b>bold</b>");
  });

  it("renders external links with safe target and rel attributes", () => {
    const { container } = render(
      <Markdown>{"[click](https://example.com)"}</Markdown>,
    );
    const link = container.querySelector("a");
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("does not add target/rel to heading anchor links", () => {
    const md = "# Heading\n";
    const { container } = render(<Markdown>{md}</Markdown>);
    const anchor = container.querySelector("h1 a");
    expect(anchor).toHaveAttribute("href", "#heading");
    expect(anchor).not.toHaveAttribute("target");
    expect(anchor).not.toHaveAttribute("rel");
  });

  it("does not add target/rel to relative links", () => {
    const { container } = render(
      <Markdown>{"[about](/pages/about)"}</Markdown>,
    );
    const link = container.querySelector("a");
    expect(link).toHaveAttribute("href", "/pages/about");
    expect(link).not.toHaveAttribute("target");
    expect(link).not.toHaveAttribute("rel");
  });

  it("applies a custom className override instead of the default prose", () => {
    const { container } = render(
      <Markdown className="flash-banner-content">{"text"}</Markdown>,
    );
    const wrapper = container.querySelector("div");
    expect(wrapper).toHaveClass("flash-banner-content");
    expect(wrapper).not.toHaveClass("prose");
  });

  it("renders GFM task lists and strikethrough", () => {
    const md = "- [x] done\n- [ ] todo\n~~old~~\n";
    const { container } = render(<Markdown>{md}</Markdown>);
    expect(container.querySelector('input[type="checkbox"]')).not.toBeNull();
    expect(container.querySelector("del")?.textContent).toBe("old");
  });
});
