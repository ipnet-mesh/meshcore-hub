"""Nodes page routes."""

import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from meshcore_hub.web.app import get_network_context, get_templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/nodes", response_class=HTMLResponse)
async def nodes_list(
    request: Request,
    search: str | None = Query(None, description="Search term"),
    adv_type: str | None = Query(None, description="Filter by node type"),
    member_id: str | None = Query(None, description="Filter by member"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
) -> HTMLResponse:
    """Render the nodes list page."""
    templates = get_templates(request)
    context = get_network_context(request)
    context["request"] = request

    # Calculate offset
    offset = (page - 1) * limit

    # Build query params
    params: dict[str, int | str] = {"limit": limit, "offset": offset}
    if search:
        params["search"] = search
    if adv_type:
        params["adv_type"] = adv_type
    if member_id:
        params["member_id"] = member_id

    # Fetch nodes from API
    nodes = []
    total = 0
    members = []

    try:
        # Fetch members for dropdown
        members_response = await request.app.state.http_client.get(
            "/api/v1/members", params={"limit": 100}
        )
        if members_response.status_code == 200:
            members = members_response.json().get("items", [])

        response = await request.app.state.http_client.get(
            "/api/v1/nodes", params=params
        )
        if response.status_code == 200:
            data = response.json()
            nodes = data.get("items", [])
            total = data.get("total", 0)
    except Exception as e:
        logger.warning(f"Failed to fetch nodes from API: {e}")
        context["api_error"] = str(e)

    # Calculate pagination
    total_pages = (total + limit - 1) // limit if total > 0 else 1

    context.update(
        {
            "nodes": nodes,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
            "search": search or "",
            "adv_type": adv_type or "",
            "member_id": member_id or "",
            "members": members,
        }
    )

    return templates.TemplateResponse("nodes.html", context)


@router.get("/nodes/{public_key}", response_class=HTMLResponse)
async def node_detail(request: Request, public_key: str) -> HTMLResponse:
    """Render the node detail page."""
    templates = get_templates(request)
    context = get_network_context(request)
    context["request"] = request

    node = None
    advertisements = []
    telemetry = []

    try:
        # Fetch node details
        response = await request.app.state.http_client.get(
            f"/api/v1/nodes/{public_key}"
        )
        if response.status_code == 200:
            node = response.json()

        # Fetch recent advertisements for this node
        response = await request.app.state.http_client.get(
            "/api/v1/advertisements", params={"public_key": public_key, "limit": 10}
        )
        if response.status_code == 200:
            advertisements = response.json().get("items", [])

        # Fetch recent telemetry for this node
        response = await request.app.state.http_client.get(
            "/api/v1/telemetry", params={"node_public_key": public_key, "limit": 10}
        )
        if response.status_code == 200:
            telemetry = response.json().get("items", [])

    except Exception as e:
        logger.warning(f"Failed to fetch node details from API: {e}")
        context["api_error"] = str(e)

    # Check if admin editing is available
    admin_enabled = getattr(request.app.state, "admin_enabled", False)
    auth_user = request.headers.get("X-Forwarded-User")

    context.update(
        {
            "node": node,
            "advertisements": advertisements,
            "telemetry": telemetry,
            "public_key": public_key,
            "admin_enabled": admin_enabled,
            "is_authenticated": bool(auth_user),
        }
    )

    return templates.TemplateResponse("node_detail.html", context)
