"""
Analytics Routes
================
Prefix: /api/v1

Endpoints:
  GET /analytics/summary → aggregate analytics across all meetings
"""

import logging

from fastapi import APIRouter, Depends

from auth import get_current_user
from database.mongo import get_analytics_summary as mongo_analytics
from modules.cache import TTLCache

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1",
    tags=["Analytics"],
)

_cache = TTLCache(ttl=60, name="analytics_routes")


@router.get("/analytics/summary")
def get_analytics_summary(current_user: dict = Depends(get_current_user)):
    """Aggregate analytics with TTL cache — reads from MongoDB."""
    cached = _cache.get("analytics")
    if cached is not None:
        return cached

    result = mongo_analytics()
    _cache.set("analytics", result)
    return result
