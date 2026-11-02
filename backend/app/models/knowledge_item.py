from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    CheckConstraint,
    UniqueConstraint,
)
from sqlalchemy.sql import func

from app.db.base import Base


class KnowledgeItem(Base):
    __tablename__ = "knowledge_items"

    __table_args__ = (
        CheckConstraint(
            "item_type IN ('task', 'decision', 'responsibility', "
            "'dependency', 'blocker', 'question')",
            name="ck_knowledge_item_type",
        ),
        CheckConstraint(
            "review_status IN ('pending', 'approved', "
            "'rejected', 'needs_clarification')",
            name="ck_knowledge_review_status",
        ),
        CheckConstraint(
            "work_status IN ('unknown', 'open', 'in_progress', "
            "'completed', 'blocked')",
            name="ck_knowledge_work_status",
        ),
        UniqueConstraint(
            "chunk_id",
            "item_type",
            "evidence_hash",
            name="uq_knowledge_evidence_item",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    chunk_id = Column(
        Integer,
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Classification of the extracted knowledge.
    item_type = Column(String(30), nullable=False)

    title = Column(String(250), nullable=False)

    description = Column(Text, nullable=False)

    # Exact supporting text copied from the source chunk.
    source_excerpt = Column(Text, nullable=False)

    evidence_hash = Column(String(64), nullable=False)

    # Raw mention from the document; not an automatically verified user.
    candidate_owner_mention = Column(String(160), nullable=True)

    # Only populated after a person verifies the assignment.
    assigned_to_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    work_status = Column(
        String(20),
        nullable=False,
        default="unknown",
        server_default="unknown",
    )

    # All extracted records require human review.
    review_status = Column(
        String(30),
        nullable=False,
        default="pending",
        server_default="pending",
    )

    reviewed_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    review_notes = Column(Text, nullable=True)

    extraction_method = Column(
        String(30),
        nullable=False,
        default="rule_based",
        server_default="rule_based",
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )