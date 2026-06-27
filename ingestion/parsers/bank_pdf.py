from pathlib import Path

import pdfplumber
import structlog

from api.file_validator import compute_file_hash
from ingestion.models import ParseResult, ParseStatus, RawTransaction, SourceType
from ingestion.sanitizers.text import (
    sanitize_amount,
    sanitize_date,
    sanitize_text,
    contains_sql_injection,
)


logger = structlog.get_logger()

_MIN_COLS = 2
_MAX_PAGES = 100
_MAX_ROWS_PER_PAGE = 500


def parse_bank_pdf(
    file_path: str,
    condominio_id: int,
) -> ParseResult:
    path = Path(file_path)
    result = ParseResult(
        status=ParseStatus.OK,
        source_file=path.name,
        source_type=SourceType.BANK_PDF,
    )

    try:
        raw_bytes = path.read_bytes()
        source_hash = compute_file_hash(raw_bytes)
        _validate_pdf_header(raw_bytes, result)
        if result.status == ParseStatus.FAILED:
            return result

        with pdfplumber.open(file_path) as pdf:
            if len(pdf.pages) > _MAX_PAGES:
                result.warnings.append(
                    f"PDF tiene {len(pdf.pages)} páginas — procesando primeras {_MAX_PAGES}"
                )

            for page_num, page in enumerate(pdf.pages[:_MAX_PAGES]):
                _parse_page(
                    page=page,
                    page_num=page_num,
                    source_hash=source_hash,
                    source_file=path.name,
                    condominio_id=condominio_id,
                    result=result,
                )

    except FileNotFoundError:
        result.status = ParseStatus.FAILED
        result.errors.append(f"Archivo no encontrado: {file_path}")
    except Exception as exc:
        result.status = ParseStatus.FAILED
        result.errors.append(f"Error inesperado al parsear PDF: {type(exc).__name__}")
        logger.error("pdf_parse_error", file=path.name, error=str(exc))

    if result.errors and result.records:
        result.status = ParseStatus.PARTIAL

    logger.info(
        "pdf_parsed",
        file=path.name,
        records=result.record_count,
        errors=result.error_count,
        status=result.status,
    )
    return result


def _validate_pdf_header(content: bytes, result: ParseResult) -> None:
    if not content.startswith(b"%PDF"):
        result.status = ParseStatus.FAILED
        result.errors.append("El archivo no es un PDF válido")


def _parse_page(
    page: object,
    page_num: int,
    source_hash: str,
    source_file: str,
    condominio_id: int,
    result: ParseResult,
) -> None:
    try:
        table = page.extract_table()  # type: ignore[attr-defined]
        if not table or len(table) < 2:
            return

        header = _detect_header(table[0])
        if header is None:
            result.warnings.append(f"Página {page_num + 1}: no se detectó tabla de transacciones")
            return

        rows = table[1:]
        if len(rows) > _MAX_ROWS_PER_PAGE:
            result.warnings.append(
                f"Página {page_num + 1}: {len(rows)} filas — procesando primeras {_MAX_ROWS_PER_PAGE}"
            )
            rows = rows[:_MAX_ROWS_PER_PAGE]

        for row_num, row in enumerate(rows):
            _parse_row(
                row=row,
                header=header,
                page_num=page_num,
                row_num=row_num,
                source_hash=source_hash,
                source_file=source_file,
                condominio_id=condominio_id,
                result=result,
            )

    except Exception as exc:
        result.errors.append(f"Página {page_num + 1}: error al extraer tabla — {type(exc).__name__}")


def _detect_header(row: list[str | None]) -> dict[str, int] | None:
    if not row:
        return None

    normalized = [sanitize_text(cell).lower() for cell in row]

    date_keywords = {"fecha", "date", "f.operacion", "f.transaccion"}
    desc_keywords = {"descripcion", "descripción", "glosa", "detalle", "concepto"}
    amount_keywords = {"monto", "importe", "cargo", "abono", "valor", "amount"}

    header: dict[str, int] = {}

    for i, cell in enumerate(normalized):
        if any(k in cell for k in date_keywords) and "fecha" not in header:
            header["fecha"] = i
        elif any(k in cell for k in desc_keywords) and "descripcion" not in header:
            header["descripcion"] = i
        elif any(k in cell for k in amount_keywords) and "monto" not in header:
            header["monto"] = i

    if len(header) < _MIN_COLS:
        return None

    return header


def _parse_row(
    row: list[str | None],
    header: dict[str, int],
    page_num: int,
    row_num: int,
    source_hash: str,
    source_file: str,
    condominio_id: int,
    result: ParseResult,
) -> None:
    try:
        raw_date = sanitize_date(_get_cell(row, header, "fecha"))
        raw_desc = sanitize_text(_get_cell(row, header, "descripcion"))
        raw_amount = sanitize_amount(_get_cell(row, header, "monto"))

        if not raw_date and not raw_amount:
            return

        if contains_sql_injection(raw_desc):
            result.warnings.append(
                f"Fila {row_num + 1}: descripción contiene contenido sospechoso — omitida"
            )
            return

        result.records.append(
            RawTransaction(
                source_file=source_file,
                source_hash=source_hash,
                source_type=SourceType.BANK_PDF,
                condominio_id=condominio_id,
                raw_date=raw_date,
                raw_description=raw_desc,
                raw_amount=raw_amount,
                raw_reference=sanitize_text(_get_cell(row, header, "referencia")),
                page_number=page_num,
                row_number=row_num,
            )
        )

    except Exception as exc:
        result.errors.append(
            f"Página {page_num + 1}, fila {row_num + 1}: {type(exc).__name__}"
        )


def _get_cell(row: list[str | None], header: dict[str, int], key: str) -> str:
    idx = header.get(key)
    if idx is None or idx >= len(row):
        return ""
    return str(row[idx]) if row[idx] is not None else ""
