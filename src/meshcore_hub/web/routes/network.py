"""Network overview page route."""

import json
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
        "advertisements_24h": 0,
        "recent_advertisements": [],
        "channel_message_counts": {},
    }

    # Fetch activity data for charts (7 days)
    advert_activity = {"days": 7, "data": []}
    message_activity = {"days": 7, "data": []}
    node_count = {"days": 7, "data": []}

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
            advert_activity = response.json()
    except Exception as e:
        logger.warning(f"Failed to fetch advertisement activity from API: {e}")

    try:
        response = await request.app.state.http_client.get(
            "/api/v1/dashboard/message-activity", params={"days": 7}
        )
        if response.status_code == 200:
            message_activity = response.json()
    except Exception as e:
        logger.warning(f"Failed to fetch message activity from API: {e}")

    try:
        response = await request.app.state.http_client.get(
            "/api/v1/dashboard/node-count", params={"days": 7}
        )
        if response.status_code == 200:
            node_count = response.json()
    except Exception as e:
        logger.warning(f"Failed to fetch node count from API: {e}")

    context["stats"] = stats
    context["advert_activity_json"] = json.dumps(advert_activity)
    context["message_activity_json"] = json.dumps(message_activity)
    context["node_count_json"] = json.dumps(node_count)

    return templates.TemplateResponse("network.html", context)
