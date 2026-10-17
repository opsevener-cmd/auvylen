"""Add Owner integrity guards, immutable audit history and free usage records."""

import sqlalchemy as sa
from alembic import op

revision = "0008_owner_administration"
down_revision = "0007_owner_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.create_check_constraint("ck_user_role", "role IN ('user','owner')")
        batch.create_check_constraint(
            "ck_owner_login", "role != 'owner' OR login_identifier = 'owner_god'"
        )
    op.create_table(
        "admin_audit",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target", sa.String(100), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("request_key", sa.String(80), unique=True),
        sa.Column("fingerprint", sa.String(64)),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_admin_audit_actor_id", "admin_audit", ["actor_id"])
    op.create_index("ix_admin_audit_created_at", "admin_audit", ["created_at"])
    op.create_table(
        "free_analysis_grants",
        sa.Column("analysis_id", sa.Uuid(), sa.ForeignKey("analyses.id"), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("product_slug", sa.String(100), nullable=False),
        sa.Column("policy", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    # PR #1 could have been exercised privately: preserve its existing free analyses.
    # Its only implemented product was aevyra-test-analysis. Missing debits for other
    # accounts remain reconciliation errors; never infer free funding at refund time.
    op.execute(
        sa.text("""INSERT INTO free_analysis_grants
        (analysis_id,user_id,product_slug,policy,created_at)
        SELECT a.id,a.user_id,'aevyra-test-analysis','owner-pr1-legacy',a.created_at
        FROM analyses a JOIN users u ON u.id=a.user_id
        WHERE u.role='owner' AND a.order_id IS NULL AND a.scoring_engine_slug='mock'
        AND NOT EXISTS
        (SELECT 1 FROM credit_transactions c JOIN wallets w ON w.id=c.wallet_id
         WHERE w.user_id=a.user_id
         AND replace(c.reference_id,'-','')=replace(CAST(a.id AS TEXT),'-','')
         AND c.transaction_type='ANALYSIS')""")
    )
    postgres = op.get_bind().dialect.name == "postgresql"
    if postgres:
        op.execute("""CREATE FUNCTION guard_owner_identity() RETURNS trigger AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            IF OLD.role = 'owner' THEN RAISE EXCEPTION 'Owner identity is permanent'; END IF;
            RETURN OLD;
          END IF;
          IF NEW.role <> OLD.role OR (OLD.role = 'owner' AND
             (NEW.login_identifier <> OLD.login_identifier OR NEW.disabled_at IS NOT NULL))
          THEN RAISE EXCEPTION 'Owner identity is immutable'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql""")
        op.execute(
            "CREATE TRIGGER guard_owner BEFORE UPDATE OR DELETE ON users "
            "FOR EACH ROW EXECUTE FUNCTION guard_owner_identity()"
        )
    else:
        op.execute("""CREATE TRIGGER guard_owner_update BEFORE UPDATE ON users
        WHEN NEW.role != OLD.role OR (OLD.role = 'owner' AND
        (NEW.login_identifier != OLD.login_identifier OR NEW.disabled_at IS NOT NULL))
        BEGIN SELECT RAISE(ABORT, 'Owner identity is immutable'); END""")
        op.execute("""CREATE TRIGGER guard_owner_delete BEFORE DELETE ON users
        WHEN OLD.role = 'owner' BEGIN SELECT RAISE(ABORT, 'Owner identity is permanent'); END""")
    for table in ("admin_audit", "free_analysis_grants"):
        if postgres:
            op.execute(f"""CREATE FUNCTION reject_{table}_mutation() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'Append-only history'; END; $$ LANGUAGE plpgsql""")
            op.execute(
                f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE OR TRUNCATE ON {table} "
                f"FOR EACH STATEMENT EXECUTE FUNCTION reject_{table}_mutation()"
            )
        else:
            for action in ("UPDATE", "DELETE"):
                op.execute(
                    f"CREATE TRIGGER immutable_{table}_{action.lower()} BEFORE {action} ON {table} "
                    "BEGIN SELECT RAISE(ABORT, 'Append-only history'); END"
                )


def downgrade() -> None:
    connection = op.get_bind()
    for table in ("admin_audit", "free_analysis_grants"):
        if connection.scalar(sa.text(f"SELECT count(*) FROM {table}")):
            raise RuntimeError("Owner history exists; restore a verified backup for rollback")
    if connection.scalar(sa.text("SELECT count(*) FROM users WHERE role='owner'")):
        raise RuntimeError("Owner identity exists; restore a verified backup for rollback")
    if connection.dialect.name == "postgresql":
        op.execute("DROP TRIGGER guard_owner ON users")
        op.execute("DROP FUNCTION guard_owner_identity()")
        for table in ("admin_audit", "free_analysis_grants"):
            op.execute(f"DROP TRIGGER immutable_{table} ON {table}")
            op.execute(f"DROP FUNCTION reject_{table}_mutation()")
    else:
        op.execute("DROP TRIGGER guard_owner_update")
        op.execute("DROP TRIGGER guard_owner_delete")
    op.drop_table("free_analysis_grants")
    op.drop_table("admin_audit")
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("ck_user_role", type_="check")
        batch.drop_constraint("ck_owner_login", type_="check")
