"""Tests for custom pages functionality (SPA)."""

import json
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from meshcore_hub.web.pages import CustomPage, PageLoader


class TestCustomPage:
    """Tests for the CustomPage dataclass."""

    def test_url_property(self) -> None:
        """Test that url property returns correct path."""
        page = CustomPage(
            slug="about",
            title="About Us",
            menu_order=10,
            content_html="<p>Content</p>",
            file_path="/pages/about.md",
        )
        assert page.url == "/pages/about"

    def test_url_property_with_hyphenated_slug(self) -> None:
        """Test url property with hyphenated slug."""
        page = CustomPage(
            slug="terms-of-service",
            title="Terms of Service",
            menu_order=50,
            content_html="<p>Terms</p>",
            file_path="/pages/terms-of-service.md",
        )
        assert page.url == "/pages/terms-of-service"


class TestPageLoader:
    """Tests for the PageLoader class."""

    def test_load_pages_nonexistent_directory(self) -> None:
        """Test loading from a non-existent directory."""
        loader = PageLoader("/nonexistent/path")
        loader.load_pages()

        assert loader.get_menu_pages() == []

    def test_load_pages_empty_directory(self) -> None:
        """Test loading from an empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loader = PageLoader(tmpdir)
            loader.load_pages()

            assert loader.get_menu_pages() == []

    def test_load_pages_with_frontmatter(self) -> None:
        """Test loading a page with full frontmatter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            page_path = Path(tmpdir) / "about.md"
            page_path.write_text(
                """---
title: About Us
slug: about
menu_order: 10
---

# About

This is the about page.
"""
            )

            loader = PageLoader(tmpdir)
            loader.load_pages()

            pages = loader.get_menu_pages()
            assert len(pages) == 1
            assert pages[0].slug == "about"
            assert pages[0].title == "About Us"
            assert pages[0].menu_order == 10
            assert "About</h1>" in pages[0].content_html
            assert "<p>This is the about page.</p>" in pages[0].content_html

    def test_load_pages_default_slug_from_filename(self) -> None:
        """Test that slug defaults to filename when not specified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            page_path = Path(tmpdir) / "my-custom-page.md"
            page_path.write_text(
                """---
title: My Custom Page
---

Content here.
"""
            )

            loader = PageLoader(tmpdir)
            loader.load_pages()

            pages = loader.get_menu_pages()
            assert len(pages) == 1
            assert pages[0].slug == "my-custom-page"

    def test_load_pages_default_title_from_slug(self) -> None:
        """Test that title defaults to titlecased slug when not specified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            page_path = Path(tmpdir) / "terms-of-service.md"
            page_path.write_text("Just content, no frontmatter.")

            loader = PageLoader(tmpdir)
            loader.load_pages()

            pages = loader.get_menu_pages()
            assert len(pages) == 1
            assert pages[0].title == "Terms Of Service"

    def test_load_pages_default_menu_order(self) -> None:
        """Test that menu_order defaults to 100."""
        with tempfile.TemporaryDirectory() as tmpdir:
            page_path = Path(tmpdir) / "page.md"
            page_path.write_text(
                """---
title: Test Page
---

Content.
"""
            )

            loader = PageLoader(tmpdir)
            loader.load_pages()

            pages = loader.get_menu_pages()
            assert len(pages) == 1
            assert pages[0].menu_order == 100

    def test_load_pages_sorted_by_menu_order(self) -> None:
        """Test that pages are sorted by menu_order then title."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create pages with different menu_order values
            (Path(tmpdir) / "page-z.md").write_text(
                """---
title: Z Page
menu_order: 30
---

Content.
"""
            )
            (Path(tmpdir) / "page-a.md").write_text(
                """---
title: A Page
menu_order: 10
---

Content.
"""
            )
            (Path(tmpdir) / "page-m.md").write_text(
                """---
title: M Page
menu_order: 20
---

Content.
"""
            )

            loader = PageLoader(tmpdir)
            loader.load_pages()

            pages = loader.get_menu_pages()
            assert len(pages) == 3
            assert [p.title for p in pages] == ["A Page", "M Page", "Z Page"]

    def test_load_pages_secondary_sort_by_title(self) -> None:
        """Test that pages with same menu_order are sorted by title."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "zebra.md").write_text(
                """---
title: Zebra
menu_order: 10
---

Content.
"""
            )
            (Path(tmpdir) / "apple.md").write_text(
                """---
title: Apple
menu_order: 10
---

Content.
"""
            )

            loader = PageLoader(tmpdir)
            loader.load_pages()

            pages = loader.get_menu_pages()
            assert len(pages) == 2
            assert [p.title for p in pages] == ["Apple", "Zebra"]

    def test_get_page_returns_correct_page(self) -> None:
        """Test that get_page returns the page with the given slug."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "about.md").write_text(
                """---
title: About
slug: about
---

About content.
"""
            )
            (Path(tmpdir) / "contact.md").write_text(
                """---
title: Contact
slug: contact
---

Contact content.
"""
            )

            loader = PageLoader(tmpdir)
            loader.load_pages()

            page = loader.get_page("about")
            assert page is not None
            assert page.slug == "about"
            assert page.title == "About"

            page = loader.get_page("contact")
            assert page is not None
            assert page.slug == "contact"

    def test_get_page_returns_none_for_unknown_slug(self) -> None:
        """Test that get_page returns None for unknown slugs."""
        loader = PageLoader("/nonexistent")
        loader.load_pages()

        assert loader.get_page("unknown") is None

    def test_reload_clears_and_reloads(self) -> None:
        """Test that reload() clears existing pages and reloads from disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            page_path = Path(tmpdir) / "page.md"
            page_path.write_text(
                """---
title: Original
---

Content.
"""
            )

            loader = PageLoader(tmpdir)
            loader.load_pages()

            pages = loader.get_menu_pages()
            assert len(pages) == 1
            assert pages[0].title == "Original"

            # Update the file
            page_path.write_text(
                """---
title: Updated
---

New content.
"""
            )

            loader.reload()

            pages = loader.get_menu_pages()
            assert len(pages) == 1
            assert pages[0].title == "Updated"

    def test_load_pages_ignores_non_md_files(self) -> None:
        """Test that only .md files are loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "page.md").write_text("# Valid Page")
            (Path(tmpdir) / "readme.txt").write_text("Not a markdown file")
            (Path(tmpdir) / "data.json").write_text('{"key": "value"}')

            loader = PageLoader(tmpdir)
            loader.load_pages()

            pages = loader.get_menu_pages()
            assert len(pages) == 1
            assert pages[0].slug == "page"

    def test_markdown_tables_rendered(self) -> None:
        """Test that markdown tables are rendered to HTML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "tables.md").write_text(
                """---
title: Tables
---

| Header 1 | Header 2 |
|----------|----------|
| Cell 1   | Cell 2   |
"""
            )

            loader = PageLoader(tmpdir)
            loader.load_pages()

            pages = loader.get_menu_pages()
            assert len(pages) == 1
            assert "<table>" in pages[0].content_html
            assert "<th>" in pages[0].content_html

    def test_markdown_fenced_code_rendered(self) -> None:
        """Test that fenced code blocks are rendered."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "code.md").write_text(
                """---
title: Code
---

```python
def hello():
    print("Hello!")
```
"""
            )

            loader = PageLoader(tmpdir)
            loader.load_pages()

            pages = loader.get_menu_pages()
            assert len(pages) == 1
            assert "<pre>" in pages[0].content_html
            assert "def hello():" in pages[0].content_html


class TestPagesRoute:
    """Tests for the custom pages routes (SPA).

    In the SPA architecture:
    - /pages/{slug} returns the SPA shell HTML (catch-all)
    - /spa/pages/{slug} returns page content as JSON
    """

    @pytest.fixture
    def pages_dir(self) -> Generator[str, None, None]:
        """Create a temporary content directory with test pages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create pages subdirectory (CONTENT_HOME/pages)
            pages_subdir = Path(tmpdir) / "pages"
            pages_subdir.mkdir()
            (pages_subdir / "about.md").write_text(
                """---
title: About Us
slug: about
menu_order: 10
---

# About Our Network

Welcome to the network.
"""
            )
            (pages_subdir / "faq.md").write_text(
                """---
title: FAQ
slug: faq
menu_order: 20
---

# Frequently Asked Questions

Here are some answers.
"""
            )
            yield tmpdir

    @pytest.fixture
    def web_app_with_pages(
        self, pages_dir: str, mock_http_client: Any
    ) -> Generator[Any, None, None]:
        """Create a web app with custom pages configured."""
        import os

        # Temporarily set CONTENT_HOME environment variable
        os.environ["CONTENT_HOME"] = pages_dir

        from meshcore_hub.web.app import create_app

        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            network_name="Test Network",
        )
        app.state.http_client = mock_http_client

        yield app

        # Cleanup
        del os.environ["CONTENT_HOME"]

    @pytest.fixture
    def client_with_pages(
        self, web_app_with_pages: Any, mock_http_client: Any
    ) -> TestClient:
        """Create a test client with custom pages."""
        web_app_with_pages.state.http_client = mock_http_client
        return TestClient(web_app_with_pages, raise_server_exceptions=True)

    def test_page_route_returns_spa_shell(self, client_with_pages: TestClient) -> None:
        """Test that /pages/{slug} returns the SPA shell HTML."""
        response = client_with_pages.get("/pages/about")
        assert response.status_code == 200
        assert "window.__APP_CONFIG__" in response.text

    def test_page_route_nonexistent_returns_spa_shell(
        self, client_with_pages: TestClient
    ) -> None:
        """Test that /pages/{slug} returns SPA shell even for nonexistent pages.

        The SPA catch-all serves the shell for all routes.
        Client-side code fetches page content via /spa/pages/{slug}.
        """
        response = client_with_pages.get("/pages/nonexistent")
        assert response.status_code == 200
        assert "window.__APP_CONFIG__" in response.text

    def test_spa_page_api_returns_json(self, client_with_pages: TestClient) -> None:
        """Test that /spa/pages/{slug} returns page content as JSON."""
        response = client_with_pages.get("/spa/pages/about")
        assert response.status_code == 200
        assert "application/json" in response.headers["content-type"]

        data = response.json()
        assert data["slug"] == "about"
        assert data["title"] == "About Us"
        assert "About Our Network" in data["content_html"]
        assert "Welcome to the network" in data["content_html"]

    def test_spa_page_api_not_found(self, client_with_pages: TestClient) -> None:
        """Test that /spa/pages/{slug} returns 404 for unknown page."""
        response = client_with_pages.get("/spa/pages/nonexistent")
        assert response.status_code == 404
        data = response.json()
        assert data["detail"] == "Page not found"

    def test_spa_page_api_faq(self, client_with_pages: TestClient) -> None:
        """Test that /spa/pages/faq returns FAQ page content."""
        response = client_with_pages.get("/spa/pages/faq")
        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == "faq"
        assert data["title"] == "FAQ"
        assert "Frequently Asked Questions" in data["content_html"]

    def test_pages_in_navigation(self, client_with_pages: TestClient) -> None:
        """Test that custom pages appear in navigation."""
        response = client_with_pages.get("/")
        assert response.status_code == 200
        # Check for navigation links
        assert 'href="/pages/about"' in response.text
        assert 'href="/pages/faq"' in response.text

    def test_pages_sorted_in_navigation(self, client_with_pages: TestClient) -> None:
        """Test that pages are sorted by menu_order in navigation."""
        response = client_with_pages.get("/")
        assert response.status_code == 200
        # About (order 10) should appear before FAQ (order 20)
        about_pos = response.text.find('href="/pages/about"')
        faq_pos = response.text.find('href="/pages/faq"')
        assert about_pos < faq_pos

    def test_pages_in_config(self, client_with_pages: TestClient) -> None:
        """Test that custom pages are included in SPA config."""
        response = client_with_pages.get("/")
        text = response.text
        config_start = text.find("window.__APP_CONFIG__ = ") + len(
            "window.__APP_CONFIG__ = "
        )
        config_end = text.find(";", config_start)
        config = json.loads(text[config_start:config_end])

        custom_pages = config["custom_pages"]
        assert len(custom_pages) == 2
        slugs = [p["slug"] for p in custom_pages]
        assert "about" in slugs
        assert "faq" in slugs


class TestPagesInSitemap:
    """Tests for custom pages in sitemap."""

    @pytest.fixture
    def pages_dir(self) -> Generator[str, None, None]:
        """Create a temporary content directory with test pages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create pages subdirectory (CONTENT_HOME/pages)
            pages_subdir = Path(tmpdir) / "pages"
            pages_subdir.mkdir()
            (pages_subdir / "about.md").write_text(
                """---
title: About
slug: about
---

About page.
"""
            )
            yield tmpdir

    @pytest.fixture
    def client_with_pages_for_sitemap(
        self, pages_dir: str, mock_http_client: Any
    ) -> Generator[TestClient, None, None]:
        """Create a test client with custom pages for sitemap testing."""
        import os

        os.environ["CONTENT_HOME"] = pages_dir

        from meshcore_hub.web.app import create_app

        app = create_app(
            api_url="http://localhost:8000",
            api_key="test-api-key",
            network_name="Test Network",
        )
        app.state.http_client = mock_http_client

        client = TestClient(app, raise_server_exceptions=True)
        yield client

        del os.environ["CONTENT_HOME"]

    def test_pages_included_in_sitemap(
        self, client_with_pages_for_sitemap: TestClient
    ) -> None:
        """Test that custom pages are included in sitemap.xml."""
        response = client_with_pages_for_sitemap.get("/sitemap.xml")
        assert response.status_code == 200
        assert "/pages/about" in response.text
        assert "<changefreq>weekly</changefreq>" in response.text
