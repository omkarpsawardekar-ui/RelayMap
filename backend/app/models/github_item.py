from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Text,
    Boolean,
    DateTime,
    JSON,
    ForeignKey,
    UniqueConstraint,
    Index,
    func,
)

from app.db.base import Base


class GitHubItem(Base):
    __tablename__ = "github_items"

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "repository_full_name",
            "github_id",
            name="uq_github_item_project_repo_id",
        ),
        Index(
            "ix_github_items_project_id",
            "project_id",
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
    )

    # Repository information
    repository_full_name = Column(
        String(255),
        nullable=False,
    )

    repository_url = Column(
        String(500),
        nullable=True,
    )

    # Original GitHub identifiers
    github_id = Column(
        BigInteger,
        nullable=False,
    )

    item_number = Column(
        Integer,
        nullable=False,
    )

    item_type = Column(
        String(30),
        nullable=False,
    )

    # Issue / Pull request information
    title = Column(
        String(500),
        nullable=False,
    )

    body = Column(
        Text,
        nullable=True,
    )

    state = Column(
        String(30),
        nullable=True,
    )

    state_reason = Column(
        String(50),
        nullable=True,
    )

    draft = Column(
        Boolean,
        default=False,
        nullable=False,
    )

    merged = Column(
        Boolean,
        default=False,
        nullable=False,
    )

    url = Column(
        String(500),
        nullable=True,
    )

    # GitHub identity and ownership information
    author_login = Column(
        String(100),
        nullable=True,
    )

    assignees = Column(
        JSON,
        default=list,
        nullable=False,
    )

    labels = Column(
        JSON,
        default=list,
        nullable=False,
    )

    # Pull request branch information
    base_branch = Column(
        String(255),
        nullable=True,
    )

    head_branch = Column(
        String(255),
        nullable=True,
    )

    # Original GitHub timestamps
    github_created_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    github_updated_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    github_closed_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    github_merged_at = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # RelayMap synchronization timestamp
    synced_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )