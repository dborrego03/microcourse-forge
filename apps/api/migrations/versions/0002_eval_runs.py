"""eval_runs

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE eval_runs (
            id serial PRIMARY KEY,
            kind text NOT NULL,
            dataset text NOT NULL,
            config jsonb NOT NULL,
            metrics jsonb NOT NULL,
            git_sha text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE eval_runs")
