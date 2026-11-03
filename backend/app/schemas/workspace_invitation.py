from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class WorkspaceInvitationCreate(BaseModel):
    invited_email: str = Field(min_length=5, max_length=255)

    role: Literal["admin", "member", "viewer"] = "member"


class WorkspaceInvitationCreated(BaseModel):
    id: int
    invited_email: str
    role: str
    invite_url: str
    status: str
    expires_at: datetime


class WorkspaceInvitationRead(BaseModel):
    id: int
    invited_email: str
    role: str
    status: str
    created_at: datetime
    expires_at: datetime


class WorkspaceInvitationAccept(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class WorkspaceInvitationAcceptResponse(BaseModel):
    message: str
    workspace_id: int
    workspace_name: str
    role: str

class WorkspaceInvitationInboxItem(BaseModel):
    id: int
    workspace_id: int
    workspace_name: str
    invited_email: str
    role: str
    status: str
    created_at: datetime
    expires_at: datetime