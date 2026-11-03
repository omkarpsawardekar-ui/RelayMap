from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------
# GENERATE HANDOVER REQUEST
# ---------------------------------------------------------

class HandoverGenerateRequest(BaseModel):
    recipient_user_id: int | None = Field(
        default=None,
        gt=0,
    )


# ---------------------------------------------------------
# REVIEW HANDOVER REQUEST
# ---------------------------------------------------------

class HandoverReviewRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    review_notes: str | None = None


# ---------------------------------------------------------
# HANDOVER REPORT RESPONSE
# ---------------------------------------------------------

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