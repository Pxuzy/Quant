from __future__ import annotations

from apps.api.core.fastapi_compat import apply_starlette_router_compat

apply_starlette_router_compat()

from fastapi import APIRouter

from apps.api.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "service": settings.app_name, "environment": settings.environment}
