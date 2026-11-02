from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProjectMemberCreate(BaseModel):
    user_id: int = Field(gt=0)

    role: Literal["admin", "member", "viewer"] = "member"

    responsibility: str | None = Field(
        default=None,
        max_length=160
    )


class ProjectMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    user_id: int
    role: str
    responsibility: str | None
    membership_status: str
    joined_at: datetime


class ProjectMemberDetails(BaseModel):
    id: int
    project_id: int
    user_id: int
    full_name: str
    email: str
    role: str
    responsibility: str | None
    membership_status: str
    joined_at: datetime