from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from api.auth import TokenData, create_access_token, get_current_user
from api.config import settings
from api.file_validator import (
    _check_magic_bytes,
    compute_file_hash,
    validate_upload,
)


class TestFileValidator:
    def _mock_file(self, filename: str) -> MagicMock:
        f = MagicMock()
        f.filename = filename
        return f

    def test_valid_pdf_filename(self) -> None:
        validate_upload(self._mock_file("estado_cuenta.pdf"))

    def test_valid_xlsx_filename(self) -> None:
        validate_upload(self._mock_file("cuotas_enero.xlsx"))

    def test_rejects_executable(self) -> None:
        with pytest.raises(HTTPException) as exc:
            validate_upload(self._mock_file("malware.exe"))
        assert exc.value.status_code == 415

    def test_rejects_path_traversal(self) -> None:
        with pytest.raises(HTTPException):
            validate_upload(self._mock_file("../../etc/passwd.pdf"))

    def test_rejects_double_extension(self) -> None:
        with pytest.raises(HTTPException):
            validate_upload(self._mock_file("archivo.pdf.exe"))

    def test_rejects_empty_filename(self) -> None:
        with pytest.raises(HTTPException):
            validate_upload(self._mock_file(""))

    def test_rejects_wrong_magic_bytes(self) -> None:
        with pytest.raises(HTTPException) as exc:
            _check_magic_bytes("archivo.pdf", b"PK\x03\x04notapdf")
        assert exc.value.status_code == 422

    def test_accepts_correct_pdf_magic(self) -> None:
        _check_magic_bytes("archivo.pdf", b"%PDF-1.4 content here")

    def test_hash_is_deterministic(self) -> None:
        content = b"same content"
        assert compute_file_hash(content) == compute_file_hash(content)

    def test_different_content_different_hash(self) -> None:
        assert compute_file_hash(b"content_a") != compute_file_hash(b"content_b")


class TestAuth:
    def test_create_and_decode_token(self) -> None:
        token = create_access_token(user_id="user1", condominio_id=42)
        assert isinstance(token, str)
        assert len(token) > 10

    def test_invalid_token_raises_401(self) -> None:
        fake = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials="not.a.real.token"
        )
        with pytest.raises(HTTPException) as exc:
            get_current_user(fake)
        assert exc.value.status_code == 401

    def test_token_contains_condominio_id(self) -> None:
        from jose import jwt

        token = create_access_token(user_id="user1", condominio_id=7)
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.algorithm]
        )
        assert payload["condominio_id"] == 7


class TestConfig:
    def test_secret_key_not_empty(self) -> None:
        assert len(settings.secret_key) >= 32

    def test_algorithm_is_hs256(self) -> None:
        assert settings.algorithm == "HS256"
