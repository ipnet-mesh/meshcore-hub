"""Home page route."""

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from meshcore_hub.web.app import get_network_context, get_templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    """Render the home page."""
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
        "advertisements_24h": 0,
    }

    # Fetch activity data for chart
    activity = {"days": 7, "data": []}

    try:
        response = await request.app.state.http_client.get("/api/v1/dashboard/stats")
        if response.status_code == 200:
            stats = response.json()
    except Exception as e:
        logger.warning(f"Failed to fetch stats from API: {e}")
        context["api_error"] = str(e)

    try:
        response = await request.app.state.http_client.get(
            "/api/v1/dashboard/activity", params={"days": 7}
        )
        if response.status_code == 200:
            activity = response.json()
    except Exception as e:
        logger.warning(f"Failed to fetch activity from API: {e}")

    context["stats"] = stats
    # Pass activity data as JSON string for the chart
    context["activity_json"] = json.dumps(activity)

    return templates.TemplateResponse("home.html", context)
