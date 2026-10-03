"""v3 multi-agent planning tables

Revision ID: e7b2d4f08c11
Revises: c4e8b1a27d90
Create Date: 2026-10-02 22:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7b2d4f08c11"
down_revision: Union[str, Sequence[str], None] = "c4e8b1a27d90"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_threads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("thread_id", sa.String(length=80), nullable=False),
        sa.Column("graph_name", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["planning_sessions.id"], name=op.f("fk_agent_threads_session_id_planning_sessions")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_threads")),
        sa.UniqueConstraint("session_id", name=op.f("uq_agent_threads_session_id")),
    )
    op.create_table(
        "agent_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("task_key", sa.String(length=64), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("assigned_agent", sa.String(length=64), nullable=False),
        sa.Column("dependencies", sa.JSON(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_tasks")),
    )
    op.create_index(op.f("ix_agent_tasks_session_id"), "agent_tasks", ["session_id"], unique=False)
    op.create_table(
        "agent_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_artifacts")),
    )
    op.create_index(op.f("ix_agent_artifacts_session_id"), "agent_artifacts", ["session_id"], unique=False)
    op.create_table(
        "agent_spans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("agent_run_id", sa.Uuid(), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("parent_agent", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("model", sa.String(length=80), nullable=True),
        sa.Column("prompt_version", sa.String(length=80), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False),
        sa.Column("tool_calls", sa.JSON(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("safe_metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"], name=op.f("fk_agent_spans_agent_run_id_agent_runs")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_spans")),
    )
    op.create_index(op.f("ix_agent_spans_session_id"), "agent_spans", ["session_id"], unique=False)
    op.create_index(op.f("ix_agent_spans_agent_run_id"), "agent_spans", ["agent_run_id"], unique=False)
    op.create_table(
        "itineraries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("itinerary_key", sa.String(length=200), nullable=False),
        sa.Column("rank_position", sa.Integer(), nullable=False),
        sa.Column("estimated_total_cost", sa.Float(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("valid", sa.Boolean(), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_itineraries")),
    )
    op.create_index(op.f("ix_itineraries_session_id"), "itineraries", ["session_id"], unique=False)
    op.create_table(
        "itinerary_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("itinerary_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("item_type", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("estimated_cost", sa.Float(), nullable=True),
        sa.Column("source_candidate_id", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(["itinerary_id"], ["itineraries.id"], name=op.f("fk_itinerary_items_itinerary_id_itineraries")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_itinerary_items")),
    )
    op.create_index(op.f("ix_itinerary_items_itinerary_id"), "itinerary_items", ["itinerary_id"], unique=False)
    op.create_table(
        "execution_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("itinerary_key", sa.String(length=200), nullable=False),
        sa.Column("item_key", sa.String(length=240), nullable=False),
        sa.Column("idempotency_key", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("calendar_event_id", sa.String(length=80), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_execution_actions")),
    )
    op.create_index(op.f("ix_execution_actions_session_id"), "execution_actions", ["session_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_execution_actions_session_id"), table_name="execution_actions")
    op.drop_table("execution_actions")
    op.drop_index(op.f("ix_itinerary_items_itinerary_id"), table_name="itinerary_items")
    op.drop_table("itinerary_items")
    op.drop_index(op.f("ix_itineraries_session_id"), table_name="itineraries")
    op.drop_table("itineraries")
    op.drop_index(op.f("ix_agent_spans_agent_run_id"), table_name="agent_spans")
    op.drop_index(op.f("ix_agent_spans_session_id"), table_name="agent_spans")
    op.drop_table("agent_spans")
    op.drop_index(op.f("ix_agent_artifacts_session_id"), table_name="agent_artifacts")
    op.drop_table("agent_artifacts")
    op.drop_index(op.f("ix_agent_tasks_session_id"), table_name="agent_tasks")
    op.drop_table("agent_tasks")
    op.drop_table("agent_threads")
