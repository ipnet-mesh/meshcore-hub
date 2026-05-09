# Plan: Network Announcement Flash Banner

**Date:** 2026-05-09
**Status:** Draft

## Problem

Network operators need a way to display a prominent, time-limited announcement to all dashboard users — for example, scheduled maintenance notices, event announcements, or incident alerts. There is currently no mechanism to show persistent, page-wide banners in the web dashboard.

## Approach

Add a `NETWORK_ANNOUNCEMENT` environment variable to `WebSettings`. When set to a non-empty string, a "flash banner" is rendered server-side in the SPA shell (`spa.html`) between the navbar and the `<main>` content area. The banner is:

- Rendered by Jinja2 at page load (no JS needed for display, no FOUC)
- Visible on every page (part of the shell template, not SPA-routed content)
- Dismissable per-session via a close button (hidden using `sessionStorage`)
- Styled with a distinctive DaisyUI alert style using `alert-warning` or `alert-info`
- Supporting Markdown input (rendered to HTML server-side using the existing `markdown` library, same as custom pages)

### New Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `NETWORK_ANNOUNCEMENT` | Markdown announcement text to display as a flash banner (empty = no banner). Supports bold, italic, links, inline code. | `None` (empty) |

This follows the existing pattern of `NETWORK_WELCOME_TEXT` and other `NETWORK_*` settings.

## Scope of Changes

### 1. Configuration (`common/config.py`)

**File:** `src/meshcore_hub/common/config.py` — `WebSettings` class (~line 335)

Add a new field in the "Network information" section, after `network_welcome_text`:

```python
network_announcement: Optional[str] = Field(
    default=None, description="Markdown announcement text for flash banner (empty = no banner)"
)
```

### 2. Web App State (`web/app.py`)

**File:** `src/meshcore_hub/web/app.py`

Three locations need updating:

#### 2a. `create_app()` function signature (~line 340)

Add `network_announcement` parameter:

```python
def create_app(
    ...
    network_welcome_text: str | None = None,
    network_announcement: str | None = None,  # NEW
    features: dict[str, bool] | None = None,
) -> FastAPI:
```

#### 2b. `create_app()` body — app.state initialization (~line 470)

After the `network_welcome_text` assignment, render the announcement Markdown to HTML and store on `app.state`:

```python
    raw_announcement = network_announcement or settings.network_announcement
if raw_announcement:
    import markdown
    app.state.network_announcement = markdown.markdown(
        raw_announcement
    )
else:
    app.state.network_announcement = None
```

This converts the Markdown to HTML once at startup (not on every request). The `markdown` library is already a project dependency (`markdown>=3.5.0` in `pyproject.toml`) and is used the same way in `web/pages.py` for custom pages.

#### 2c. `spa_catchall()` template context (~line 1098)

Add `network_announcement` to the template context dict:

```python
{
    ...
    "network_announcement": request.app.state.network_announcement,
    ...
}
```

Note: `network_announcement` is intentionally **not** added to the JS config injected via `_build_config_json()` (at `app.py:283-307`). The banner is server-side rendered and the SPA frontend does not need this value — it's purely a template-level concern.

### 3. SPA Template (`web/templates/spa.html`)

**File:** `src/meshcore_hub/web/templates/spa.html` (~line 107)

Insert the banner between the navbar `</div>` (line 106) and `<main>` (line 109):

```html
    </div>

    <!-- Flash Banner (shown when NETWORK_ANNOUNCEMENT is set) -->
    {% if network_announcement %}
    <div id="flash-banner" class="alert alert-warning rounded-none py-2 px-4 text-center text-sm">
        <div class="flash-banner-content">{{ network_announcement | safe }}</div>
        <button aria-label="Dismiss" onclick="document.getElementById('flash-banner').style.display='none'; sessionStorage.setItem('flash-banner-dismissed','1')" class="btn btn-ghost btn-xs">&times;</button>
    </div>
    <script>
        if (sessionStorage.getItem('flash-banner-dismissed') === '1') {
            document.getElementById('flash-banner').style.display = 'none';
        }
    </script>
    {% endif %}

    <!-- Main Content -->
    <main ...>
```

Key design decisions:
- **`alert-warning`**: Amber/yellow tone is visible but not alarming — suitable for maintenance notices and general announcements. Stands out from the standard UI without implying an error.
- **`rounded-none`**: Full-width edge-to-edge look, visually distinct from in-page alert components.
- **`sessionStorage` dismissal**: Banner reappears on new browser sessions/tabs but stays dismissed within the same session. This balances persistence (operators want users to see it) with user experience (no nagging within a session).
- **`{{ network_announcement | safe }}`**: The Markdown is converted to HTML server-side at startup (not at render time) using the Python `markdown` library. The `|safe` filter is needed to render the generated HTML. This is safe because: (1) the source is an environment variable controlled by the operator, not user input; (2) this is the same pattern used in `pages.py` for custom Markdown pages; (3) the Markdown library does not execute arbitrary JavaScript from Markdown syntax. **Note:** This differs from `network_welcome_text` which is rendered as plain text via Jinja2 autoescaping (no `|safe`). The announcement supports rich text (Markdown), while welcome text is plain text only.
- **`<div class="flash-banner-content">`**: Wraps the rendered HTML for scoped styling (links, bold, italic, inline code).

### 4. Web CLI (`web/cli.py`)

**File:** `src/meshcore_hub/web/cli.py`

Three locations need updating:

#### 4a. Add `--network-announcement` Click option (~line 104, after `--network-welcome-text`)

```python
@click.option(
    "--network-announcement",
    type=str,
    default=None,
    envvar="NETWORK_ANNOUNCEMENT",
    help="Announcement text for flash banner",
)
```

#### 4b. Add `network_announcement: str | None` to the `web()` function signature (~line 128)

After `network_welcome_text: str | None,`:

```python
    network_announcement: str | None,
```

#### 4c. Pass it through to `create_app()` (~line 220)

```python
app = create_app(
    ...
    network_announcement=network_announcement,
)
```

### 5. Custom CSS (`web/static/css/app.css`)

**File:** `src/meshcore_hub/web/static/css/app.css`

Add a small CSS section for flash banner adjustments:

```css
/* ==========================================================================
   Flash Banner
   ========================================================================== */

#flash-banner {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
}

.flash-banner-content {
    display: inline;
}

.flash-banner-content a {
    text-decoration: underline;
    font-weight: 600;
}

.flash-banner-content a:hover {
    opacity: 0.8;
}

.flash-banner-content code {
    font-size: 0.875rem;
    padding: 0.125rem 0.375rem;
    border-radius: 0.25rem;
    background: oklch(var(--b3) / 0.5);
}

.flash-banner-content p {
    display: inline;
    margin: 0;
}

.flash-banner-content p + p {
    display: block;
    margin-top: 0.25rem;
}
```

This ensures consistent centering and spacing, and styles rendered Markdown elements (links, inline code, paragraphs) inline within the alert. The heavy lifting is done by DaisyUI's `alert` classes.

### 6. Documentation Updates

| File | Change |
|------|--------|
| `AGENTS.md` | Add `NETWORK_ANNOUNCEMENT` to the Environment Variables table, in the "Network information" sub-section, after `NETWORK_WELCOME_TEXT` |
| `.env.example` | Add `NETWORK_ANNOUNCEMENT=` entry with description comment, after `NETWORK_WELCOME_TEXT=` (line 440) |

### Files Changed (Summary)

| File | Change |
|------|--------|
| `src/meshcore_hub/common/config.py` | Add `network_announcement` field to `WebSettings` |
| `src/meshcore_hub/web/app.py` | Add param to `create_app()`, wire to `app.state`, add to template context |
| `src/meshcore_hub/web/templates/spa.html` | Add conditional flash banner HTML between navbar and main |
| `src/meshcore_hub/web/static/css/app.css` | Add flash banner CSS section |
| `src/meshcore_hub/web/cli.py` | Add `--network-announcement` CLI option |
| `AGENTS.md` | Document `NETWORK_ANNOUNCEMENT` env var |
| `.env.example` | Add `NETWORK_ANNOUNCEMENT` entry |

### Tests to Add/Update

| Test File | Change |
|-----------|--------|
| `tests/test_web/test_app.py` | Verify banner HTML present when `network_announcement` is set; absent when `None` |
| `tests/test_web/test_app.py` | Verify Markdown is rendered: `**bold**` → `<strong>bold</strong>`, `[link](url)` → `<a href="url">link</a>` |
| `tests/test_web/test_app.py` | Verify raw HTML in input is escaped (e.g. `<script>` does not execute) |
| `tests/test_web/test_app.py` | Verify banner is not shown for empty string `""` or whitespace-only `"   "` |
| `tests/test_common/test_config.py` | Verify `network_announcement` field defaults to `None` |

### Edge Cases

- **`NETWORK_ANNOUNCEMENT` is empty string**: Banner should not appear (Jinja2 `{% if %}` is falsy for `""`).
- **`NETWORK_ANNOUNCEMENT` contains raw HTML**: The Python `markdown` library passes raw HTML through by default (e.g., `<b>bold</b>` renders as-is). This is safe because the source is an operator-controlled environment variable — same trust model as custom pages in `pages.py`.
- **Markdown with links**: Links render as `<a>` tags with proper styling. External links open in the same tab (no `target="_blank"` added) to keep the banner simple.
- **Very long announcement text**: DaisyUI `alert` will wrap naturally. Consider adding `max-height` + `overflow` in CSS if needed, but likely unnecessary for typical one-line notices.
- **Dismissed banner persists on SPA navigation**: Since the banner is in the shell (not SPA content), it stays visible/hidden across SPA route changes. `sessionStorage` survives SPA navigations.
- **Multiple browser tabs**: Each tab has its own `sessionStorage`, so dismissing in one tab does not affect another. This is desirable — each tab should independently show the banner until dismissed.
- **Reload/restart**: Since the banner text comes from `app.state` (loaded at startup), changing `NETWORK_ANNOUNCEMENT` requires a server restart. This matches the behavior of all other `NETWORK_*` settings.

### Out of Scope

- Multiple banner levels (info/warning/error) — a single warning-style banner is sufficient for the initial implementation
- Start/end datetime for automatic show/hide — operators can set/unset the env var and restart
- Admin UI for editing the announcement — env var only
- Animation or slide-in effects — static display is sufficient

## Implementation Order

1. Add `network_announcement` field to `WebSettings` in `config.py`
2. Wire `network_announcement` into `create_app()`, `app.state`, and `spa_catchall()` in `web/app.py`
3. Add conditional banner HTML to `spa.html`
4. Add CSS for flash banner in `app.css`
5. Add `--network-announcement` CLI option to `web/cli.py`
6. Add tests
7. Update documentation (`AGENTS.md`, `.env.example`)
8. Run `pre-commit run --all-files` and `pytest tests/test_web/`
