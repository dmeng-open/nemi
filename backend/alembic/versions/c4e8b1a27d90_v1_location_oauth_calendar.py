"""v1 location, oauth, and calendar columns

Revision ID: c4e8b1a27d90
Revises: ad1a206d0e8d
Create Date: 2026-10-02 16:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c4e8b1a27d90"
down_revision: Union[str, Sequence[str], None] = "ad1a206d0e8d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user_preferences", sa.Column("home_city", sa.String(length=80), nullable=True))
    op.add_column("user_preferences", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("user_preferences", sa.Column("longitude", sa.Float(), nullable=True))
    op.add_column("user_preferences", sa.Column("default_radius_km", sa.Float(), nullable=True))
    op.add_column("user_preferences", sa.Column("timezone", sa.String(length=64), nullable=True))
    op.add_column(
        "calendar_actions",
        sa.Column("external_event_id", sa.String(length=128), nullable=True),
    )
    op.create_table(
        "oauth_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.JSON(), nullable=False),
        sa.Column("account_email", sa.String(length=320), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_oauth_connections_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oauth_connections")),
        sa.UniqueConstraint("user_id", name=op.f("uq_oauth_connections_user_id")),
    )
    op.create_table(
        "oauth_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("return_path", sa.String(length=80), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_oauth_states_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oauth_states")),
        sa.UniqueConstraint("state_hash", name=op.f("uq_oauth_states_state_hash")),
    )
    op.create_index(op.f("ix_oauth_states_user_id"), "oauth_states", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_oauth_states_user_id"), table_name="oauth_states")
    op.drop_table("oauth_states")
    op.drop_table("oauth_connections")
    op.drop_column("calendar_actions", "external_event_id")
    op.drop_column("user_preferences", "timezone")
    op.drop_column("user_preferences", "default_radius_km")
    op.drop_column("user_preferences", "longitude")
    op.drop_column("user_preferences", "latitude")
    op.drop_column("user_preferences", "home_city")
