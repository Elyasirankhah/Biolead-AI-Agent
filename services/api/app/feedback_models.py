from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


FeedbackLabel = Literal["wrong_direction", "irrelevant", "important"]


class FeedbackCreate(BaseModel):
    disease: str = Field(min_length=2, max_length=120)
    gene: str = Field(min_length=1, max_length=40)
    evidence_id: str = Field(min_length=1, max_length=120)
    label: FeedbackLabel
    note: str | None = Field(default=None, max_length=400)
    run_id: str | None = None


class FeedbackRecord(BaseModel):
    feedback_id: str
    disease: str
    gene: str
    evidence_id: str
    label: FeedbackLabel
    note: str | None = None
    run_id: str | None = None
    user_id: str | None = None
    user_email: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FeedbackApplySummary(BaseModel):
    applied: int = 0
    irrelevant: int = 0
    wrong_direction: int = 0
    important: int = 0
    evidence_ids: list[str] = Field(default_factory=list)
