"""Schemas for semantic merchant classification and user-confirmed rules."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SemanticDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str = Field(min_length=1, max_length=100)
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1, max_length=500)


class ClassificationSuggestionResponse(BaseModel):
    id: str
    transaction_id: int
    normalized_merchant: str
    suggested_category: str
    confidence: float = Field(ge=0, le=1)
    evidence_refs: list[str]
    rationale_summary: str
    route: Literal["user_rule", "platform", "history", "model"]
    status: Literal["pending", "applied", "confirmed", "rejected"]
    provider: str | None = None
    model: str | None = None
    model_called: bool
    created_at: datetime
    resolved_at: datetime | None = None


class ClassificationSuggestionListResponse(BaseModel):
    items: list[ClassificationSuggestionResponse]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class ConfirmClassificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str | None = Field(default=None, min_length=1, max_length=100)
    save_rule: bool = True


class MerchantRuleResponse(BaseModel):
    id: str
    normalized_merchant: str
    display_merchant: str
    category: str
    source: str
    active: bool
    created_at: datetime
    updated_at: datetime


class MerchantRuleListResponse(BaseModel):
    items: list[MerchantRuleResponse]
    total: int = Field(ge=0)
