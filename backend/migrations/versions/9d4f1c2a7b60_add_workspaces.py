
"""Add workspaces and workspace membership."""

from alembic import op
import sqlalchemy as sa


revision = "9d4f1c2a7b60"
down_revision = "bcf8037ab545"
branch_labels = None
depends_on = None


LEGACY_DESCRIPTION = (
    "Automatically created during workspace migration "
    "for existing RelayMap projects."
)


def upgrade():

    # 1. Create workspaces.
    op.create_table(
        "workspaces",

        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False
        ),

        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            ondelete="RESTRICT"
        ),

        sa.PrimaryKeyConstraint("id")
    )

    op.create_index(
        "ix_workspaces_created_by",
        "workspaces",
        ["created_by"]
    )

    # 2. Create workspace members.
    op.create_table(
        "workspace_members",

        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "role",
            sa.String(length=30),
            server_default="member",
            nullable=False
        ),
        sa.Column(
            "membership_status",
            sa.String(length=30),
            server_default="active",
            nullable=False
        ),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False
        ),

        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'member', 'viewer')",
            name="ck_workspace_member_role"
        ),

        sa.CheckConstraint(
            "membership_status IN ('active', 'pending', 'removed')",
            name="ck_workspace_membership_status"
        ),

        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE"
        ),

        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE"
        ),

        sa.PrimaryKeyConstraint("id"),

        sa.UniqueConstraint(
            "workspace_id",
            "user_id",
            name="uq_workspace_member"
        )
    )

    op.create_index(
        "ix_workspace_members_workspace_id",
        "workspace_members",
        ["workspace_id"]
    )

    op.create_index(
        "ix_workspace_members_user_id",
        "workspace_members",
        ["user_id"]
    )

    # 3. Add workspace_id to existing projects.
    op.add_column(
        "projects",
        sa.Column("workspace_id", sa.Integer(), nullable=True)
    )

    op.create_index(
        "ix_projects_workspace_id",
        "projects",
        ["workspace_id"]
    )

    op.create_foreign_key(
        "fk_projects_workspace_id_workspaces",
        "projects",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE"
    )

    # 4. Create one legacy workspace per existing project creator.
    op.execute(
        sa.text("""
            INSERT INTO workspaces (
                name,
                description,
                created_by
            )
            SELECT
                u.full_name || ' Workspace',
                :legacy_description,
                u.id
            FROM users u
            WHERE EXISTS (
                SELECT 1
                FROM projects p
                WHERE p.created_by = u.id
            )
        """).bindparams(
            legacy_description=LEGACY_DESCRIPTION
        )
    )

    # 5. Assign each existing project to its creator's legacy workspace.
    op.execute(
        sa.text("""
            UPDATE projects p
            SET workspace_id = w.id
            FROM workspaces w
            WHERE w.created_by = p.created_by
              AND w.description = :legacy_description
        """).bindparams(
            legacy_description=LEGACY_DESCRIPTION
        )
    )

    # 6. Add each legacy workspace creator as its owner.
    op.execute(
        sa.text("""
            INSERT INTO workspace_members (
                workspace_id,
                user_id,
                role,
                membership_status
            )
            SELECT
                w.id,
                w.created_by,
                'owner',
                'active'
            FROM workspaces w
            WHERE w.description = :legacy_description
            ON CONFLICT (workspace_id, user_id) DO NOTHING
        """).bindparams(
            legacy_description=LEGACY_DESCRIPTION
        )
    )

    # 7. Carry existing project members into their respective workspaces.
    # Existing project owner/admin roles are not elevated to workspace owner.
    op.execute(
        sa.text("""
            INSERT INTO workspace_members (
                workspace_id,
                user_id,
                role,
                membership_status
            )
            SELECT DISTINCT
                p.workspace_id,
                pm.user_id,
                CASE
                    WHEN pm.role = 'admin' THEN 'admin'
                    WHEN pm.role = 'viewer' THEN 'viewer'
                    ELSE 'member'
                END,
                CASE
                    WHEN pm.membership_status = 'departed'
                        THEN 'removed'
                    ELSE 'active'
                END
            FROM project_members pm
            JOIN projects p
              ON p.id = pm.project_id
            WHERE p.workspace_id IS NOT NULL
            ON CONFLICT (workspace_id, user_id) DO NOTHING
        """)
    )


def downgrade():

    op.drop_constraint(
        "fk_projects_workspace_id_workspaces",
        "projects",
        type_="foreignkey"
    )

    op.drop_index(
        "ix_projects_workspace_id",
        table_name="projects"
    )

    op.drop_column("projects", "workspace_id")

    op.drop_index(
        "ix_workspace_members_user_id",
        table_name="workspace_members"
    )

    op.drop_index(
        "ix_workspace_members_workspace_id",
        table_name="workspace_members"
    )

    op.drop_table("workspace_members")

    op.drop_index(
        "ix_workspaces_created_by",
        table_name="workspaces"
    )

    op.drop_table("workspaces")