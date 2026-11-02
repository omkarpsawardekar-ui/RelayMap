from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    ForeignKey,
    CheckConstraint,
    JSON,
)
from sqlalchemy.sql import func

from app.db.base import Base


class HandoverReport(Base):
    __tablename__ = "handover_reports"

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'approved', 'rejected')",
            name="ck_handover_report_status",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The intended successor receiving this handover.
    recipient_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Person who generated the report.
    generated_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    title = Column(
        String(200),
        nullable=False,
    )

    # Immutable snapshot of project knowledge and its evidence.
    report_data = Column(
        JSON,
        nullable=False,
    )

    # Every new report starts as a draft.
    status = Column(
        String(20),
        nullable=False,
        default="draft",
        server_default="draft",
    )

    reviewed_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    reviewed_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    review_notes = Column(
        String,
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )