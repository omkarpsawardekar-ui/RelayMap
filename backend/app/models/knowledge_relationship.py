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


class KnowledgeRelationship(Base):
    __tablename__ = "knowledge_relationships"

    __table_args__ = (
        CheckConstraint(
            "relation_type IN ('depends_on', 'blocks', "
            "'related_to', 'supports', 'informs')",
            name="ck_knowledge_relationship_type",
        ),
        CheckConstraint(
            "review_status IN ('pending', 'approved', 'rejected')",
            name="ck_knowledge_relationship_review_status",
        ),
        CheckConstraint(
            "source_item_id <> target_item_id",
            name="ck_knowledge_relationship_distinct_items",
        ),
        UniqueConstraint(
            "source_item_id",
            "target_item_id",
            "relation_type",
            "evidence_hash",
            name="uq_knowledge_relationship_evidence",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Direction: source_item_id -> target_item_id
    source_item_id = Column(
        Integer,
        ForeignKey("knowledge_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    target_item_id = Column(
        Integer,
        ForeignKey("knowledge_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    relation_type = Column(
        String(30),
        nullable=False,
    )

    # Evidence supporting this particular relationship.
    evidence_chunk_id = Column(
        Integer,
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    evidence_excerpt = Column(
        Text,
        nullable=False,
    )

    evidence_hash = Column(
        String(64),
        nullable=False,
    )

    # New relationships are never automatically trusted.
    review_status = Column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )

    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
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
        Text,
        nullable=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )