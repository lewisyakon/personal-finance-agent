from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ImportStatus = Literal["pending", "processing", "completed", "partial", "failed", "cancelled"]


class ImportCounts(BaseModel):
    total_rows: int = 0
    success_rows: int = 0
    duplicate_rows: int = 0
    skipped_rows: int = 0
    failed_rows: int = 0
    pending_confirmation_rows: int = 0


class BillImportResponse(ImportCounts):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    source: str
    format: str
    file_name: str
    file_sha256: str
    status: ImportStatus
    error_summary: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    raw_file_available: bool = False
    idempotent_reuse: bool = False


class ImportListResponse(BaseModel):
    items: list[BillImportResponse]
    total: int
    page: int
    page_size: int


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: str
    bill_import_id: str
    fingerprint: str
    platform: str
    occurred_at: datetime
    direction: str
    amount_minor: int = Field(ge=0)
    currency: str
    status: str
    merchant: str
    description: str
    payment_method: str
    platform_category: str
    category: str | None = None
    category_source: str | None = None
    category_confidence: int | None = None
    source_transaction_id: str | None = None
    source_row: int
    created_at: datetime
    updated_at: datetime


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]
    total: int
    page: int
    page_size: int


class CategoryUpdateRequest(BaseModel):
    category: str | None = Field(default=None, max_length=100)
    # ``category_name`` is accepted as a backwards-compatible client alias.
    category_name: str | None = Field(default=None, max_length=100)


class CategoryChangeResponse(BaseModel):
    transaction: TransactionResponse
    previous_category: str | None
    new_category: str | None
    source: str
