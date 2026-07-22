import { memo } from "react";
import MarkdownReact from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSlug from "rehype-slug";
import rehypeAutolinkHeadings from "rehype-autolink-headings";

interface MarkdownProps {
  children: string;
  className?: string;
}

export const Markdown = memo(function Markdown({
  children,
  className = "prose prose-lg max-w-none",
}: MarkdownProps) {
  return (
    <div className={className}>
      <MarkdownReact
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[
          rehypeSlug,
          [rehypeAutolinkHeadings, { behavior: "wrap" }],
        ]}
        components={{
          a({ node: _node, href, children, ...rest }) {
            const isExternal = /^https?:\/\//i.test(href ?? "");
            return (
              <a
                href={href}
                {...(isExternal
                  ? { target: "_blank", rel: "noopener noreferrer" }
                  : {})}
                {...rest}
              >
                {children}
              </a>
            );
          },
        }}
      >
        {children}
      </MarkdownReact>
    </div>
  );
});
