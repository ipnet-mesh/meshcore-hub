"""Advertisements page route."""

import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from meshcore_hub.web.app import get_network_context, get_templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/advertisements", response_class=HTMLResponse)
async def advertisements_list(
    request: Request,
    search: str | None = Query(None, description="Search term"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(50, ge=1, le=100, description="Items per page"),
) -> HTMLResponse:
    """Render the advertisements list page."""
    templates = get_templates(request)
    context = get_network_context(request)
    context["request"] = request

    # Calculate offset
    offset = (page - 1) * limit

    # Build query params
    params: dict[str, int | str] = {"limit": limit, "offset": offset}
    if search:
        params["search"] = search

    # Fetch advertisements from API
    advertisements = []
    total = 0

    try:
        response = await request.app.state.http_client.get(
            "/api/v1/advertisements", params=params
        )
        if response.status_code == 200:
            data = response.json()
            advertisements = data.get("items", [])
            total = data.get("total", 0)
    except Exception as e:
        logger.warning(f"Failed to fetch advertisements from API: {e}")
        context["api_error"] = str(e)

    # Calculate pagination
    total_pages = (total + limit - 1) // limit if total > 0 else 1

    context.update(
        {
            "advertisements": advertisements,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "search": search or "",
        }
    )

    return templates.TemplateResponse("advertisements.html", context)
