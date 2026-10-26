"""Phase 6 aesthetic analysis requests (private image references and pinned model)."""

import sqlalchemy as sa
from alembic import op

revision = "0009_aesthetic_analyses"
down_revision = "0008_owner_administration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "aesthetic_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("request_key", sa.String(length=80), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=True),
        sa.Column("image_sha256", sa.String(length=64), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("consent_version", sa.String(length=60), nullable=False),
        sa.Column("model_version", sa.String(length=64), nullable=False),
        sa.Column("manifest_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("width > 0 AND height > 0", name="ck_aesthetic_dimensions"),
        sa.ForeignKeyConstraint(["job_id"], ["research_jobs.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
        sa.UniqueConstraint("user_id", "request_key", name="uq_aesthetic_request"),
    )
    op.create_index(
        op.f("ix_aesthetic_analyses_user_id"), "aesthetic_analyses", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_aesthetic_analyses_expires_at"), "aesthetic_analyses", ["expires_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_aesthetic_analyses_expires_at"), table_name="aesthetic_analyses")
    op.drop_index(op.f("ix_aesthetic_analyses_user_id"), table_name="aesthetic_analyses")
    op.drop_table("aesthetic_analyses")
