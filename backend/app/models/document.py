from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    BigInteger,
    DateTime,
    ForeignKey,
    CheckConstraint,
)
from sqlalchemy.sql import func

from app.db.base import Base


class Document(Base):
    __tablename__ = "documents"

    __table_args__ = (
        CheckConstraint(
            "extraction_status IN ('pending', 'processed', 'failed')",
            name="ck_document_extraction_status",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    original_filename = Column(
        String(255),
        nullable=False,
    )

    stored_filename = Column(
        String(100),
        nullable=False,
        unique=True,
    )

    file_type = Column(
        String(10),
        nullable=False,
    )

    mime_type = Column(
        String(150),
        nullable=True,
    )

    file_path = Column(
        Text,
        nullable=False,
    )

    size_bytes = Column(
        BigInteger,
        nullable=False,
    )

    sha256 = Column(
        String(64),
        nullable=False,
    )

    extraction_status = Column(
        String(20),
        nullable=False,
        default="pending",
    )

    extracted_text = Column(
        Text,
        nullable=True,
    )

    uploaded_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )