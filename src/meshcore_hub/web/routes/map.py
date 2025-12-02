"""Map page route."""

import logging

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
    """Return node location data as JSON for the map."""
    nodes_with_location = []

    try:
        # Fetch all nodes from API
        response = await request.app.state.http_client.get(
            "/api/v1/nodes", params={"limit": 500}
        )
        if response.status_code == 200:
            data = response.json()
            nodes = data.get("items", [])

            # Filter nodes with location tags
            for node in nodes:
                tags = node.get("tags", [])
                lat = None
                lon = None
                for tag in tags:
                    if tag.get("key") == "lat":
                        try:
                            lat = float(tag.get("value"))
                        except (ValueError, TypeError):
                            pass
                    elif tag.get("key") == "lon":
                        try:
                            lon = float(tag.get("value"))
                        except (ValueError, TypeError):
                            pass

                if lat is not None and lon is not None:
                    nodes_with_location.append({
                        "public_key": node.get("public_key"),
                        "name": node.get("name") or node.get("public_key", "")[:12],
                        "adv_type": node.get("adv_type"),
                        "lat": lat,
                        "lon": lon,
                        "last_seen": node.get("last_seen"),
                    })

    except Exception as e:
        logger.warning(f"Failed to fetch nodes for map: {e}")

    # Get network center location
    network_location = request.app.state.network_location

    return JSONResponse({
        "nodes": nodes_with_location,
        "center": {
            "lat": network_location[0],
            "lon": network_location[1],
        },
    })
