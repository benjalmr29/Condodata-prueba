from sqlalchemy import text
from sqlalchemy.orm import Session


def is_duplicate(
    db: Session,
    source_hash: str,
    condominio_id: int,
    table: str,
) -> bool:
    allowed_tables = {"raw.bank_transactions", "raw.cuotas", "raw.gastos"}
    if table not in allowed_tables:
        raise ValueError(f"Tabla no permitida: {table}")

    row = db.execute(
        text(
            f"SELECT 1 FROM {table} WHERE source_hash = :hash AND condominio_id = :cid LIMIT 1"
        ),  # noqa: S608
        {"hash": source_hash, "cid": condominio_id},
    ).fetchone()

    return row is not None


def get_ingestion_history(
    db: Session,
    condominio_id: int,
    limit: int = 50,
) -> list[dict[str, object]]:
    rows = db.execute(
        text("""
            SELECT run_id, source_type, source_file, status,
                   started_at, finished_at, records_loaded, records_failed
            FROM audit.ingestion_log
            WHERE condominio_id = :cid
            ORDER BY started_at DESC
            LIMIT :limit
        """),
        {"cid": condominio_id, "limit": min(limit, 200)},
    ).fetchall()

    return [dict(r._mapping) for r in rows]
