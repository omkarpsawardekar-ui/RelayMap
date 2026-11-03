from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    CheckConstraint
)
from sqlalchemy.sql import func

from app.db.base import Base


class WorkspaceInvitation(Base):
    __tablename__ = "workspace_invitations"

    __table_args__ = (
        CheckConstraint(
            "role IN ('admin', 'member', 'viewer')",
            name="ck_workspace_invitation_role"
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')",
            name="ck_workspace_invitation_status"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    workspace_id = Column(
        Integer,
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    invited_email = Column(
        String(255),
        nullable=False,
        index=True
    )

    role = Column(
        String(30),
        nullable=False,
        default="member"
    )

    # Only a SHA-256 hash is stored, never the original invitation token.
    token_hash = Column(
        String(64),
        nullable=False,
        unique=True
    )

    invited_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False
    )

    accepted_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    status = Column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending"
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    expires_at = Column(
        DateTime(timezone=True),
        nullable=False
    )

    accepted_at = Column(
        DateTime(timezone=True),
        nullable=True
    )