"""
Parser de gastos — soporta PDF, Excel e imágenes (fotos de boletas).

La realidad del condominio es que los proveedores entregan:
- Facturas en PDF
- Registros en Excel del administrador
- Fotos de boletas desde el celular

Este módulo detecta el tipo y delega al parser correcto.
"""

from pathlib import Path

import structlog

from api.file_validator import compute_file_hash
from ingestion.models import ParseResult, ParseStatus, RawGasto, SourceType
from ingestion.sanitizers.text import (
    contains_sql_injection,
    sanitize_amount,
    sanitize_date,
    sanitize_text,
)


logger = structlog.get_logger()

_SUPPORTED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".csv", ".jpg", ".jpeg", ".png"}
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
_MAX_ROWS = 5_000


def parse_gastos(
    file_path: str,
    condominio_id: int,
) -> ParseResult:
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext not in _SUPPORTED_EXTENSIONS:
        return ParseResult(
            status=ParseStatus.FAILED,
            source_file=path.name,
            source_type=SourceType.GASTO_PDF,
            errors=[f"Formato no soportado: {ext}"],
        )

    if ext == ".pdf":
        return _parse_gasto_pdf(path, condominio_id)
    elif ext in {".xlsx", ".xls", ".csv"}:
        return _parse_gasto_excel(path, condominio_id)
    else:
        return _parse_gasto_image(path, condominio_id)


def _parse_gasto_pdf(path: Path, condominio_id: int) -> ParseResult:
    import pdfplumber

    result = ParseResult(
        status=ParseStatus.OK,
        source_file=path.name,
        source_type=SourceType.GASTO_PDF,
    )

    try:
        raw_bytes = path.read_bytes()
        if not raw_bytes.startswith(b"%PDF"):
            result.status = ParseStatus.FAILED
            result.errors.append("El archivo no es un PDF válido")
            return result

        source_hash = compute_file_hash(raw_bytes)

        with pdfplumber.open(str(path)) as pdf:
            full_text = "\n".join(page.extract_text() or "" for page in pdf.pages[:20])

        gasto = _extract_gasto_from_text(
            text=full_text,
            source_hash=source_hash,
            source_file=path.name,
            condominio_id=condominio_id,
        )
        if gasto:
            result.records.append(gasto)
        else:
            result.warnings.append(
                "No se pudo extraer información del PDF — requiere revisión manual"
            )

    except Exception as exc:
        result.status = ParseStatus.FAILED
        result.errors.append(f"Error procesando PDF: {type(exc).__name__}")
        logger.error("gasto_pdf_error", file=path.name, error=str(exc))

    return result


def _parse_gasto_excel(path: Path, condominio_id: int) -> ParseResult:
    import pandas as pd

    result = ParseResult(
        status=ParseStatus.OK,
        source_file=path.name,
        source_type=SourceType.GASTO_EXCEL,
    )

    try:
        raw_bytes = path.read_bytes()
        source_hash = compute_file_hash(raw_bytes)

        if path.suffix.lower() == ".csv":
            df = _read_csv_gastos(path)
        else:
            df = pd.read_excel(str(path), dtype=str, engine="openpyxl").fillna("")

        df.columns = pd.Index([sanitize_text(str(c)).lower() for c in df.columns])
        col_map = _map_gasto_columns(list(df.columns))

        if len(df) > _MAX_ROWS:
            result.warnings.append(f"{len(df)} filas — procesando primeras {_MAX_ROWS}")
            df = df.iloc[:_MAX_ROWS]

        for row_num, row in df.iterrows():
            _parse_gasto_row(
                row,
                int(str(row_num)),
                col_map,
                source_hash,
                path.name,
                condominio_id,
                result,
            )

    except Exception as exc:
        result.status = ParseStatus.FAILED
        result.errors.append(f"Error leyendo archivo: {type(exc).__name__}")
        logger.error("gasto_excel_error", file=path.name, error=str(exc))

    if result.errors and result.records:
        result.status = ParseStatus.PARTIAL

    return result


def _parse_gasto_image(path: Path, condominio_id: int) -> ParseResult:
    result = ParseResult(
        status=ParseStatus.OK,
        source_file=path.name,
        source_type=SourceType.GASTO_IMAGE,
    )

    try:
        raw_bytes = path.read_bytes()
        _validate_image_header(raw_bytes, path.suffix.lower(), result)
        if result.status == ParseStatus.FAILED:
            return result

        source_hash = compute_file_hash(raw_bytes)

        try:
            import pytesseract
            from PIL import Image
            import io

            image = Image.open(io.BytesIO(raw_bytes))
            text = pytesseract.image_to_string(image, lang="spa")
            gasto = _extract_gasto_from_text(
                text=text,
                source_hash=source_hash,
                source_file=path.name,
                condominio_id=condominio_id,
            )
            if gasto:
                result.records.append(gasto)
            else:
                result.warnings.append(
                    "OCR no pudo extraer datos — imagen guardada para revisión manual"
                )
        except ImportError:
            result.warnings.append(
                "pytesseract no disponible — imagen guardada sin OCR para revisión manual"
            )
            result.records.append(
                RawGasto(
                    source_file=path.name,
                    source_hash=source_hash,
                    source_type=SourceType.GASTO_IMAGE,
                    condominio_id=condominio_id,
                    raw_fecha="",
                    raw_proveedor="",
                    raw_concepto="imagen_pendiente_revision",
                    raw_monto="",
                    raw_comprobante=path.name,
                )
            )

    except Exception as exc:
        result.status = ParseStatus.FAILED
        result.errors.append(f"Error procesando imagen: {type(exc).__name__}")
        logger.error("gasto_image_error", file=path.name, error=str(exc))

    return result


def _validate_image_header(content: bytes, ext: str, result: ParseResult) -> None:
    magic: dict[str, bytes] = {
        ".jpg": b"\xff\xd8\xff",
        ".jpeg": b"\xff\xd8\xff",
        ".png": b"\x89PNG",
    }
    expected = magic.get(ext, b"")
    if expected and not content.startswith(expected):
        result.status = ParseStatus.FAILED
        result.errors.append(f"El archivo no es una imagen {ext.upper()} válida")


def _extract_gasto_from_text(
    text: str,
    source_hash: str,
    source_file: str,
    condominio_id: int,
) -> RawGasto | None:
    import re

    if not text.strip():
        return None

    date_match = re.search(
        r"\b(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}|\d{4}[/\-\.]\d{1,2}[/\-\.]\d{1,2})\b",
        text,
    )
    amount_match = re.search(
        r"\$?\s*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)\b",
        text,
    )

    raw_fecha = sanitize_date(date_match.group(1) if date_match else "")
    raw_monto = sanitize_amount(amount_match.group(1) if amount_match else "")

    if not raw_fecha and not raw_monto:
        return None

    first_line = sanitize_text(text.split("\n")[0])

    return RawGasto(
        source_file=source_file,
        source_hash=source_hash,
        source_type=SourceType.GASTO_PDF,
        condominio_id=condominio_id,
        raw_fecha=raw_fecha,
        raw_proveedor=first_line[:100],
        raw_concepto=sanitize_text(text[:200]),
        raw_monto=raw_monto,
        raw_comprobante=source_file,
    )


def _map_gasto_columns(columns: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    fecha_kw = {"fecha", "date", "f."}
    prov_kw = {"proveedor", "empresa", "razon", "razón", "nombre"}
    conc_kw = {"concepto", "descripcion", "descripción", "detalle", "glosa"}
    monto_kw = {"monto", "importe", "valor", "total", "amount"}
    cat_kw = {"categoria", "categoría", "tipo", "rubro"}

    for col in columns:
        lower = col.lower()
        if any(k in lower for k in fecha_kw) and "fecha" not in mapping:
            mapping["fecha"] = col
        elif any(k in lower for k in prov_kw) and "proveedor" not in mapping:
            mapping["proveedor"] = col
        elif any(k in lower for k in conc_kw) and "concepto" not in mapping:
            mapping["concepto"] = col
        elif any(k in lower for k in monto_kw) and "monto" not in mapping:
            mapping["monto"] = col
        elif any(k in lower for k in cat_kw) and "categoria" not in mapping:
            mapping["categoria"] = col

    return mapping


def _parse_gasto_row(
    row: object,
    row_num: int,
    col_map: dict[str, str],
    source_hash: str,
    source_file: str,
    condominio_id: int,
    result: ParseResult,
) -> None:
    try:
        import pandas as pd

        row_series = row if isinstance(row, pd.Series) else pd.Series(row)  # type: ignore[arg-type]

        fecha = sanitize_date(str(row_series.get(col_map.get("fecha", ""), "")))
        proveedor = sanitize_text(str(row_series.get(col_map.get("proveedor", ""), "")))
        concepto = sanitize_text(str(row_series.get(col_map.get("concepto", ""), "")))
        monto = sanitize_amount(str(row_series.get(col_map.get("monto", ""), "")))
        categoria = sanitize_text(str(row_series.get(col_map.get("categoria", ""), "")))

        if not monto and not proveedor:
            return

        if contains_sql_injection(proveedor) or contains_sql_injection(concepto):
            result.warnings.append(f"Fila {row_num}: contenido sospechoso — omitida")
            return

        result.records.append(
            RawGasto(
                source_file=source_file,
                source_hash=source_hash,
                source_type=SourceType.GASTO_EXCEL,
                condominio_id=condominio_id,
                raw_fecha=fecha,
                raw_proveedor=proveedor,
                raw_concepto=concepto,
                raw_monto=monto,
                raw_categoria=categoria,
            )
        )
    except Exception as exc:
        result.errors.append(f"Fila {row_num}: {type(exc).__name__}")


def _read_csv_gastos(path: Path) -> object:
    import pandas as pd

    for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            return pd.read_csv(
                str(path), dtype=str, encoding=encoding, sep=None, engine="python"
            ).fillna("")
        except UnicodeDecodeError:
            continue
    return pd.read_csv(str(path), dtype=str, encoding="latin-1").fillna("")
