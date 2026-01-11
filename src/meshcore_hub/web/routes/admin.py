"""Admin page route."""

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from meshcore_hub.web.app import get_network_context, get_templates

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/a", tags=["admin"])


@router.get("/", response_class=HTMLResponse)
async def admin_home(request: Request) -> HTMLResponse:
    """Render the admin page with OAuth2Proxy user info."""
    # Check if admin interface is enabled
    if not getattr(request.app.state, "admin_enabled", False):
        raise HTTPException(status_code=404, detail="Not Found")

    templates = get_templates(request)
    context = get_network_context(request)
    context["request"] = request

    # Extract OAuth2Proxy headers
    context["auth_user"] = request.headers.get("X-Forwarded-User")
    context["auth_groups"] = request.headers.get("X-Forwarded-Groups")
    context["auth_email"] = request.headers.get("X-Forwarded-Email")
    context["auth_username"] = request.headers.get("X-Forwarded-Preferred-Username")

    return templates.TemplateResponse("admin.html", context)
