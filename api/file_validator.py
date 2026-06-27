import hashlib
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from api.config import settings


_MAGIC_BYTES: dict[str, bytes] = {
    ".pdf": b"%PDF",
    ".xlsx": b"PK\x03\x04",
    ".csv": b"",
}

_MAX_FILENAME_LENGTH = 100


def validate_upload(file: UploadFile) -> None:
    _check_filename(file.filename or "")
    _check_extension(file.filename or "")


async def validate_upload_content(file: UploadFile) -> bytes:
    validate_upload(file)
    content = await file.read()
    await file.seek(0)
    _check_size(content)
    _check_magic_bytes(file.filename or "", content)
    return content


def _check_filename(filename: str) -> None:
    if not filename:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nombre de archivo requerido")
    if len(filename) > _MAX_FILENAME_LENGTH:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Nombre de archivo demasiado largo"
        )
    forbidden_chars = set('/\\:*?"<>|')
    if any(c in forbidden_chars for c in filename):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Nombre de archivo contiene caracteres inválidos",
        )
    stem = Path(filename).stem
    if stem.startswith(".") or ".." in filename:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nombre de archivo inválido")


def _check_extension(filename: str) -> None:
    ext = Path(filename).suffix.lower()
    if ext not in settings.allowed_file_extensions:
        allowed = ", ".join(settings.allowed_file_extensions)
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Tipo de archivo no permitido. Permitidos: {allowed}",
        )


def _check_size(content: bytes) -> None:
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"Archivo excede el límite de {settings.max_upload_size_mb} MB",
        )


def _check_magic_bytes(filename: str, content: bytes) -> None:
    ext = Path(filename).suffix.lower()
    magic = _MAGIC_BYTES.get(ext, b"")
    if magic and not content.startswith(magic):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "El contenido del archivo no corresponde a su extensión",
        )


def compute_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
