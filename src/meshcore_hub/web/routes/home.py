"""Home page route."""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from meshcore_hub.web.app import get_network_context, get_templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    """Render the home page."""
    templates = get_templates(request)
    context = get_network_context(request)
    context["request"] = request

    return templates.TemplateResponse("home.html", context)
