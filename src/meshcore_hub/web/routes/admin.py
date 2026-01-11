"""Admin page routes."""

import logging
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from meshcore_hub.web.app import get_network_context, get_templates

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/a", tags=["admin"])


def _check_admin_enabled(request: Request) -> None:
    """Check if admin interface is enabled, raise 404 if not."""
    if not getattr(request.app.state, "admin_enabled", False):
        raise HTTPException(status_code=404, detail="Not Found")


def _get_auth_context(request: Request) -> dict:
    """Extract OAuth2Proxy authentication headers."""
    return {
        "auth_user": request.headers.get("X-Forwarded-User"),
        "auth_groups": request.headers.get("X-Forwarded-Groups"),
        "auth_email": request.headers.get("X-Forwarded-Email"),
        "auth_username": request.headers.get("X-Forwarded-Preferred-Username"),
    }


@router.get("/", response_class=HTMLResponse)
async def admin_home(request: Request) -> HTMLResponse:
    """Render the admin page with OAuth2Proxy user info."""
    _check_admin_enabled(request)

    templates = get_templates(request)
    context = get_network_context(request)
    context["request"] = request
    context.update(_get_auth_context(request))

    return templates.TemplateResponse("admin/index.html", context)


@router.get("/node-tags", response_class=HTMLResponse)
async def admin_node_tags(
    request: Request,
    public_key: Optional[str] = Query(None),
    message: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
) -> HTMLResponse:
    """Admin page for managing node tags."""
    _check_admin_enabled(request)

    templates = get_templates(request)
    context = get_network_context(request)
    context["request"] = request
    context.update(_get_auth_context(request))

    # Flash messages from redirects
    context["message"] = message
    context["error"] = error

    # Fetch all nodes for dropdown
    nodes = []
    try:
        response = await request.app.state.http_client.get(
            "/api/v1/nodes",
            params={"limit": 100},
        )
        if response.status_code == 200:
            data = response.json()
            nodes = data.get("items", [])
    except Exception as e:
        logger.exception("Failed to fetch nodes: %s", e)
        context["error"] = "Failed to fetch nodes"

    context["nodes"] = nodes
    context["selected_public_key"] = public_key

    # Fetch tags for selected node
    tags = []
    selected_node = None
    if public_key:
        # Find the selected node in the list
        for node in nodes:
            if node.get("public_key") == public_key:
                selected_node = node
                break

        try:
            response = await request.app.state.http_client.get(
                f"/api/v1/nodes/{public_key}/tags",
            )
            if response.status_code == 200:
                tags = response.json()
            elif response.status_code == 404:
                context["error"] = "Node not found"
        except Exception as e:
            logger.exception("Failed to fetch tags: %s", e)
            context["error"] = "Failed to fetch tags"

    context["tags"] = tags
    context["selected_node"] = selected_node

    return templates.TemplateResponse("admin/node_tags.html", context)


@router.post("/node-tags", response_class=RedirectResponse)
async def admin_create_node_tag(
    request: Request,
    public_key: str = Form(...),
    key: str = Form(...),
    value: str = Form(""),
    value_type: str = Form("string"),
) -> RedirectResponse:
    """Create a new node tag."""
    _check_admin_enabled(request)

    redirect_url = f"/a/node-tags?public_key={public_key}"

    try:
        response = await request.app.state.http_client.post(
            f"/api/v1/nodes/{public_key}/tags",
            json={
                "key": key,
                "value": value or None,
                "value_type": value_type,
            },
        )
        if response.status_code == 201:
            redirect_url += f"&message=Tag '{key}' created successfully"
        elif response.status_code == 409:
            redirect_url += f"&error=Tag '{key}' already exists"
        elif response.status_code == 404:
            redirect_url += "&error=Node not found"
        else:
            detail = response.json().get("detail", "Unknown error")
            redirect_url += f"&error={detail}"
    except Exception as e:
        logger.exception("Failed to create tag: %s", e)
        redirect_url += "&error=Failed to create tag"

    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/node-tags/update", response_class=RedirectResponse)
async def admin_update_node_tag(
    request: Request,
    public_key: str = Form(...),
    key: str = Form(...),
    value: str = Form(""),
    value_type: str = Form("string"),
) -> RedirectResponse:
    """Update an existing node tag."""
    _check_admin_enabled(request)

    redirect_url = f"/a/node-tags?public_key={public_key}"

    try:
        response = await request.app.state.http_client.put(
            f"/api/v1/nodes/{public_key}/tags/{key}",
            json={
                "value": value or None,
                "value_type": value_type,
            },
        )
        if response.status_code == 200:
            redirect_url += f"&message=Tag '{key}' updated successfully"
        elif response.status_code == 404:
            redirect_url += f"&error=Tag '{key}' not found"
        else:
            detail = response.json().get("detail", "Unknown error")
            redirect_url += f"&error={detail}"
    except Exception as e:
        logger.exception("Failed to update tag: %s", e)
        redirect_url += "&error=Failed to update tag"

    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/node-tags/move", response_class=RedirectResponse)
async def admin_move_node_tag(
    request: Request,
    public_key: str = Form(...),
    key: str = Form(...),
    new_public_key: str = Form(...),
) -> RedirectResponse:
    """Move a node tag to a different node."""
    _check_admin_enabled(request)

    # Redirect to the destination node after move
    redirect_url = f"/a/node-tags?public_key={new_public_key}"

    try:
        response = await request.app.state.http_client.put(
            f"/api/v1/nodes/{public_key}/tags/{key}/move",
            json={"new_public_key": new_public_key},
        )
        if response.status_code == 200:
            redirect_url += f"&message=Tag '{key}' moved successfully"
        elif response.status_code == 404:
            # Stay on source node if not found
            redirect_url = f"/a/node-tags?public_key={public_key}"
            detail = response.json().get("detail", "Not found")
            redirect_url += f"&error={detail}"
        elif response.status_code == 409:
            redirect_url = f"/a/node-tags?public_key={public_key}"
            redirect_url += f"&error=Tag '{key}' already exists on destination node"
        else:
            redirect_url = f"/a/node-tags?public_key={public_key}"
            detail = response.json().get("detail", "Unknown error")
            redirect_url += f"&error={detail}"
    except Exception as e:
        logger.exception("Failed to move tag: %s", e)
        redirect_url = f"/a/node-tags?public_key={public_key}"
        redirect_url += "&error=Failed to move tag"

    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/node-tags/delete", response_class=RedirectResponse)
async def admin_delete_node_tag(
    request: Request,
    public_key: str = Form(...),
    key: str = Form(...),
) -> RedirectResponse:
    """Delete a node tag."""
    _check_admin_enabled(request)

    redirect_url = f"/a/node-tags?public_key={public_key}"

    try:
        response = await request.app.state.http_client.delete(
            f"/api/v1/nodes/{public_key}/tags/{key}",
        )
        if response.status_code == 204:
            redirect_url += f"&message=Tag '{key}' deleted successfully"
        elif response.status_code == 404:
            redirect_url += f"&error=Tag '{key}' not found"
        else:
            detail = response.json().get("detail", "Unknown error")
            redirect_url += f"&error={detail}"
    except Exception as e:
        logger.exception("Failed to delete tag: %s", e)
        redirect_url += "&error=Failed to delete tag"

    return RedirectResponse(url=redirect_url, status_code=303)
