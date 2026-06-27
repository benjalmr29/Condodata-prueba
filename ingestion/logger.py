import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.orm import Session


logger = structlog.get_logger()


class IngestionLogger:
    def __init__(self, db: Session, source_type: str, condominio_id: int) -> None:
        self._db = db
        self._source_type = source_type
        self._condominio_id = condominio_id
        self._run_id = str(uuid.uuid4())
        self._started_at = datetime.now(timezone.utc)
        self._log = logger.bind(run_id=self._run_id, source_type=source_type)

    def start(self, source_file: str) -> None:
        self._source_file = source_file
        self._log.info("ingestion_started", source_file=source_file)
        self._db.execute(
            _INSERT_LOG,
            {
                "run_id": self._run_id,
                "source_type": self._source_type,
                "source_file": source_file,
                "condominio_id": self._condominio_id,
            },
        )
        self._db.commit()

    def finish(self, records_read: int, records_loaded: int, records_failed: int) -> None:
        self._log.info(
            "ingestion_finished",
            records_read=records_read,
            records_loaded=records_loaded,
            records_failed=records_failed,
        )
        self._db.execute(
            _UPDATE_LOG_SUCCESS,
            {
                "run_id": self._run_id,
                "finished_at": datetime.now(timezone.utc),
                "records_read": records_read,
                "records_loaded": records_loaded,
                "records_failed": records_failed,
            },
        )
        self._db.commit()

    def fail(self, error: Exception) -> None:
        self._log.error("ingestion_failed", error=str(error))
        self._db.execute(
            _UPDATE_LOG_FAILURE,
            {
                "run_id": self._run_id,
                "finished_at": datetime.now(timezone.utc),
                "error_message": str(error),
            },
        )
        self._db.commit()

    @property
    def run_id(self) -> str:
        return self._run_id

    def bind(self, **kwargs: Any) -> "IngestionLogger":
        self._log = self._log.bind(**kwargs)
        return self


_INSERT_LOG = """
    INSERT INTO audit.ingestion_log
        (run_id, source_type, source_file, condominio_id, status)
    VALUES
        (:run_id, :source_type, :source_file, :condominio_id, 'running')
"""

_UPDATE_LOG_SUCCESS = """
    UPDATE audit.ingestion_log SET
        finished_at   = :finished_at,
        status        = 'success',
        records_read  = :records_read,
        records_loaded = :records_loaded,
        records_failed = :records_failed
    WHERE run_id = :run_id
"""

_UPDATE_LOG_FAILURE = """
    UPDATE audit.ingestion_log SET
        finished_at   = :finished_at,
        status        = 'failed',
        error_message = :error_message
    WHERE run_id = :run_id
"""
