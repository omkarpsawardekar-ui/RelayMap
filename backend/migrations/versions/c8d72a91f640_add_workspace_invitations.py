"""Add workspace invitations."""

from alembic import op
import sqlalchemy as sa


revision = "c8d72a91f640"
down_revision = "9d4f1c2a7b60"
branch_labels = None
depends_on = None


def upgrade():

    op.create_table(
        "workspace_invitations",

        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("invited_email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("invited_by_user_id", sa.Integer(), nullable=False),
        sa.Column("accepted_by_user_id", sa.Integer(), nullable=True),

        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False
        ),

        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False
        ),

        sa.Column(
            "accepted_at",
            sa.DateTime(timezone=True),
            nullable=True
        ),

        sa.CheckConstraint(
            "role IN ('admin', 'member', 'viewer')",
            name="ck_workspace_invitation_role"
        ),

        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')",
            name="ck_workspace_invitation_status"
        ),

        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE"
        ),

        sa.ForeignKeyConstraint(
            ["invited_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT"
        ),

        sa.ForeignKeyConstraint(
            ["accepted_by_user_id"],
            ["users.id"],
            ondelete="SET NULL"
        ),

        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "token_hash",
            name="uq_workspace_invitation_token_hash"
        )
    )

    op.create_index(
        "ix_workspace_invitations_workspace_id",
        "workspace_invitations",
        ["workspace_id"]
    )

    op.create_index(
        "ix_workspace_invitations_invited_email",
        "workspace_invitations",
        ["invited_email"]
    )


def downgrade():

    op.drop_index(
        "ix_workspace_invitations_invited_email",
        table_name="workspace_invitations"
    )

    op.drop_index(
        "ix_workspace_invitations_workspace_id",
        table_name="workspace_invitations"
    )

    op.drop_table("workspace_invitations")