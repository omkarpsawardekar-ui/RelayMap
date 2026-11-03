from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint
)
from sqlalchemy.sql import func

from app.db.base import Base


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "user_id",
            name="uq_workspace_member"
        ),
        CheckConstraint(
            "role IN ('owner', 'admin', 'member', 'viewer')",
            name="ck_workspace_member_role"
        ),
        CheckConstraint(
            "membership_status IN ('active', 'pending', 'removed')",
            name="ck_workspace_membership_status"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    workspace_id = Column(
        Integer,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    role = Column(
        String(30),
        default="member",
        nullable=False
    )

    membership_status = Column(
        String(30),
        default="active",
        nullable=False
    )

    joined_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )