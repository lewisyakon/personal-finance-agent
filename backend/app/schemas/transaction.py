from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Direction = Literal["expense", "income", "transfer", "unknown"]
TransactionStatus = Literal["success", "failed", "refunded", "pending", "unknown"]


class TransactionRecord(BaseModel):
    """Parser output. Amounts are integer minor currency units, never floats."""

    model_config = ConfigDict(extra="forbid")

    platform: str = "wechat"
    occurred_at: datetime
    direction: Direction
    amount_minor: int = Field(ge=0)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    status: TransactionStatus = "unknown"
    merchant: str = ""
    description: str = ""
    payment_method: str = ""
    platform_category: str = ""
    source_transaction_id: str | None = None
    source_row: int = Field(ge=1)

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at 必须包含时区")
        return value

    @field_validator("amount_minor", mode="before")
    @classmethod
    def normalize_amount(cls, value: int | Decimal | str) -> int:
        if isinstance(value, int):
            return value
        return int(Decimal(str(value)))


class ParseRowError(BaseModel):
    row_number: int = Field(ge=1)
    message: str


class ParseReport(BaseModel):
    source: str
    format: str
    encoding: str
    total_rows: int = 0
    success_rows: int = 0
    error_rows: list[ParseRowError] = Field(default_factory=list)
    records: list[TransactionRecord] = Field(default_factory=list)
    header_row: int | None = None

