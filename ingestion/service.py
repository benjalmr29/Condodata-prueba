from pathlib import Path

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from ingestion.logger import IngestionLogger
from ingestion.models import (
    ParseResult,
    ParseStatus,
    RawCuota,
    RawGasto,
    RawTransaction,
    SourceType,
)
from ingestion.parsers.bank_excel import parse_bank_excel
from ingestion.parsers.bank_pdf import parse_bank_pdf
from ingestion.parsers.cuotas_manual import parse_cuotas_manual
from ingestion.parsers.gastos import parse_gastos
from ingestion.validators.duplicates import is_duplicate


logger = structlog.get_logger()

_SOURCE_TABLE: dict[SourceType, str] = {
    SourceType.BANK_PDF: "raw.bank_transactions",
    SourceType.BANK_EXCEL: "raw.bank_transactions",
    SourceType.CUOTA_MANUAL: "raw.cuotas",
    SourceType.GASTO_PDF: "raw.gastos",
    SourceType.GASTO_EXCEL: "raw.gastos",
    SourceType.GASTO_IMAGE: "raw.gastos",
}


def ingest_file(
    file_path: str,
    condominio_id: int,
    db: Session,
) -> ParseResult:
    path = Path(file_path)
    ing_logger = IngestionLogger(db, source_type=_detect_source_type(path), condominio_id=condominio_id)
    ing_logger.start(path.name)

    try:
        result = _parse(file_path, condominio_id)

        if result.status == ParseStatus.FAILED:
            ing_logger.fail(Exception("; ".join(result.errors)))
            return result

        table = _SOURCE_TABLE.get(result.source_type)
        if table is None:
            ing_logger.fail(Exception(f"Tipo de fuente sin tabla asignada: {result.source_type}"))
            return result

        if result.records:
            first_hash = getattr(result.records[0], "source_hash", "")
            if first_hash and is_duplicate(db, first_hash, condominio_id, table):
                result.warnings.append("Archivo ya fue procesado anteriormente — omitido")
                ing_logger.finish(
                    records_read=result.record_count,
                    records_loaded=0,
                    records_failed=0,
                )
                return result

        loaded, failed = _insert_records(result, db)
        ing_logger.finish(
            records_read=result.record_count,
            records_loaded=loaded,
            records_failed=failed,
        )

    except Exception as exc:
        ing_logger.fail(exc)
        result = ParseResult(
            status=ParseStatus.FAILED,
            source_file=path.name,
            source_type=SourceType.BANK_PDF,
            errors=[str(exc)],
        )

    return result


def _parse(file_path: str, condominio_id: int) -> ParseResult:
    path = Path(file_path)
    ext = path.suffix.lower()
    name = path.name.lower()

    if ext == ".pdf":
        if any(k in name for k in ("gasto", "factura", "boleta", "proveedor")):
            return parse_gastos(file_path, condominio_id)
        return parse_bank_pdf(file_path, condominio_id)

    if ext in {".xlsx", ".xls"}:
        if any(k in name for k in ("cuota", "residente", "propietario")):
            return parse_cuotas_manual(file_path, condominio_id)
        if any(k in name for k in ("gasto", "egreso", "proveedor")):
            return parse_gastos(file_path, condominio_id)
        return parse_bank_excel(file_path, condominio_id)

    if ext == ".csv":
        if any(k in name for k in ("cuota", "residente")):
            return parse_cuotas_manual(file_path, condominio_id)
        return parse_gastos(file_path, condominio_id)

    if ext in {".jpg", ".jpeg", ".png"}:
        return parse_gastos(file_path, condominio_id)

    return ParseResult(
        status=ParseStatus.FAILED,
        source_file=path.name,
        source_type=SourceType.BANK_PDF,
        errors=[f"Extensión no soportada: {ext}"],
    )


def _insert_records(result: ParseResult, db: Session) -> tuple[int, int]:
    loaded = 0
    failed = 0

    for record in result.records:
        try:
            if isinstance(record, RawTransaction):
                db.execute(text(_INSERT_TRANSACTION), _transaction_params(record))
            elif isinstance(record, RawCuota):
                db.execute(text(_INSERT_CUOTA), _cuota_params(record))
            elif isinstance(record, RawGasto):
                db.execute(text(_INSERT_GASTO), _gasto_params(record))
            loaded += 1
        except Exception as exc:
            failed += 1
            logger.warning("record_insert_failed", error=str(exc))

    db.commit()
    return loaded, failed


def _detect_source_type(path: Path) -> str:
    ext = path.suffix.lower()
    name = path.name.lower()
    if ext == ".pdf":
        return "bank_pdf" if not any(k in name for k in ("gasto", "factura")) else "gasto_pdf"
    if ext in {".xlsx", ".xls"}:
        return "bank_excel"
    if ext in {".jpg", ".jpeg", ".png"}:
        return "gasto_image"
    return "unknown"


def _transaction_params(r: RawTransaction) -> dict[str, object]:
    return {
        "source_file": r.source_file,
        "source_hash": r.source_hash,
        "raw_date": r.raw_date,
        "raw_description": r.raw_description,
        "raw_amount": r.raw_amount,
        "raw_reference": r.raw_reference,
        "page_number": r.page_number,
        "row_number": r.row_number,
        "condominio_id": r.condominio_id,
    }


def _cuota_params(r: RawCuota) -> dict[str, object]:
    return {
        "source_file": r.source_file,
        "source_hash": r.source_hash,
        "raw_unidad": r.raw_unidad,
        "raw_propietario": r.raw_propietario,
        "raw_periodo": r.raw_periodo,
        "raw_monto": r.raw_monto,
        "raw_fecha_pago": r.raw_fecha_pago,
        "raw_estado": r.raw_estado,
        "condominio_id": r.condominio_id,
    }


def _gasto_params(r: RawGasto) -> dict[str, object]:
    return {
        "source_file": r.source_file,
        "source_hash": r.source_hash,
        "raw_fecha": r.raw_fecha,
        "raw_proveedor": r.raw_proveedor,
        "raw_concepto": r.raw_concepto,
        "raw_monto": r.raw_monto,
        "raw_categoria": r.raw_categoria,
        "raw_comprobante": r.raw_comprobante,
        "condominio_id": r.condominio_id,
    }


_INSERT_TRANSACTION = """
    INSERT INTO raw.bank_transactions
        (source_file, source_hash, raw_date, raw_description, raw_amount,
         raw_reference, page_number, row_number, condominio_id)
    VALUES
        (:source_file, :source_hash, :raw_date, :raw_description, :raw_amount,
         :raw_reference, :page_number, :row_number, :condominio_id)
    ON CONFLICT DO NOTHING
"""

_INSERT_CUOTA = """
    INSERT INTO raw.cuotas
        (source_file, source_hash, raw_unidad, raw_propietario, raw_periodo,
         raw_monto, raw_fecha_pago, raw_estado, condominio_id)
    VALUES
        (:source_file, :source_hash, :raw_unidad, :raw_propietario, :raw_periodo,
         :raw_monto, :raw_fecha_pago, :raw_estado, :condominio_id)
    ON CONFLICT DO NOTHING
"""

_INSERT_GASTO = """
    INSERT INTO raw.gastos
        (source_file, source_hash, raw_fecha, raw_proveedor, raw_concepto,
         raw_monto, raw_categoria, raw_comprobante, condominio_id)
    VALUES
        (:source_file, :source_hash, :raw_fecha, :raw_proveedor, :raw_concepto,
         :raw_monto, :raw_categoria, :raw_comprobante, :condominio_id)
    ON CONFLICT DO NOTHING
"""
