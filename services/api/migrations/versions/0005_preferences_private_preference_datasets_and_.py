"""Private preference datasets and annotations"""

import sqlalchemy as sa
from alembic import op

revision = "0005_preferences"
down_revision = "0004_research"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "preference_projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_preference_projects_user_id"), "preference_projects", ["user_id"], unique=False
    )
    op.create_table(
        "preference_datasets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=500), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=False),
        sa.Column("license", sa.String(length=500), nullable=False),
        sa.Column("rating_min", sa.Integer(), nullable=False),
        sa.Column("rating_max", sa.Integer(), nullable=False),
        sa.Column("consent_version", sa.String(length=40), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rating_min < rating_max", name="ck_dataset_scale"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["preference_projects.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_preference_datasets_expires_at"),
        "preference_datasets",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_preference_datasets_project_id"),
        "preference_datasets",
        ["project_id"],
        unique=False,
    )
    op.create_table(
        "preference_images",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_id", sa.Uuid(), nullable=False),
        sa.Column("thumbnail_id", sa.Uuid(), nullable=False),
        sa.Column("original_hash", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("subject_group", sa.String(length=120), nullable=True),
        sa.Column("excluded", sa.Boolean(), nullable=False),
        sa.Column("consent_version", sa.String(length=40), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("byte_size > 0", name="ck_image_bytes"),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["preference_datasets.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "content_hash", name="uq_dataset_image_content"),
    )
    op.create_index(
        op.f("ix_preference_images_dataset_id"), "preference_images", ["dataset_id"], unique=False
    )
    op.create_table(
        "preference_pairs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("left_id", sa.Uuid(), nullable=False),
        sa.Column("right_id", sa.Uuid(), nullable=False),
        sa.Column("choice", sa.String(length=10), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("choice IN ('left','right','equal','skip')", name="ck_pair_choice"),
        sa.CheckConstraint("left_id < right_id", name="ck_pair_canonical_order"),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["preference_datasets.id"],
        ),
        sa.ForeignKeyConstraint(
            ["left_id"],
            ["preference_images.id"],
        ),
        sa.ForeignKeyConstraint(
            ["right_id"],
            ["preference_images.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("left_id", "right_id", name="uq_preference_pair"),
    )
    op.create_index(
        op.f("ix_preference_pairs_dataset_id"), "preference_pairs", ["dataset_id"], unique=False
    )
    op.create_table(
        "preference_ratings",
        sa.Column("image_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["image_id"],
            ["preference_images.id"],
        ),
        sa.PrimaryKeyConstraint("image_id"),
    )


def downgrade() -> None:
    op.drop_table("preference_ratings")
    op.drop_index(op.f("ix_preference_pairs_dataset_id"), table_name="preference_pairs")
    op.drop_table("preference_pairs")
    op.drop_index(op.f("ix_preference_images_dataset_id"), table_name="preference_images")
    op.drop_table("preference_images")
    op.drop_index(op.f("ix_preference_datasets_project_id"), table_name="preference_datasets")
    op.drop_index(op.f("ix_preference_datasets_expires_at"), table_name="preference_datasets")
    op.drop_table("preference_datasets")
    op.drop_index(op.f("ix_preference_projects_user_id"), table_name="preference_projects")
    op.drop_table("preference_projects")
