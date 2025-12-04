"""Map page route."""

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from meshcore_hub.web.app import get_network_context, get_templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/map", response_class=HTMLResponse)
async def map_page(request: Request) -> HTMLResponse:
    """Render the map page."""
    templates = get_templates(request)
    context = get_network_context(request)
    context["request"] = request

    return templates.TemplateResponse("map.html", context)


@router.get("/map/data")
async def map_data(request: Request) -> JSONResponse:
    """Return node location data as JSON for the map.

    Includes role tag, member ownership info, and all data needed for filtering.
    """
    nodes_with_location: list[dict[str, Any]] = []
    members_list: list[dict[str, Any]] = []
    members_by_key: dict[str, dict[str, Any]] = {}
    error: str | None = None
    total_nodes = 0
    nodes_with_coords = 0

    try:
        # Fetch all members to build lookup by public_key
        members_response = await request.app.state.http_client.get(
            "/api/v1/members", params={"limit": 500}
        )
        if members_response.status_code == 200:
            members_data = members_response.json()
            for member in members_data.get("items", []):
                member_info = {
                    "id": member.get("id"),
                    "name": member.get("name"),
                    "callsign": member.get("callsign"),
                }
                members_list.append(member_info)
                if member.get("public_key"):
                    members_by_key[member["public_key"]] = member_info
        else:
            logger.warning(
                f"Failed to fetch members: status {members_response.status_code}"
            )

        # Fetch all nodes from API
        response = await request.app.state.http_client.get(
            "/api/v1/nodes", params={"limit": 500}
        )
        if response.status_code == 200:
            data = response.json()
            nodes = data.get("items", [])
            total_nodes = len(nodes)

            # Filter nodes with location tags
            for node in nodes:
                tags = node.get("tags", [])
                lat = None
                lon = None
                friendly_name = None
                role = None

                for tag in tags:
                    key = tag.get("key")
                    if key == "lat":
                        try:
                            lat = float(tag.get("value"))
                        except (ValueError, TypeError):
                            pass
                    elif key == "lon":
                        try:
                            lon = float(tag.get("value"))
                        except (ValueError, TypeError):
                            pass
                    elif key == "friendly_name":
                        friendly_name = tag.get("value")
                    elif key == "role":
                        role = tag.get("value")

                if lat is not None and lon is not None:
                    nodes_with_coords += 1
                    # Use friendly_name, then node name, then public key prefix
                    display_name = (
                        friendly_name
                        or node.get("name")
                        or node.get("public_key", "")[:12]
                    )
                    public_key = node.get("public_key")

                    # Find owner member if exists
                    owner = members_by_key.get(public_key)

                    nodes_with_location.append(
                        {
                            "public_key": public_key,
                            "name": display_name,
                            "adv_type": node.get("adv_type"),
                            "lat": lat,
                            "lon": lon,
                            "last_seen": node.get("last_seen"),
                            "role": role,
                            "is_infra": role == "infra",
                            "owner": owner,
                        }
                    )
        else:
            error = f"API returned status {response.status_code}"
            logger.warning(f"Failed to fetch nodes: {error}")

    except Exception as e:
        error = str(e)
        logger.warning(f"Failed to fetch nodes for map: {e}")

    logger.info(
        f"Map data: {total_nodes} total nodes, " f"{nodes_with_coords} with coordinates"
    )

    # Calculate center from nodes, or use default (0, 0)
    center_lat = 0.0
    center_lon = 0.0
    if nodes_with_location:
        center_lat = sum(n["lat"] for n in nodes_with_location) / len(
            nodes_with_location
        )
        center_lon = sum(n["lon"] for n in nodes_with_location) / len(
            nodes_with_location
        )

    return JSONResponse(
        {
            "nodes": nodes_with_location,
            "members": members_list,
            "center": {
                "lat": center_lat,
                "lon": center_lon,
            },
            "debug": {
                "total_nodes": total_nodes,
                "nodes_with_coords": nodes_with_coords,
                "error": error,
            },
        }
    )
