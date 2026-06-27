from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.auth import TokenData, get_current_user
from api.database import get_db
from api.file_validator import compute_file_hash, validate_upload_content
from ingestion.models import ParseStatus
from ingestion.service import ingest_file
from ingestion.validators.duplicates import get_ingestion_history


import tempfile
import os


router = APIRouter(prefix="/ingestion", tags=["ingestion"])

_ALLOWED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".csv", ".jpg", ".jpeg", ".png"}


class IngestionResponse(BaseModel):
    status: str
    source_file: str
    records_loaded: int
    warnings: list[str]
    errors: list[str]


class IngestionHistoryItem(BaseModel):
    run_id: str
    source_type: str
    source_file: str
    status: str
    started_at: str
    records_loaded: int | None
    records_failed: int | None


@router.post("/upload", response_model=IngestionResponse)
async def upload_file(
    file: UploadFile,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> IngestionResponse:
    content = await validate_upload_content(file)

    tmp_path: str | None = None
    try:
        suffix = _get_safe_suffix(file.filename or "")
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=suffix,
            prefix="condodata_",
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        result = ingest_file(
            file_path=tmp_path,
            condominio_id=current_user.condominio_id,
            db=db,
        )

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if result.status == ParseStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=result.errors[0] if result.errors else "Error procesando archivo",
        )

    return IngestionResponse(
        status=result.status.value,
        source_file=result.source_file,
        records_loaded=result.record_count,
        warnings=result.warnings,
        errors=result.errors,
    )


@router.get("/history", response_model=list[IngestionHistoryItem])
def get_history(
    limit: int = 20,
    current_user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[IngestionHistoryItem]:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit debe estar entre 1 y 100")

    rows = get_ingestion_history(db, current_user.condominio_id, limit)
    return [
        IngestionHistoryItem(
            run_id=str(r["run_id"]),
            source_type=str(r["source_type"]),
            source_file=str(r["source_file"] or ""),
            status=str(r["status"]),
            started_at=str(r["started_at"]),
            records_loaded=r.get("records_loaded"),  # type: ignore[arg-type]
            records_failed=r.get("records_failed"),  # type: ignore[arg-type]
        )
        for r in rows
    ]


def _get_safe_suffix(filename: str) -> str:
    from pathlib import Path

    ext = Path(filename).suffix.lower()
    return ext if ext in _ALLOWED_EXTENSIONS else ".bin"
