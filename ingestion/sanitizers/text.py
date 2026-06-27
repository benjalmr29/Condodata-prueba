import re
import unicodedata


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SQL_KEYWORDS = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION|SCRIPT)\b",
    re.IGNORECASE,
)
_MAX_FIELD_LENGTH = 500


def sanitize_text(value: str | None) -> str:
    if value is None:
        return ""
    value = str(value)
    value = unicodedata.normalize("NFKC", value)
    value = _CONTROL_CHARS.sub("", value)
    value = value.strip()
    if len(value) > _MAX_FIELD_LENGTH:
        value = value[:_MAX_FIELD_LENGTH]
    return value


def sanitize_amount(value: str | None) -> str:
    if value is None:
        return ""
    value = str(value).strip()
    value = re.sub(r"[^\d.,\-]", "", value)
    value = value.replace(",", ".")
    parts = value.split(".")
    if len(parts) > 2:
        value = parts[0] + "." + "".join(parts[1:])
    if len(value) > 20:
        return ""
    return value


def sanitize_date(value: str | None) -> str:
    if value is None:
        return ""
    value = str(value).strip()
    value = re.sub(r"[^\d/\-\.]", "", value)
    if len(value) > 20:
        return ""
    return value


def contains_sql_injection(value: str) -> bool:
    return bool(_SQL_KEYWORDS.search(value))


def sanitize_filename(filename: str) -> str:
    filename = sanitize_text(filename)
    filename = re.sub(r"[^\w\s\-.]", "", filename)
    filename = re.sub(r"\.{2,}", ".", filename)
    return filename[:100]


def sanitize_row(row: dict[str, str | None]) -> dict[str, str]:
    return {k: sanitize_text(v) for k, v in row.items()}
