import io
import struct
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ingestion.models import ParseStatus, SourceType
from ingestion.parsers.cuotas_manual import parse_cuotas_manual
from ingestion.sanitizers.text import (
    contains_sql_injection,
    sanitize_amount,
    sanitize_date,
    sanitize_text,
)


class TestSanitizeText:
    def test_strips_whitespace(self) -> None:
        assert sanitize_text("  hola  ") == "hola"

    def test_removes_control_chars(self) -> None:
        assert "\x00" not in sanitize_text("texto\x00sucio")

    def test_truncates_long_strings(self) -> None:
        assert len(sanitize_text("a" * 1000)) == 500

    def test_handles_none(self) -> None:
        assert sanitize_text(None) == ""

    def test_normalizes_unicode(self) -> None:
        result = sanitize_text("café")
        assert isinstance(result, str)


class TestSanitizeAmount:
    def test_valid_amount(self) -> None:
        assert sanitize_amount("1.500,00") == "1.500.00"

    def test_strips_currency_symbol(self) -> None:
        assert "$" not in sanitize_amount("$150.000")

    def test_handles_none(self) -> None:
        assert sanitize_amount(None) == ""

    def test_rejects_too_long(self) -> None:
        assert sanitize_amount("1" * 25) == ""

    def test_allows_negative(self) -> None:
        result = sanitize_amount("-500")
        assert "-" in result


class TestSanitizeDate:
    def test_valid_date(self) -> None:
        assert sanitize_date("01/12/2024") == "01/12/2024"

    def test_strips_letters(self) -> None:
        result = sanitize_date("01-ENE-2024")
        assert "E" not in result

    def test_handles_none(self) -> None:
        assert sanitize_date(None) == ""

    def test_rejects_too_long(self) -> None:
        assert sanitize_date("1" * 25) == ""


class TestSQLInjection:
    def test_detects_select(self) -> None:
        assert contains_sql_injection("SELECT * FROM users") is True

    def test_detects_drop(self) -> None:
        assert contains_sql_injection("DROP TABLE cuotas") is True

    def test_clean_text_passes(self) -> None:
        assert contains_sql_injection("Pago cuota enero") is False

    def test_case_insensitive(self) -> None:
        assert contains_sql_injection("select * from raw") is True

    def test_partial_word_passes(self) -> None:
        assert contains_sql_injection("insertar datos") is False


class TestCuotaParser:
    def _make_csv(self, content: str, tmp_path: Path) -> str:
        f = tmp_path / "cuotas.csv"
        f.write_text(content, encoding="utf-8")
        return str(f)

    def test_parses_valid_csv(self, tmp_path: Path) -> None:
        csv = "unidad,propietario,periodo,monto,fecha_pago,estado\n101,Juan,2024-01,50000,2024-01-05,pagado"
        path = self._make_csv(csv, tmp_path)
        result = parse_cuotas_manual(path, condominio_id=1)
        assert result.status == ParseStatus.OK
        assert result.record_count == 1

    def test_skips_empty_rows(self, tmp_path: Path) -> None:
        csv = "unidad,propietario,periodo,monto,fecha_pago,estado\n,,,,,"
        path = self._make_csv(csv, tmp_path)
        result = parse_cuotas_manual(path, condominio_id=1)
        assert result.record_count == 0

    def test_rejects_sql_injection(self, tmp_path: Path) -> None:
        csv = "unidad,propietario,periodo,monto,fecha_pago,estado\n101,SELECT * FROM users,2024-01,50000,,"
        path = self._make_csv(csv, tmp_path)
        result = parse_cuotas_manual(path, condominio_id=1)
        assert result.record_count == 0
        assert len(result.warnings) > 0

    def test_fails_on_unsupported_format(self, tmp_path: Path) -> None:
        f = tmp_path / "cuotas.txt"
        f.write_text("datos")
        result = parse_cuotas_manual(str(f), condominio_id=1)
        assert result.status == ParseStatus.FAILED

    def test_condominio_id_in_records(self, tmp_path: Path) -> None:
        csv = "unidad,propietario,periodo,monto\n101,Ana,2024-01,50000"
        path = self._make_csv(csv, tmp_path)
        result = parse_cuotas_manual(path, condominio_id=99)
        assert result.records[0].condominio_id == 99

    def test_source_hash_present(self, tmp_path: Path) -> None:
        csv = "unidad,propietario,periodo,monto\n101,Ana,2024-01,50000"
        path = self._make_csv(csv, tmp_path)
        result = parse_cuotas_manual(path, condominio_id=1)
        assert result.records[0].source_hash != ""

    def test_handles_missing_columns_gracefully(self, tmp_path: Path) -> None:
        csv = "unidad,monto\n101,50000"
        path = self._make_csv(csv, tmp_path)
        result = parse_cuotas_manual(path, condominio_id=1)
        assert result.record_count == 1


class TestFileValidator:
    def test_rejects_fake_pdf(self, tmp_path: Path) -> None:
        from ingestion.sanitizers.text import sanitize_text
        from api.file_validator import _check_magic_bytes
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            _check_magic_bytes("test.pdf", b"not a pdf at all")

    def test_accepts_real_pdf_magic(self) -> None:
        from api.file_validator import _check_magic_bytes

        _check_magic_bytes("test.pdf", b"%PDF-1.4 real content")
