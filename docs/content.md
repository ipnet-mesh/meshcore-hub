# Custom Content

The web dashboard supports custom content including markdown pages and media files. Content is served from the `CONTENT_HOME` directory (default: `./content`).

## Directory Structure

```
content/
├── pages/     # Custom markdown pages
│   └── about.md
└── media/     # Custom media files
    └── images/
        ├── logo.svg          # Full-color custom logo (default)
        └── logo-invert.svg   # Monochrome custom logo (darkened in light mode)
```

## Custom Logos

The web dashboard supports custom logo images placed in `media/images/`:

- `logo.svg` — full-color logo, displayed as-is in both themes (no automatic darkening)
- `logo-invert.svg` — monochrome/two-tone logo, automatically darkened in light mode for visibility

If no custom logos are provided, the default MeshCore Hub logos are used.

## Markdown Pages

Custom pages are written in Markdown with optional YAML frontmatter for metadata. Pages automatically appear in the navigation menu and sitemap.

### Setup

```bash
# Create content directory structure
mkdir -p content/pages content/media

# Create a custom page
cat > content/pages/about.md << 'EOF'
---
title: About Us
slug: about
menu_order: 10
---

# About Our Network

Welcome to our MeshCore mesh network!

## Getting Started

1. Get a compatible LoRa device
2. Flash MeshCore firmware
3. Configure your radio settings
EOF
```

### Frontmatter Fields

Pages use YAML frontmatter for metadata:

```markdown
---
title: About Us        # Browser tab title and nav link (not rendered on page)
slug: about            # URL path (default: filename without .md)
menu_order: 10         # Nav sort order (default: 100, lower = earlier)
---

# About Our Network

Markdown content here (include your own heading)...
```

| Field | Default | Description |
|-------|---------|-------------|
| `title` | Filename titlecased | Browser tab title and navigation link text (not rendered on page) |
| `slug` | Filename without `.md` | URL path (e.g., `about` → `/pages/about`) |
| `menu_order` | `100` | Sort order in navigation (lower = earlier) |

The markdown content is rendered as-is, so include your own `# Heading` if desired.

### Supported Markdown Features

Pages are shipped as raw markdown and rendered client-side by the React SPA
(`react-markdown` + `remark-gfm`). Raw HTML in the source is **escaped** (not
rendered) — this is a security choice; use markdown syntax instead of inline HTML.

| Feature | Syntax | Notes |
|---------|--------|-------|
| Headings | `# H1` through `### H3` | Rendered with `.prose` styling; each heading gets an anchor `id` for deep-linking (e.g. `/pages/about#getting-started`) |
| Bold / Italic | `**bold**`, `*italic*` | Standard Markdown |
| Links | `[text](url)` | Relative paths supported |
| Unordered lists | `- item` or `* item` | Nested lists supported |
| Ordered lists | `1. item` | Nested lists supported |
| Tables | Pipe-delimited (`\| Header \|`) | GFM tables (thead/tbody) |
| Fenced code blocks | ` ``` ` with optional language | Rendered as `<pre><code>` |
| Inline code | `` `code` `` | Styled with monospace font |
| Blockquotes | `> quote` | Left border styling |
| Images | `![alt](/media/image.png)` | Use absolute paths to `/media/` |
| Task lists | `- [ ] item` / `- [x] item` | GFM task lists |
| Strikethrough | `~~text~~` | GFM |

## Docker Configuration

With Docker, mount the content directory as a read-only volume. This is already configured in `docker-compose.yml`:

```yaml
volumes:
  - ${CONTENT_HOME:-./content}:/content:ro
environment:
  - CONTENT_HOME=/content
```

The `CONTENT_HOME` variable (default `./content`) is documented in [configuration.md → Web Dashboard](configuration.md#web-dashboard).
