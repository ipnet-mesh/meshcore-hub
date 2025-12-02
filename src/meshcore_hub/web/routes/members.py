"""Members page route."""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from meshcore_hub.web.app import get_network_context, get_templates

logger = logging.getLogger(__name__)
router = APIRouter()


def load_members(members_file: str | None) -> list[dict]:
    """Load members from JSON file.

    Args:
        members_file: Path to members JSON file

    Returns:
        List of member dictionaries
    """
    if not members_file:
        return []

    try:
        path = Path(members_file)
        if path.exists():
            with open(path, "r") as f:
                data = json.load(f)
                # Handle both list and dict with "members" key
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict) and "members" in data:
                    return data["members"]
        else:
            logger.warning(f"Members file not found: {members_file}")
    except Exception as e:
        logger.error(f"Failed to load members file: {e}")

    return []


@router.get("/members", response_class=HTMLResponse)
async def members_page(request: Request) -> HTMLResponse:
    """Render the members page."""
    templates = get_templates(request)
    context = get_network_context(request)
    context["request"] = request

    # Load members from file
    members_file = request.app.state.members_file
    members = load_members(members_file)

    context["members"] = members

    return templates.TemplateResponse("members.html", context)
