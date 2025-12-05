"""Members page route."""

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from meshcore_hub.web.app import get_network_context, get_templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/members", response_class=HTMLResponse)
async def members_page(request: Request) -> HTMLResponse:
    """Render the members page."""
    templates = get_templates(request)
    context = get_network_context(request)
    context["request"] = request

    # Fetch members from API
    members = []

    def node_sort_key(node: dict) -> int:
        """Sort nodes: repeater first, then chat, then others."""
        role = (node.get("node_role") or "").lower()
        if role == "repeater":
            return 0
        if role == "chat":
            return 1
        return 2

    try:
        response = await request.app.state.http_client.get(
            "/api/v1/members", params={"limit": 100}
        )
        if response.status_code == 200:
            data = response.json()
            members = data.get("items", [])
            # Sort nodes within each member (repeater first, then chat)
            for member in members:
                if member.get("nodes"):
                    member["nodes"] = sorted(member["nodes"], key=node_sort_key)
    except Exception as e:
        logger.warning(f"Failed to fetch members from API: {e}")
        context["api_error"] = str(e)

    context["members"] = members

    return templates.TemplateResponse("members.html", context)
