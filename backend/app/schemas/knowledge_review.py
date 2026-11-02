from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeReviewUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_status: Literal[
        "approved",
        "rejected",
        "needs_clarification",
    ]

    reviewed_by_user_id: int

    work_status: Literal[
        "unknown",
        "open",
        "in_progress",
        "completed",
        "blocked",
    ] | None = None

    assigned_to_user_id: int | None = None

    review_notes: str | None = Field(
        default=None,
        max_length=5000,
    )


class KnowledgeReviewResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    item_type: str

    review_status: str
    work_status: str

    assigned_to_user_id: int | None
    reviewed_by_user_id: int | None
    reviewed_at: object | None

    review_notes: str | None