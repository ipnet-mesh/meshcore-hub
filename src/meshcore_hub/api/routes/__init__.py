"""API route handlers."""

from fastapi import APIRouter

from meshcore_hub.api.routes.nodes import router as nodes_router
from meshcore_hub.api.routes.node_tags import router as node_tags_router
from meshcore_hub.api.routes.messages import router as messages_router
from meshcore_hub.api.routes.advertisements import router as advertisements_router
from meshcore_hub.api.routes.trace_paths import router as trace_paths_router
from meshcore_hub.api.routes.telemetry import router as telemetry_router
from meshcore_hub.api.routes.dashboard import router as dashboard_router
from meshcore_hub.api.routes.user_profiles import router as user_profiles_router
from meshcore_hub.api.routes.adoptions import router as adoptions_router

api_router = APIRouter()

# Include all routers
api_router.include_router(nodes_router, prefix="/nodes", tags=["Nodes"])
api_router.include_router(node_tags_router, tags=["Node Tags"])
api_router.include_router(messages_router, prefix="/messages", tags=["Messages"])
api_router.include_router(
    advertisements_router, prefix="/advertisements", tags=["Advertisements"]
)
api_router.include_router(
    trace_paths_router, prefix="/trace-paths", tags=["Trace Paths"]
)
api_router.include_router(telemetry_router, prefix="/telemetry", tags=["Telemetry"])
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(user_profiles_router, prefix="/user", tags=["User"])
api_router.include_router(adoptions_router, prefix="/adoptions", tags=["Adoptions"])
