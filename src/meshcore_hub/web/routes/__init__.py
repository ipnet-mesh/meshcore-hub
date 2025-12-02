"""Web routes for MeshCore Hub Dashboard."""

from fastapi import APIRouter

from meshcore_hub.web.routes.home import router as home_router
from meshcore_hub.web.routes.network import router as network_router
from meshcore_hub.web.routes.nodes import router as nodes_router
from meshcore_hub.web.routes.messages import router as messages_router
from meshcore_hub.web.routes.map import router as map_router
from meshcore_hub.web.routes.members import router as members_router

# Create main web router
web_router = APIRouter()

# Include all sub-routers
web_router.include_router(home_router)
web_router.include_router(network_router)
web_router.include_router(nodes_router)
web_router.include_router(messages_router)
web_router.include_router(map_router)
web_router.include_router(members_router)

__all__ = ["web_router"]
