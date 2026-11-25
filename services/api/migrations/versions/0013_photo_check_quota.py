"""Photo check funding, credits charged and roast level

Additive: three columns on photo_check_analyses. Existing rows keep funding NULL (checks made
before quotas existed, never counted towards a quota), credits_charged 0 and roast "off".
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_photo_check_quota"
down_revision = "0012_photo_check"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("photo_check_analyses", sa.Column("funding", sa.String(length=16), nullable=True))
    op.add_column(
        "photo_check_analyses",
        sa.Column("credits_charged", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "photo_check_analyses",
        sa.Column("roast", sa.String(length=8), server_default="off", nullable=False),
    )
    # Batch mode so SQLite (used by the test suite) can add constraints to an existing table.
    with op.batch_alter_table("photo_check_analyses") as batch:
        batch.create_check_constraint(
            "ck_photo_check_funding",
            "funding IS NULL OR funding IN ('free_signup','free_weekly','credits','owner')",
        )
        batch.create_check_constraint("ck_photo_check_credits", "credits_charged >= 0")


def downgrade() -> None:
    with op.batch_alter_table("photo_check_analyses") as batch:
        batch.drop_constraint("ck_photo_check_credits", type_="check")
        batch.drop_constraint("ck_photo_check_funding", type_="check")
        batch.drop_column("roast")
        batch.drop_column("credits_charged")
        batch.drop_column("funding")
