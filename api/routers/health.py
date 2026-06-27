from fastapi import APIRouter
from pydantic import BaseModel

from api.database import check_connection


router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: str
    database: str
    version: str


@router.get("", response_model=HealthResponse)
def health_check() -> HealthResponse:
    db_ok = check_connection()
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        database="connected" if db_ok else "unreachable",
        version="0.1.0",
    )
