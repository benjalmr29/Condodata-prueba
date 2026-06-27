from unittest.mock import MagicMock, call

import pytest

from ingestion.logger import IngestionLogger


@pytest.fixture
def mock_db() -> MagicMock:
    db = MagicMock()
    db.execute = MagicMock()
    db.commit = MagicMock()
    return db


def test_logger_start_inserts_record(mock_db: MagicMock) -> None:
    log = IngestionLogger(mock_db, source_type="pdf", condominio_id=1)
    log.start("estado_cuenta.pdf")
    assert mock_db.execute.called
    assert mock_db.commit.called


def test_logger_finish_updates_record(mock_db: MagicMock) -> None:
    log = IngestionLogger(mock_db, source_type="pdf", condominio_id=1)
    log.start("estado_cuenta.pdf")
    mock_db.reset_mock()
    log.finish(records_read=50, records_loaded=48, records_failed=2)
    assert mock_db.execute.called
    assert mock_db.commit.called


def test_logger_fail_updates_status(mock_db: MagicMock) -> None:
    log = IngestionLogger(mock_db, source_type="pdf", condominio_id=1)
    log.start("estado_cuenta.pdf")
    mock_db.reset_mock()
    log.fail(ValueError("archivo corrupto"))
    assert mock_db.execute.called


def test_run_id_is_unique(mock_db: MagicMock) -> None:
    log1 = IngestionLogger(mock_db, source_type="pdf", condominio_id=1)
    log2 = IngestionLogger(mock_db, source_type="pdf", condominio_id=1)
    assert log1.run_id != log2.run_id
