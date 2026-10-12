"""Custom rating models and worker progress"""

import sqlalchemy as sa
from alembic import op

revision = "0006_custom_models"
down_revision = "0005_preferences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "custom_preference_models",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("training_job_id", sa.Uuid(), nullable=False),
        sa.Column("extractor", sa.String(length=100), nullable=False),
        sa.Column("implementation", sa.String(length=100), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(length=64), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=True),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('TRAINING','READY','FAILED','ARCHIVED','DELETED')", name="ck_custom_state"
        ),
        sa.CheckConstraint("version >= 1", name="ck_custom_version"),
        sa.ForeignKeyConstraint(["dataset_id"], ["preference_datasets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["preference_projects.id"],
        ),
        sa.ForeignKeyConstraint(
            ["training_job_id"],
            ["research_jobs.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "version", name="uq_custom_dataset_version"),
        sa.UniqueConstraint("training_job_id"),
    )
    op.create_index(
        op.f("ix_custom_preference_models_dataset_id"),
        "custom_preference_models",
        ["dataset_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_custom_preference_models_expires_at"),
        "custom_preference_models",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_custom_preference_models_user_id"),
        "custom_preference_models",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "preference_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("image_id", sa.Uuid(), nullable=False),
        sa.Column("extractor", sa.String(length=100), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["image_id"], ["preference_images.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("image_id", "extractor", name="uq_image_extractor"),
    )
    op.create_index(
        op.f("ix_preference_embeddings_image_id"),
        "preference_embeddings",
        ["image_id"],
        unique=False,
    )
    op.add_column("research_jobs", sa.Column("payload", sa.JSON(), nullable=True))
    op.add_column(
        "research_jobs", sa.Column("progress", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "research_jobs",
        sa.Column("phase", sa.String(length=100), server_default="Queued", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("research_jobs", "phase")
    op.drop_column("research_jobs", "progress")
    op.drop_column("research_jobs", "payload")
    op.drop_index(op.f("ix_preference_embeddings_image_id"), table_name="preference_embeddings")
    op.drop_table("preference_embeddings")
    op.drop_index(
        op.f("ix_custom_preference_models_user_id"), table_name="custom_preference_models"
    )
    op.drop_index(
        op.f("ix_custom_preference_models_expires_at"), table_name="custom_preference_models"
    )
    op.drop_index(
        op.f("ix_custom_preference_models_dataset_id"), table_name="custom_preference_models"
    )
    op.drop_table("custom_preference_models")
