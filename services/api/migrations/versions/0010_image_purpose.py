"""Separate prediction-only photographs from annotation/training photographs."""

import sqlalchemy as sa
from alembic import op

revision = "0010_image_purpose"
down_revision = "0009_aesthetic_analyses"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing rows keep their meaning: every previously uploaded image is for annotation.
    with op.batch_alter_table("preference_images") as batch:
        batch.add_column(
            sa.Column("purpose", sa.String(length=20), nullable=False, server_default="annotation")
        )
        batch.create_check_constraint("ck_image_purpose", "purpose IN ('annotation','prediction')")


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(
        sa.text("SELECT count(*) FROM preference_images WHERE purpose = 'prediction'")
    ):
        raise RuntimeError("Delete prediction-only photographs before downgrading")
    with op.batch_alter_table("preference_images") as batch:
        batch.drop_constraint("ck_image_purpose", type_="check")
        batch.drop_column("purpose")
