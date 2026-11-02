from typing import Literal

from pydantic import BaseModel, ConfigDict


class MemberStatusUpdate(BaseModel):
    membership_status: Literal[
        "active",
        "departing",
        "departed",
    ]


class MemberStatusResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    project_id: int
    user_id: int
    full_name: str
    role: str
    membership_status: str


class ContinuityGapItem(BaseModel):
    knowledge_item_id: int
    item_type: str
    title: str
    work_status: str

    assigned_member_user_id: int
    assigned_member_name: str
    membership_status: str

    document_id: int
    original_filename: str
    source_locator: str
    source_excerpt: str

    reason: str


class ContinuityGapReport(BaseModel):
    project_id: int
    departing_members_count: int
    potential_gaps_count: int
    gaps: list[ContinuityGapItem]