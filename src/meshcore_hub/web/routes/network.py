"""Network overview page route."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from meshcore_hub.web.app import get_network_context, get_templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/network", response_class=HTMLResponse)
async def network_overview(request: Request) -> HTMLResponse:
    """Render the network overview page."""
    templates = get_templates(request)
    context = get_network_context(request)
    context["request"] = request

    # Fetch stats from API
    stats = {
        "total_nodes": 0,
        "active_nodes": 0,
        "total_messages": 0,
        "messages_today": 0,
        "total_advertisements": 0,
        "channel_message_counts": {},
    }

    try:
        response = await request.app.state.http_client.get("/api/v1/dashboard/stats")
        if response.status_code == 200:
            stats = response.json()
    except Exception as e:
        logger.warning(f"Failed to fetch stats from API: {e}")
        context["api_error"] = str(e)

    context["stats"] = stats

    return templates.TemplateResponse("network.html", context)
