"""audio_assets

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision = "0005"
down_revision = "0004"


def upgrade() -> None:
    # Files live in data/media/lesson-<id>/part-<n>.mp3|.vtt locally (Blob storage when deployed).
    op.execute("""
        CREATE TABLE audio_assets (
            id serial PRIMARY KEY,
            lesson_id int NOT NULL REFERENCES lessons (id) ON DELETE CASCADE,
            part int NOT NULL,
            provider text NOT NULL,
            model text NOT NULL,
            voice text NOT NULL,
            characters int NOT NULL,
            duration_s numeric(8, 2) NOT NULL,
            cost_usd numeric(10, 6),
            cache_key text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (lesson_id, part)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE audio_assets")
