"""Custom markdown pages loader for MeshCore Hub Web Dashboard."""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import frontmatter
import markdown

logger = logging.getLogger(__name__)


@dataclass
class CustomPage:
    """Represents a custom markdown page."""

    slug: str
    title: str
    menu_order: int
    content_html: str
    file_path: str

    @property
    def url(self) -> str:
        """Get the URL path for this page."""
        return f"/pages/{self.slug}"


class PageLoader:
    """Loads and manages custom markdown pages from a directory."""

    def __init__(self, pages_dir: str) -> None:
        """Initialize the page loader.

        Args:
            pages_dir: Path to the directory containing markdown pages.
        """
        self.pages_dir = Path(pages_dir)
        self._pages: dict[str, CustomPage] = {}
        self._md = markdown.Markdown(
            extensions=["tables", "fenced_code", "toc"],
            output_format="html",
        )

    def load_pages(self) -> None:
        """Load all markdown pages from the pages directory."""
        self._pages.clear()

        if not self.pages_dir.exists():
            logger.debug(f"Pages directory does not exist: {self.pages_dir}")
            return

        if not self.pages_dir.is_dir():
            logger.warning(f"Pages path is not a directory: {self.pages_dir}")
            return

        for md_file in self.pages_dir.glob("*.md"):
            try:
                page = self._load_page(md_file)
                if page:
                    self._pages[page.slug] = page
                    logger.info(f"Loaded custom page: {page.slug} ({md_file.name})")
            except Exception as e:
                logger.error(f"Failed to load page {md_file}: {e}")

        logger.info(f"Loaded {len(self._pages)} custom page(s)")

    def _load_page(self, file_path: Path) -> Optional[CustomPage]:
        """Load a single markdown page.

        Args:
            file_path: Path to the markdown file.

        Returns:
            CustomPage instance or None if loading failed.
        """
        content = file_path.read_text(encoding="utf-8")
        post = frontmatter.loads(content)

        # Extract frontmatter fields
        slug = post.get("slug", file_path.stem)
        title = post.get("title", slug.replace("-", " ").replace("_", " ").title())
        menu_order = post.get("menu_order", 100)

        # Convert markdown to HTML
        self._md.reset()
        content_html = self._md.convert(post.content)

        return CustomPage(
            slug=slug,
            title=title,
            menu_order=menu_order,
            content_html=content_html,
            file_path=str(file_path),
        )

    def get_page(self, slug: str) -> Optional[CustomPage]:
        """Get a page by its slug.

        Args:
            slug: The page slug.

        Returns:
            CustomPage instance or None if not found.
        """
        return self._pages.get(slug)

    def get_menu_pages(self) -> list[CustomPage]:
        """Get all pages sorted by menu_order for navigation.

        Returns:
            List of CustomPage instances sorted by menu_order.
        """
        return sorted(self._pages.values(), key=lambda p: (p.menu_order, p.title))

    def reload(self) -> None:
        """Reload all pages from disk."""
        self.load_pages()
