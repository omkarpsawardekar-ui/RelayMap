"""Rename project_member to project_members

Revision ID: 698130c1062b
Revises: 402e86fcf105
"""

from typing import Sequence, Union

from alembic import op


# Revision identifiers
revision: str = "698130c1062b"
down_revision: Union[str, Sequence[str], None] = "402e86fcf105"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename the existing membership table."""
    op.rename_table("project_member", "project_members")


def downgrade() -> None:
    """Restore the original table name."""
    op.rename_table("project_members", "project_member")