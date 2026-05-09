# Tasks: Network Announcement Flash Banner

## Implementation

- [ ] **T1: Add `network_announcement` to `WebSettings`** (`src/meshcore_hub/common/config.py`)
  - Add `network_announcement: Optional[str] = Field(default=None, description="Markdown announcement text for flash banner (empty = no banner)")` after `network_welcome_text` (~line 365)

- [ ] **T2: Wire `network_announcement` into `create_app()`** (`src/meshcore_hub/web/app.py`)
  - Add `network_announcement: str | None = None` param to `create_app()` signature (~line 351)
  - Render Markdown to HTML at startup and store on `app.state.network_announcement` (~line 470):
    ```python
    raw_announcement = network_announcement or settings.network_announcement
    if raw_announcement:
        import markdown
        app.state.network_announcement = markdown.markdown(raw_announcement)
    else:
        app.state.network_announcement = None
    ```
  - Add `"network_announcement": request.app.state.network_announcement` to `spa_catchall()` template context (~line 1098)
  - Do NOT add to `_build_config_json()` — server-side only, SPA doesn't need it

- [ ] **T3: Add conditional banner HTML to `spa.html`** (`src/meshcore_hub/web/templates/spa.html`)
  - Insert between navbar `</div>` (line 106) and `<main>` (line 109):
    ```html
    {% if network_announcement %}
    <div id="flash-banner" class="alert alert-warning rounded-none py-2 px-4 text-center text-sm">
        <div class="flash-banner-content">{{ network_announcement | safe }}</div>
        <button aria-label="Dismiss" onclick="..." class="btn btn-ghost btn-xs">&times;</button>
    </div>
    <script>
        if (sessionStorage.getItem('flash-banner-dismissed') === '1') {
            document.getElementById('flash-banner').style.display = 'none';
        }
    </script>
    {% endif %}
    ```

- [ ] **T4: Add flash banner CSS** (`src/meshcore_hub/web/static/css/app.css`)
  - Add `#flash-banner` layout rules (flex, centering, gap)
  - Add `.flash-banner-content` scoped styles for `a`, `code`, `p` elements

- [ ] **T5: Add `--network-announcement` CLI option** (`src/meshcore_hub/web/cli.py`)
  - Add `@click.option("--network-announcement", ...)` after `--network-welcome-text` (~line 104)
  - Add `network_announcement: str | None` to `web()` function signature (~line 128)
  - Pass `network_announcement=network_announcement` to `create_app()` call (~line 220)

## Tests

- [ ] **T6: Banner visibility tests** (`tests/test_web/test_app.py`)
  - Test: banner HTML present when `network_announcement` is set
  - Test: banner absent when `network_announcement` is `None`
  - Test: banner not shown for empty string `""` or whitespace-only `"   "`

- [ ] **T7: Markdown rendering tests** (`tests/test_web/test_app.py`)
  - Test: `**bold**` rendered as `<strong>bold</strong>`
  - Test: `[link](url)` rendered as `<a href="url">link</a>`
  - Test: raw HTML like `<script>` is escaped, not executed

- [ ] **T8: Config default test** (`tests/test_common/test_config.py`)
  - Test: `network_announcement` field defaults to `None`

## Documentation & Quality

- [ ] **T9: Update documentation** (`AGENTS.md`, `.env.example`)
  - Add `NETWORK_ANNOUNCEMENT` to Environment Variables → "Network information" sub-section in `AGENTS.md`, after `NETWORK_WELCOME_TEXT`
  - Add `NETWORK_ANNOUNCEMENT=` entry to `.env.example` after `NETWORK_WELCOME_TEXT=` (line 440)

- [ ] **T10: Run quality checks**
  - `pre-commit run --all-files`
  - `pytest tests/test_web/ tests/test_common/test_config.py`
