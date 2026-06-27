from pathlib import Path

import pandas as pd
import structlog

from api.file_validator import compute_file_hash
from ingestion.models import ParseResult, ParseStatus, RawTransaction, SourceType
from ingestion.sanitizers.text import (
    contains_sql_injection,
    sanitize_amount,
    sanitize_date,
    sanitize_text,
)


logger = structlog.get_logger()

_MAX_ROWS = 10_000
_MAX_SHEETS = 10


def parse_bank_excel(
    file_path: str,
    condominio_id: int,
) -> ParseResult:
    path = Path(file_path)
    result = ParseResult(
        status=ParseStatus.OK,
        source_file=path.name,
        source_type=SourceType.BANK_EXCEL,
    )

    try:
        raw_bytes = path.read_bytes()
        source_hash = compute_file_hash(raw_bytes)
        _validate_excel_header(raw_bytes, result)
        if result.status == ParseStatus.FAILED:
            return result

        xl = pd.ExcelFile(file_path, engine="openpyxl")
        sheets = xl.sheet_names[:_MAX_SHEETS]

        for sheet_name in sheets:
            df = xl.parse(sheet_name, header=None, dtype=str)
            df = df.fillna("")
            _parse_sheet(
                df=df,
                sheet_name=str(sheet_name),
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
        result.errors.append(f"Error al leer Excel: {type(exc).__name__}")
        logger.error("excel_parse_error", file=path.name, error=str(exc))

    if result.errors and result.records:
        result.status = ParseStatus.PARTIAL

    logger.info(
        "excel_parsed",
        file=path.name,
        records=result.record_count,
        errors=result.error_count,
        status=result.status,
    )
    return result


def _validate_excel_header(content: bytes, result: ParseResult) -> None:
    if not content.startswith(b"PK\x03\x04"):
        result.status = ParseStatus.FAILED
        result.errors.append("El archivo no es un Excel válido (.xlsx)")


def _parse_sheet(
    df: pd.DataFrame,
    sheet_name: str,
    source_hash: str,
    source_file: str,
    condominio_id: int,
    result: ParseResult,
) -> None:
    header_row = _find_header_row(df)
    if header_row is None:
        return

    df.columns = pd.Index([sanitize_text(str(c)) for c in df.iloc[header_row]])
    df = df.iloc[header_row + 1:].reset_index(drop=True)
    df = df[df.apply(lambda r: any(str(v).strip() for v in r), axis=1)]

    if len(df) > _MAX_ROWS:
        result.warnings.append(
            f"Hoja '{sheet_name}': {len(df)} filas — procesando primeras {_MAX_ROWS}"
        )
        df = df.iloc[:_MAX_ROWS]

    col_map = _map_columns(list(df.columns))
    if not col_map:
        return

    for row_num, row in df.iterrows():
        _parse_row(
            row=row,
            col_map=col_map,
            sheet_name=sheet_name,
            row_num=int(str(row_num)),
            source_hash=source_hash,
            source_file=source_file,
            condominio_id=condominio_id,
            result=result,
        )


def _find_header_row(df: pd.DataFrame) -> int | None:
    date_keywords = {"fecha", "date", "f.operacion"}
    amount_keywords = {"monto", "importe", "cargo", "abono", "valor"}

    for i in range(min(20, len(df))):
        row_vals = [sanitize_text(str(v)).lower() for v in df.iloc[i]]
        has_date = any(any(k in v for k in date_keywords) for v in row_vals)
        has_amount = any(any(k in v for k in amount_keywords) for v in row_vals)
        if has_date and has_amount:
            return i
    return None


def _map_columns(columns: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    date_kw = {"fecha", "date", "f.operacion", "f.transaccion"}
    desc_kw = {"descripcion", "descripción", "glosa", "detalle", "concepto"}
    amount_kw = {"monto", "importe", "cargo", "valor", "amount"}
    ref_kw = {"referencia", "ref", "numero", "número", "folio"}

    for col in columns:
        lower = col.lower()
        if any(k in lower for k in date_kw) and "fecha" not in mapping:
            mapping["fecha"] = col
        elif any(k in lower for k in desc_kw) and "descripcion" not in mapping:
            mapping["descripcion"] = col
        elif any(k in lower for k in amount_kw) and "monto" not in mapping:
            mapping["monto"] = col
        elif any(k in lower for k in ref_kw) and "referencia" not in mapping:
            mapping["referencia"] = col

    return mapping


def _parse_row(
    row: pd.Series,  # type: ignore[type-arg]
    col_map: dict[str, str],
    sheet_name: str,
    row_num: int,
    source_hash: str,
    source_file: str,
    condominio_id: int,
    result: ParseResult,
) -> None:
    try:
        raw_date = sanitize_date(str(row.get(col_map.get("fecha", ""), "")))
        raw_desc = sanitize_text(str(row.get(col_map.get("descripcion", ""), "")))
        raw_amount = sanitize_amount(str(row.get(col_map.get("monto", ""), "")))

        if not raw_date and not raw_amount:
            return

        if contains_sql_injection(raw_desc):
            result.warnings.append(
                f"Hoja '{sheet_name}', fila {row_num}: descripción sospechosa — omitida"
            )
            return

        result.records.append(
            RawTransaction(
                source_file=source_file,
                source_hash=source_hash,
                source_type=SourceType.BANK_EXCEL,
                condominio_id=condominio_id,
                raw_date=raw_date,
                raw_description=raw_desc,
                raw_amount=raw_amount,
                raw_reference=sanitize_text(
                    str(row.get(col_map.get("referencia", ""), ""))
                ),
                page_number=0,
                row_number=row_num,
            )
        )

    except Exception as exc:
        result.errors.append(f"Hoja '{sheet_name}', fila {row_num}: {type(exc).__name__}")
