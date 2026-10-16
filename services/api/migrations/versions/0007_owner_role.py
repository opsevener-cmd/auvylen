"""Persist Owner role with a single-owner database invariant."""

import sqlalchemy as sa
from alembic import op

revision = "0007_owner_role"
down_revision = "0006_custom_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("role", sa.String(length=16), nullable=False, server_default="user"))
    op.create_index("uq_users_single_owner", "users", ["role"], unique=True,
                    postgresql_where=sa.text("role = 'owner'"),
                    sqlite_where=sa.text("role = 'owner'"))


def downgrade() -> None:
    op.drop_index("uq_users_single_owner", table_name="users")
    op.drop_column("users", "role")
