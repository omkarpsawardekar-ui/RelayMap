"""Safely ensure the project_members table exists.

Revision ID: 698130c1062b
Revises: 402e86fcf105
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "698130c1062b"
down_revision: Union[str, Sequence[str], None] = "402e86fcf105"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Ensure the expected project membership table exists."""

    connection = op.get_bind()
    inspector = sa.inspect(connection)

    tables = set(inspector.get_table_names())

    has_singular = "project_member" in tables
    has_plural = "project_members" in tables

    if has_singular and has_plural:
        raise RuntimeError(
            "Both project_member and project_members exist. "
            "Manual database inspection is required."
        )

    if has_singular:
        op.rename_table(
            "project_member",
            "project_members",
        )

    elif has_plural:
        # The initial migration already created the correct table.
        pass

    else:
        raise RuntimeError(
            "Neither project_member nor project_members exists."
        )


def downgrade() -> None:
    """Keep the project_members table created by the initial migration."""

    pass