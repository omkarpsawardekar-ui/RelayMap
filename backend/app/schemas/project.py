from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str | None = None

    # Optional temporarily for compatibility with the existing frontend.
    # The backend chooses the user's only available owner/admin workspace
    # when this field is omitted.
    workspace_id: int | None = Field(default=None, gt=0)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: int
    name: str
    description: str | None
    status: str
    created_by: int
    created_at: datetime
    updated_at: datetime