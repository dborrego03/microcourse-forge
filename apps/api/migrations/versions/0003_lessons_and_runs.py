"""lessons and runs

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    # One lesson plus its quiz is one micro-course for now; a courses table can
    # group lessons when there is more than one per course.
    op.execute("""
        CREATE TABLE lessons (
            id serial PRIMARY KEY,
            status text NOT NULL,
            request jsonb NOT NULL,
            lesson jsonb,
            quiz jsonb,
            source_chunk_ids int[] NOT NULL DEFAULT '{}',
            model text,
            prompt_version text,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE runs (
            id serial PRIMARY KEY,
            lesson_id int REFERENCES lessons (id) ON DELETE CASCADE,
            step text NOT NULL,
            status text NOT NULL,
            model text,
            tokens_in int NOT NULL DEFAULT 0,
            tokens_out int NOT NULL DEFAULT 0,
            cost_usd numeric(10, 6) NOT NULL DEFAULT 0,
            latency_ms int NOT NULL,
            retries int NOT NULL DEFAULT 0,
            cached boolean NOT NULL DEFAULT false,
            error text,
            git_sha text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE runs")
    op.execute("DROP TABLE lessons")
