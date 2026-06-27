from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class SourceType(str, Enum):  # noqa: UP042
    BANK_PDF = "bank_pdf"
    BANK_EXCEL = "bank_excel"
    CUOTA_MANUAL = "cuota_manual"
    GASTO_PDF = "gasto_pdf"
    GASTO_EXCEL = "gasto_excel"
    GASTO_IMAGE = "gasto_image"


class ParseStatus(str, Enum):  # noqa: UP042
    OK = "ok"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass
class RawTransaction:
    source_file: str
    source_hash: str
    source_type: SourceType
    condominio_id: int
    raw_date: str
    raw_description: str
    raw_amount: str
    raw_reference: str = ""
    page_number: int = 0
    row_number: int = 0


@dataclass
class RawCuota:
    source_file: str
    source_hash: str
    source_type: SourceType
    condominio_id: int
    raw_unidad: str
    raw_propietario: str
    raw_periodo: str
    raw_monto: str
    raw_fecha_pago: str = ""
    raw_estado: str = ""


@dataclass
class RawGasto:
    source_file: str
    source_hash: str
    source_type: SourceType
    condominio_id: int
    raw_fecha: str
    raw_proveedor: str
    raw_concepto: str
    raw_monto: str
    raw_categoria: str = ""
    raw_comprobante: str = ""


@dataclass
class ParseResult:
    status: ParseStatus
    source_file: str
    source_type: SourceType
    records: list[RawTransaction | RawCuota | RawGasto] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def record_count(self) -> int:
        return len(self.records)

    @property
    def error_count(self) -> int:
        return len(self.errors)
