from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class HandoverGenerateRequest(BaseModel):
    generated_by_user_id: int = Field(gt=0)
    recipient_user_id: int | None = Field(default=None, gt=0)


class HandoverReviewRequest(BaseModel):
    reviewer_user_id: int = Field(gt=0)
    decision: Literal["approved", "rejected"]
    review_notes: str | None = Field(default=None, max_length=5000)


class HandoverReportRead(BaseModel):
    id: int
    project_id: int
    recipient_user_id: int | None
    generated_by_user_id: int
    title: str
    report_data: dict[str, Any]
    status: str
    reviewed_by_user_id: int | None
    reviewed_at: datetime | None
    review_notes: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)