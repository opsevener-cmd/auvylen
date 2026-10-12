"""accounts_credits_redemption"""

import sqlalchemy as sa
from alembic import op

revision = "0003_credits"
down_revision = "0002_commercial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "redemption_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("public_batch_id", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("channel", sa.String(length=64), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("credits_per_code", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.CheckConstraint("credits_per_code > 0 AND quantity > 0", name="ck_batch_quantity"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_batch_id"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("public_user_id", sa.String(length=40), nullable=False),
        sa.Column("login_identifier", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("login_identifier"),
        sa.UniqueConstraint("public_user_id"),
    )
    op.create_table(
        "redemption_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("lookup_digest", sa.String(length=64), nullable=False),
        sa.Column("masked_suffix", sa.String(length=4), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.CheckConstraint("status IN ('AVAILABLE','REDEEMED')", name="ck_redemption_code_status"),
        sa.ForeignKeyConstraint(
            ["batch_id"],
            ["redemption_batches.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lookup_digest"),
    )
    op.create_index(
        op.f("ix_redemption_codes_batch_id"), "redemption_codes", ["batch_id"], unique=False
    )
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_digest"),
    )
    op.create_index(op.f("ix_sessions_expires_at"), "sessions", ["expires_at"], unique=False)
    op.create_index(op.f("ix_sessions_user_id"), "sessions", ["user_id"], unique=False)
    op.create_table(
        "wallets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("cached_balance", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("cached_balance >= 0", name="ck_wallet_nonnegative"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_table(
        "credit_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("wallet_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("transaction_type", sa.String(length=40), nullable=False),
        sa.Column("reference_type", sa.String(length=40), nullable=False),
        sa.Column("reference_id", sa.String(length=80), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("balance_after", sa.BigInteger(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount <> 0 AND balance_after >= 0", name="ck_credit_amount"),
        sa.ForeignKeyConstraint(
            ["wallet_id"],
            ["wallets.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("wallet_id", "idempotency_key", name="uq_credit_idempotency"),
    )
    op.create_index(
        op.f("ix_credit_transactions_wallet_id"), "credit_transactions", ["wallet_id"], unique=False
    )
    op.create_table(
        "redemptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("redemption_code_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("wallet_id", sa.Uuid(), nullable=False),
        sa.Column("credit_transaction_id", sa.Uuid(), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["credit_transaction_id"],
            ["credit_transactions.id"],
        ),
        sa.ForeignKeyConstraint(
            ["redemption_code_id"],
            ["redemption_codes.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
        ),
        sa.ForeignKeyConstraint(
            ["wallet_id"],
            ["wallets.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credit_transaction_id"),
        sa.UniqueConstraint("redemption_code_id"),
    )
    op.create_index(op.f("ix_redemptions_user_id"), "redemptions", ["user_id"], unique=False)
    with op.batch_alter_table("analyses") as batch:
        batch.add_column(sa.Column("user_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("credit_request_key", sa.String(80), nullable=True))
        batch.alter_column("order_id", existing_type=sa.Uuid(), nullable=True)
        batch.create_index("ix_analyses_user_id", ["user_id"])
        batch.create_unique_constraint(
            "uq_analysis_credit_request", ["user_id", "credit_request_key"]
        )
        batch.create_foreign_key("fk_analysis_user", "users", ["user_id"], ["id"])
        batch.create_check_constraint(
            "ck_analysis_funding",
            "(order_id IS NOT NULL AND user_id IS NULL AND credit_request_key IS NULL) OR "
            "(order_id IS NULL AND user_id IS NOT NULL AND credit_request_key IS NOT NULL)",
        )
    with op.batch_alter_table("products") as batch:
        batch.add_column(sa.Column("credit_cost", sa.Integer(), server_default="1", nullable=False))
        batch.create_check_constraint("ck_product_credit_cost", "credit_cost > 0")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION forbid_credit_history_mutation() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'Credit history is immutable; append a compensating transaction';
            END $$""")
        op.execute("""CREATE TRIGGER credit_history_immutable BEFORE UPDATE OR DELETE
            ON credit_transactions FOR EACH ROW
            EXECUTE FUNCTION forbid_credit_history_mutation()""")
        op.execute("""CREATE TRIGGER credit_history_no_truncate BEFORE TRUNCATE
            ON credit_transactions FOR EACH STATEMENT
            EXECUTE FUNCTION forbid_credit_history_mutation()""")


def downgrade() -> None:
    # Financial/account data must never be removed by a casual rollback.
    count = op.get_bind().scalar(
        sa.text("SELECT (SELECT count(*) FROM users) + (SELECT count(*) FROM redemption_batches)")
    )
    if count:
        raise RuntimeError("Accounts or issued batches exist; restore a reviewed backup instead")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER credit_history_immutable ON credit_transactions")
        op.execute("DROP TRIGGER credit_history_no_truncate ON credit_transactions")
        op.execute("DROP FUNCTION forbid_credit_history_mutation()")
    with op.batch_alter_table("products") as batch:
        batch.drop_constraint("ck_product_credit_cost", type_="check")
        batch.drop_column("credit_cost")
    with op.batch_alter_table("analyses") as batch:
        batch.drop_constraint("ck_analysis_funding", type_="check")
        batch.drop_constraint("fk_analysis_user", type_="foreignkey")
        batch.drop_constraint("uq_analysis_credit_request", type_="unique")
        batch.drop_index("ix_analyses_user_id")
        batch.drop_column("credit_request_key")
        batch.drop_column("user_id")
        batch.alter_column("order_id", existing_type=sa.Uuid(), nullable=False)
    for table in (
        "redemptions",
        "credit_transactions",
        "wallets",
        "sessions",
        "redemption_codes",
        "users",
        "redemption_batches",
    ):
        op.drop_table(table)
