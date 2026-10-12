"""Commercial skeleton and one clearly synthetic development product."""

from uuid import UUID

import sqlalchemy as sa
from alembic import op

revision = "0002_commercial"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.String(1000), nullable=False),
        sa.Column("product_type", sa.String(40), nullable=False),
        sa.Column("price_amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.CheckConstraint("price_amount > 0", name="ck_product_price"),
    )
    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("public_order_id", sa.String(40), nullable=False, unique=True),
        sa.Column("product_id", sa.Uuid(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.CheckConstraint("amount > 0", name="ck_order_amount"),
        sa.CheckConstraint(
            "status IN ('CREATED','PENDING_PAYMENT','PAID','FULFILLING',"
            "'COMPLETED','FAILED','CANCELLED','REFUNDED')",
            name="ck_order_status",
        ),
    )
    op.create_table(
        "payment_attempts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("order_id", sa.Uuid(), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("provider_payment_id", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("provider", "provider_payment_id", name="uq_provider_payment"),
        sa.CheckConstraint("amount > 0", name="ck_payment_amount"),
        sa.CheckConstraint(
            "status IN ('PENDING','SUCCEEDED','FAILED','REFUNDED')", name="ck_payment_status"
        ),
    )
    op.create_index("ix_payment_attempts_order_id", "payment_attempts", ["order_id"])
    op.create_table(
        "payment_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("provider_event_id", sa.String(100), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("processing_status", sa.String(30), nullable=False),
        sa.UniqueConstraint("provider", "provider_event_id", name="uq_provider_event"),
        sa.CheckConstraint(
            "processing_status IN ('RECEIVED','PROCESSED','REJECTED')", name="ck_event_status"
        ),
    )
    op.create_table(
        "analyses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("order_id", sa.Uuid(), sa.ForeignKey("orders.id"), nullable=False, unique=True),
        sa.Column("scoring_engine_slug", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("failure_reason", sa.String(100)),
        sa.CheckConstraint(
            "status IN ('CREATED','PROCESSING','COMPLETED','FAILED')", name="ck_analysis_status"
        ),
    )
    op.create_table(
        "analysis_results",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "analysis_id", sa.Uuid(), sa.ForeignKey("analyses.id"), nullable=False, unique=True
        ),
        sa.Column("raw_score", sa.Double(), nullable=False),
        sa.Column("display_score", sa.Double(), nullable=False),
        sa.Column("engine_slug", sa.String(100), nullable=False),
        sa.Column("engine_version", sa.String(100), nullable=False),
        sa.Column("calibration_version", sa.String(100)),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    products = sa.table(
        "products",
        sa.column("id", sa.Uuid()),
        sa.column("slug", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
        sa.column("product_type", sa.String()),
        sa.column("price_amount", sa.Integer()),
        sa.column("currency", sa.String()),
        sa.column("active", sa.Boolean()),
    )
    op.bulk_insert(
        products,
        [
            {
                "id": UUID("14b760f2-26ef-42fc-99c2-fbb5126eb328"),
                "slug": "aevyra-test-analysis",
                "name": "Aevyra Analysis",
                "description": (
                    "Development-only analysis with a synthetic mock score. "
                    "No photo or real AI model is used."
                ),
                "product_type": "test_analysis",
                "price_amount": 100,
                "currency": "CNY",
                "active": True,
            }
        ],
    )


def downgrade() -> None:
    for table in (
        "analysis_results",
        "analyses",
        "payment_events",
        "payment_attempts",
        "orders",
        "products",
    ):
        op.drop_table(table)
