"""runs.trace_id

Revision ID: 0004
Revises: 0003
"""

from alembic import op

revision = "0004"
down_revision = "0003"


def upgrade() -> None:
    # Null when tracing is off; otherwise links a run to its trace in Jaeger or Langfuse.
    op.execute("ALTER TABLE runs ADD COLUMN trace_id text")


def downgrade() -> None:
    op.execute("ALTER TABLE runs DROP COLUMN trace_id")
