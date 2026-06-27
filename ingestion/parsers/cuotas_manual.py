"""
Parser para cuotas ingresadas manualmente.

Como las cuotas están en papel, el administrador las transcribe a una
plantilla Excel o CSV estándar que generamos nosotros. Este parser
procesa esa plantilla con validaciones estrictas.
"""

from pathlib import Path

import pandas as pd
import structlog

from api.file_validator import compute_file_hash
from ingestion.models import ParseResult, ParseStatus, RawCuota, SourceType
from ingestion.sanitizers.text import (
    contains_sql_injection,
    sanitize_amount,
    sanitize_date,
    sanitize_text,
)


logger = structlog.get_logger()

TEMPLATE_COLUMNS = ["unidad", "propietario", "periodo", "monto", "fecha_pago", "estado"]
VALID_ESTADOS = {"pagado", "pendiente", "en mora", "exento", ""}
_MAX_ROWS = 5_000


def parse_cuotas_manual(
    file_path: str,
    condominio_id: int,
) -> ParseResult:
    path = Path(file_path)
    ext = path.suffix.lower()
    result = ParseResult(
        status=ParseStatus.OK,
        source_file=path.name,
        source_type=SourceType.CUOTA_MANUAL,
    )

    try:
        raw_bytes = path.read_bytes()
        source_hash = compute_file_hash(raw_bytes)

        if ext == ".csv":
            df = _read_csv(file_path, result)
        elif ext in {".xlsx", ".xls"}:
            df = _read_excel(file_path, result)
        else:
            result.status = ParseStatus.FAILED
            result.errors.append(f"Formato no soportado para cuotas: {ext}")
            return result

        if df is None or result.status == ParseStatus.FAILED:
            return result

        _process_dataframe(df, source_hash, path.name, condominio_id, result)

    except Exception as exc:
        result.status = ParseStatus.FAILED
        result.errors.append(f"Error inesperado: {type(exc).__name__}")
        logger.error("cuota_parse_error", file=path.name, error=str(exc))

    if result.errors and result.records:
        result.status = ParseStatus.PARTIAL

    logger.info(
        "cuotas_parsed",
        file=path.name,
        records=result.record_count,
        errors=result.error_count,
        status=result.status,
    )
    return result


def _read_csv(file_path: str, result: ParseResult) -> pd.DataFrame | None:
    for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            df = pd.read_csv(
                file_path,
                dtype=str,
                encoding=encoding,
                sep=None,
                engine="python",
            )
            df = df.fillna("")
            df.columns = pd.Index([c.strip().lower() for c in df.columns])
            return df
        except UnicodeDecodeError:
            continue
        except Exception as exc:
            result.errors.append(f"Error leyendo CSV: {type(exc).__name__}")
            result.status = ParseStatus.FAILED
            return None
    result.errors.append("No se pudo decodificar el CSV — prueba guardarlo como UTF-8")
    result.status = ParseStatus.FAILED
    return None


def _read_excel(file_path: str, result: ParseResult) -> pd.DataFrame | None:
    try:
        df = pd.read_excel(file_path, dtype=str, engine="openpyxl")
        df = df.fillna("")
        df.columns = pd.Index([sanitize_text(str(c)).lower() for c in df.columns])
        return df
    except Exception as exc:
        result.errors.append(f"Error leyendo Excel: {type(exc).__name__}")
        result.status = ParseStatus.FAILED
        return None


def _process_dataframe(
    df: pd.DataFrame,
    source_hash: str,
    source_file: str,
    condominio_id: int,
    result: ParseResult,
) -> None:
    missing = [c for c in TEMPLATE_COLUMNS if c not in df.columns]
    if missing:
        result.warnings.append(
            f"Columnas no encontradas: {missing} — se usarán valores vacíos"
        )

    if len(df) > _MAX_ROWS:
        result.warnings.append(f"{len(df)} filas — procesando primeras {_MAX_ROWS}")
        df = df.iloc[:_MAX_ROWS]

    for row_num, row in df.iterrows():
        _parse_row(row, int(str(row_num)), source_hash, source_file, condominio_id, result)


def _parse_row(
    row: pd.Series,  # type: ignore[type-arg]
    row_num: int,
    source_hash: str,
    source_file: str,
    condominio_id: int,
    result: ParseResult,
) -> None:
    try:
        unidad = sanitize_text(str(row.get("unidad", "")))
        propietario = sanitize_text(str(row.get("propietario", "")))
        periodo = sanitize_date(str(row.get("periodo", "")))
        monto = sanitize_amount(str(row.get("monto", "")))
        fecha_pago = sanitize_date(str(row.get("fecha_pago", "")))
        estado = sanitize_text(str(row.get("estado", ""))).lower()

        if not unidad and not monto:
            return

        if contains_sql_injection(propietario) or contains_sql_injection(unidad):
            result.warnings.append(f"Fila {row_num}: contenido sospechoso — omitida")
            return

        if estado and estado not in VALID_ESTADOS:
            result.warnings.append(
                f"Fila {row_num}: estado '{estado}' no reconocido — se guarda como recibido"
            )

        result.records.append(
            RawCuota(
                source_file=source_file,
                source_hash=source_hash,
                source_type=SourceType.CUOTA_MANUAL,
                condominio_id=condominio_id,
                raw_unidad=unidad,
                raw_propietario=propietario,
                raw_periodo=periodo,
                raw_monto=monto,
                raw_fecha_pago=fecha_pago,
                raw_estado=estado,
            )
        )

    except Exception as exc:
        result.errors.append(f"Fila {row_num}: {type(exc).__name__}")
