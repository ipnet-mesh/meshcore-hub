"""Admin page routes."""

import logging
from typing import Any, Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from httpx import Response

from meshcore_hub.web.app import get_network_context, get_templates


def _build_redirect_url(
    public_key: str,
    message: Optional[str] = None,
    error: Optional[str] = None,
) -> str:
    """Build a properly encoded redirect URL with optional message/error."""
    params: dict[str, str] = {"public_key": public_key}
    if message:
        params["message"] = message
    if error:
        params["error"] = error
    return f"/a/node-tags?{urlencode(params)}"


def _get_error_detail(response: Response) -> str:
    """Safely extract error detail from response JSON."""
    try:
        data: Any = response.json()
        detail: str = data.get("detail", "Unknown error")
        return detail
    except Exception:
        return "Unknown error"


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


def _is_authenticated(request: Request) -> bool:
    """Check if user is authenticated via OAuth2Proxy headers."""
    return bool(
        request.headers.get("X-Forwarded-User")
        or request.headers.get("X-Forwarded-Email")
    )


def _require_auth(request: Request) -> None:
    """Require authentication, raise 403 if not authenticated."""
    if not _is_authenticated(request):
        raise HTTPException(status_code=403, detail="Access denied")


@router.get("/", response_class=HTMLResponse)
async def admin_home(request: Request) -> HTMLResponse:
    """Render the admin page with OAuth2Proxy user info."""
    _check_admin_enabled(request)

    templates = get_templates(request)
    context = get_network_context(request)
    context["request"] = request
    context.update(_get_auth_context(request))

    # Check if user is authenticated
    if not _is_authenticated(request):
        return templates.TemplateResponse(
            "admin/access_denied.html", context, status_code=403
        )

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

    # Check if user is authenticated
    if not _is_authenticated(request):
        return templates.TemplateResponse(
            "admin/access_denied.html", context, status_code=403
        )

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
            # Sort nodes alphabetically by name (unnamed nodes at the end)
            nodes.sort(
                key=lambda n: (n.get("name") is None, (n.get("name") or "").lower())
            )
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
    _require_auth(request)

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
            redirect_url = _build_redirect_url(
                public_key, message=f"Tag '{key}' created successfully"
            )
        elif response.status_code == 409:
            redirect_url = _build_redirect_url(
                public_key, error=f"Tag '{key}' already exists"
            )
        elif response.status_code == 404:
            redirect_url = _build_redirect_url(public_key, error="Node not found")
        else:
            redirect_url = _build_redirect_url(
                public_key, error=_get_error_detail(response)
            )
    except Exception as e:
        logger.exception("Failed to create tag: %s", e)
        redirect_url = _build_redirect_url(public_key, error="Failed to create tag")

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
    _require_auth(request)

    try:
        response = await request.app.state.http_client.put(
            f"/api/v1/nodes/{public_key}/tags/{key}",
            json={
                "value": value or None,
                "value_type": value_type,
            },
        )
        if response.status_code == 200:
            redirect_url = _build_redirect_url(
                public_key, message=f"Tag '{key}' updated successfully"
            )
        elif response.status_code == 404:
            redirect_url = _build_redirect_url(
                public_key, error=f"Tag '{key}' not found"
            )
        else:
            redirect_url = _build_redirect_url(
                public_key, error=_get_error_detail(response)
            )
    except Exception as e:
        logger.exception("Failed to update tag: %s", e)
        redirect_url = _build_redirect_url(public_key, error="Failed to update tag")

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
    _require_auth(request)

    try:
        response = await request.app.state.http_client.put(
            f"/api/v1/nodes/{public_key}/tags/{key}/move",
            json={"new_public_key": new_public_key},
        )
        if response.status_code == 200:
            # Redirect to the destination node after successful move
            redirect_url = _build_redirect_url(
                new_public_key, message=f"Tag '{key}' moved successfully"
            )
        elif response.status_code == 404:
            # Stay on source node if not found
            redirect_url = _build_redirect_url(
                public_key, error=_get_error_detail(response)
            )
        elif response.status_code == 409:
            redirect_url = _build_redirect_url(
                public_key, error=f"Tag '{key}' already exists on destination node"
            )
        else:
            redirect_url = _build_redirect_url(
                public_key, error=_get_error_detail(response)
            )
    except Exception as e:
        logger.exception("Failed to move tag: %s", e)
        redirect_url = _build_redirect_url(public_key, error="Failed to move tag")

    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/node-tags/delete", response_class=RedirectResponse)
async def admin_delete_node_tag(
    request: Request,
    public_key: str = Form(...),
    key: str = Form(...),
) -> RedirectResponse:
    """Delete a node tag."""
    _check_admin_enabled(request)
    _require_auth(request)

    try:
        response = await request.app.state.http_client.delete(
            f"/api/v1/nodes/{public_key}/tags/{key}",
        )
        if response.status_code == 204:
            redirect_url = _build_redirect_url(
                public_key, message=f"Tag '{key}' deleted successfully"
            )
        elif response.status_code == 404:
            redirect_url = _build_redirect_url(
                public_key, error=f"Tag '{key}' not found"
            )
        else:
            redirect_url = _build_redirect_url(
                public_key, error=_get_error_detail(response)
            )
    except Exception as e:
        logger.exception("Failed to delete tag: %s", e)
        redirect_url = _build_redirect_url(public_key, error="Failed to delete tag")

    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/node-tags/copy-all", response_class=RedirectResponse)
async def admin_copy_all_tags(
    request: Request,
    public_key: str = Form(...),
    dest_public_key: str = Form(...),
) -> RedirectResponse:
    """Copy all tags from one node to another."""
    _check_admin_enabled(request)
    _require_auth(request)

    try:
        response = await request.app.state.http_client.post(
            f"/api/v1/nodes/{public_key}/tags/copy-to/{dest_public_key}",
        )
        if response.status_code == 200:
            data = response.json()
            copied = data.get("copied", 0)
            skipped = data.get("skipped", 0)
            if skipped > 0:
                message = f"Copied {copied} tag(s), skipped {skipped} existing"
            else:
                message = f"Copied {copied} tag(s) successfully"
            # Redirect to destination node to show copied tags
            redirect_url = _build_redirect_url(dest_public_key, message=message)
        elif response.status_code == 400:
            redirect_url = _build_redirect_url(
                public_key, error=_get_error_detail(response)
            )
        elif response.status_code == 404:
            redirect_url = _build_redirect_url(
                public_key, error=_get_error_detail(response)
            )
        else:
            redirect_url = _build_redirect_url(
                public_key, error=_get_error_detail(response)
            )
    except Exception as e:
        logger.exception("Failed to copy tags: %s", e)
        redirect_url = _build_redirect_url(public_key, error="Failed to copy tags")

    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/node-tags/delete-all", response_class=RedirectResponse)
async def admin_delete_all_tags(
    request: Request,
    public_key: str = Form(...),
) -> RedirectResponse:
    """Delete all tags from a node."""
    _check_admin_enabled(request)
    _require_auth(request)

    try:
        response = await request.app.state.http_client.delete(
            f"/api/v1/nodes/{public_key}/tags",
        )
        if response.status_code == 200:
            data = response.json()
            deleted = data.get("deleted", 0)
            message = f"Deleted {deleted} tag(s) successfully"
            redirect_url = _build_redirect_url(public_key, message=message)
        elif response.status_code == 404:
            redirect_url = _build_redirect_url(
                public_key, error=_get_error_detail(response)
            )
        else:
            redirect_url = _build_redirect_url(
                public_key, error=_get_error_detail(response)
            )
    except Exception as e:
        logger.exception("Failed to delete tags: %s", e)
        redirect_url = _build_redirect_url(public_key, error="Failed to delete tags")

    return RedirectResponse(url=redirect_url, status_code=303)


def _build_members_redirect_url(
    message: Optional[str] = None,
    error: Optional[str] = None,
) -> str:
    """Build a properly encoded redirect URL for members page with optional message/error."""
    params: dict[str, str] = {}
    if message:
        params["message"] = message
    if error:
        params["error"] = error
    if params:
        return f"/a/members?{urlencode(params)}"
    return "/a/members"


@router.get("/members", response_class=HTMLResponse)
async def admin_members(
    request: Request,
    message: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
) -> HTMLResponse:
    """Admin page for managing members."""
    _check_admin_enabled(request)

    templates = get_templates(request)
    context = get_network_context(request)
    context["request"] = request
    context.update(_get_auth_context(request))

    # Check if user is authenticated
    if not _is_authenticated(request):
        return templates.TemplateResponse(
            "admin/access_denied.html", context, status_code=403
        )

    # Flash messages from redirects
    context["message"] = message
    context["error"] = error

    # Fetch all members
    members = []
    try:
        response = await request.app.state.http_client.get(
            "/api/v1/members",
            params={"limit": 1000},
        )
        if response.status_code == 200:
            data = response.json()
            members = data.get("items", [])
            # Sort members alphabetically by name
            members.sort(key=lambda m: m.get("name", "").lower())
    except Exception as e:
        logger.exception("Failed to fetch members: %s", e)
        context["error"] = "Failed to fetch members"

    context["members"] = members

    return templates.TemplateResponse("admin/members.html", context)


@router.post("/members", response_class=RedirectResponse)
async def admin_create_member(
    request: Request,
    name: str = Form(...),
    member_id: str = Form(...),
    callsign: Optional[str] = Form(None),
    role: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    contact: Optional[str] = Form(None),
) -> RedirectResponse:
    """Create a new member."""
    _check_admin_enabled(request)
    _require_auth(request)

    try:
        # Build request payload
        payload = {
            "name": name,
            "member_id": member_id,
        }
        if callsign:
            payload["callsign"] = callsign
        if role:
            payload["role"] = role
        if description:
            payload["description"] = description
        if contact:
            payload["contact"] = contact

        response = await request.app.state.http_client.post(
            "/api/v1/members",
            json=payload,
        )
        if response.status_code == 201:
            redirect_url = _build_members_redirect_url(
                message=f"Member '{name}' created successfully"
            )
        elif response.status_code == 409:
            redirect_url = _build_members_redirect_url(
                error=f"Member ID '{member_id}' already exists"
            )
        else:
            redirect_url = _build_members_redirect_url(
                error=_get_error_detail(response)
            )
    except Exception as e:
        logger.exception("Failed to create member: %s", e)
        redirect_url = _build_members_redirect_url(error="Failed to create member")

    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/members/update", response_class=RedirectResponse)
async def admin_update_member(
    request: Request,
    id: str = Form(...),
    name: Optional[str] = Form(None),
    member_id: Optional[str] = Form(None),
    callsign: Optional[str] = Form(None),
    role: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    contact: Optional[str] = Form(None),
) -> RedirectResponse:
    """Update an existing member."""
    _check_admin_enabled(request)
    _require_auth(request)

    try:
        # Build update payload (only include non-None fields)
        payload: dict[str, str | None] = {}
        if name is not None:
            payload["name"] = name
        if member_id is not None:
            payload["member_id"] = member_id
        if callsign is not None:
            payload["callsign"] = callsign if callsign else None
        if role is not None:
            payload["role"] = role if role else None
        if description is not None:
            payload["description"] = description if description else None
        if contact is not None:
            payload["contact"] = contact if contact else None

        response = await request.app.state.http_client.put(
            f"/api/v1/members/{id}",
            json=payload,
        )
        if response.status_code == 200:
            redirect_url = _build_members_redirect_url(
                message="Member updated successfully"
            )
        elif response.status_code == 404:
            redirect_url = _build_members_redirect_url(error="Member not found")
        elif response.status_code == 409:
            redirect_url = _build_members_redirect_url(
                error=f"Member ID '{member_id}' already exists"
            )
        else:
            redirect_url = _build_members_redirect_url(
                error=_get_error_detail(response)
            )
    except Exception as e:
        logger.exception("Failed to update member: %s", e)
        redirect_url = _build_members_redirect_url(error="Failed to update member")

    return RedirectResponse(url=redirect_url, status_code=303)


@router.post("/members/delete", response_class=RedirectResponse)
async def admin_delete_member(
    request: Request,
    id: str = Form(...),
) -> RedirectResponse:
    """Delete a member."""
    _check_admin_enabled(request)
    _require_auth(request)

    try:
        response = await request.app.state.http_client.delete(
            f"/api/v1/members/{id}",
        )
        if response.status_code == 204:
            redirect_url = _build_members_redirect_url(
                message="Member deleted successfully"
            )
        elif response.status_code == 404:
            redirect_url = _build_members_redirect_url(error="Member not found")
        else:
            redirect_url = _build_members_redirect_url(
                error=_get_error_detail(response)
            )
    except Exception as e:
        logger.exception("Failed to delete member: %s", e)
        redirect_url = _build_members_redirect_url(error="Failed to delete member")

    return RedirectResponse(url=redirect_url, status_code=303)
