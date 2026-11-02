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


class ProjectMember(Base):

    __tablename__ = "project_members"

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "user_id",
            name="uq_project_member"
        ),
        CheckConstraint(
            "role IN ('owner', 'admin', 'member', 'viewer')",
            name="ck_project_member_role"
        ),
        CheckConstraint(
            "membership_status IN ('active', 'departing', 'departed')",
            name="ck_membership_status"
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False
    )

    role = Column(
        String(30),
        default="member",
        nullable=False
    )

    responsibility = Column(
        String(160),
        nullable=True
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