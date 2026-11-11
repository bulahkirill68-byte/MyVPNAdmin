"""Initial schema. Explicit tables keep this migration independent of future models."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None


def upgrade():
    op.create_table("admins", sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("name", sa.String(80), nullable=False, unique=True),
                    sa.Column("password", sa.Text, nullable=False))
    op.create_table("login_guards", sa.Column("key", sa.String(100), primary_key=True),
                    sa.Column("failures", sa.Integer, nullable=False), sa.Column("until", sa.Integer, nullable=False))
    op.create_table("sessions", sa.Column("token_hash", sa.String(64), primary_key=True),
                    sa.Column("admin_id", sa.Integer, nullable=False), sa.Column("csrf", sa.String(100), nullable=False),
                    sa.Column("expires", sa.Integer, nullable=False))
    op.create_table("servers", sa.Column("id", sa.Integer, primary_key=True),
                    sa.Column("metadata_json", sa.JSON, nullable=False))
    op.create_table("users", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False), sa.Column("uuid", sa.String(36), nullable=False, unique=True),
        sa.Column("email", sa.String(150, collation="NOCASE"), nullable=False, unique=True),
        sa.Column("comment", sa.Text, nullable=False),
        sa.Column("intent", sa.String(20), nullable=False), sa.Column("expires_at", sa.Integer),
        sa.Column("quota_bytes", sa.Integer), sa.Column("used_bytes", sa.Integer, nullable=False),
        sa.Column("last_up", sa.Integer, nullable=False), sa.Column("last_down", sa.Integer, nullable=False),
        sa.Column("last_activity", sa.Integer), sa.Column("sync", sa.String(30), nullable=False), sa.Column("error", sa.Text),
        sa.Column("applied_uuid", sa.String(36)), sa.Column("historical_uuids", sa.JSON, nullable=False),
        sa.Column("deleted", sa.Boolean, nullable=False),
        sa.Column("token_hash", sa.String(64)), sa.Column("notified", sa.Integer, nullable=False),
        sa.Column("policy", sa.String(30), nullable=False), sa.Column("created", sa.Integer, nullable=False))
    op.create_table("audit", sa.Column("id", sa.Integer, primary_key=True), sa.Column("at", sa.Integer, nullable=False),
        sa.Column("actor", sa.String(100), nullable=False), sa.Column("action", sa.String(100), nullable=False),
        sa.Column("user_id", sa.Integer), sa.Column("detail", sa.Text, nullable=False))
    op.create_index("ix_audit_at", "audit", ["at"])
    op.create_table("samples", sa.Column("id", sa.Integer, primary_key=True), sa.Column("at", sa.Integer, nullable=False),
        sa.Column("user_id", sa.Integer, nullable=False), sa.Column("delta", sa.Integer, nullable=False))
    op.create_index("ix_samples_at", "samples", ["at"])
    op.create_index("ix_samples_user_id", "samples", ["user_id"])
    op.create_table("settings", sa.Column("key", sa.String(100), primary_key=True),
                    sa.Column("value", sa.JSON, nullable=False))


def downgrade():
    for table in ["settings", "samples", "audit", "users", "servers", "sessions", "login_guards", "admins"]:
        op.drop_table(table)
