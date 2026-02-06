"""Custom pages route for MeshCore Hub Web Dashboard."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from meshcore_hub.web.app import get_network_context, get_templates

router = APIRouter(tags=["Pages"])


@router.get("/pages/{slug}", response_class=HTMLResponse)
async def custom_page(request: Request, slug: str) -> HTMLResponse:
    """Render a custom markdown page.

    Args:
        request: FastAPI request object.
        slug: The page slug from the URL.

    Returns:
        Rendered HTML page.

    Raises:
        HTTPException: 404 if page not found.
    """
    page_loader = request.app.state.page_loader
    page = page_loader.get_page(slug)

    if not page:
        raise HTTPException(status_code=404, detail=f"Page '{slug}' not found")

    templates = get_templates(request)
    context = get_network_context(request)
    context["request"] = request
    context["page"] = page

    return templates.TemplateResponse("page.html", context)
