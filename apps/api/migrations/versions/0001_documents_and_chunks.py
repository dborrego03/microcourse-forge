"""documents and chunks

Revision ID: 0001
Revises:
"""

from alembic import op

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("""
        CREATE TABLE documents (
            id serial PRIMARY KEY,
            title text NOT NULL,
            authors text NOT NULL,
            source_url text NOT NULL,
            license text NOT NULL,
            license_url text NOT NULL,
            attribution text NOT NULL,
            content_hash text NOT NULL UNIQUE,
            ingested_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    # tsv is here already so hybrid search later doesn't need a re-ingest.
    op.execute("""
        CREATE TABLE chunks (
            id serial PRIMARY KEY,
            document_id int NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
            ordinal int NOT NULL,
            section_path text NOT NULL,
            pdf_page_start int NOT NULL,
            pdf_page_end int NOT NULL,
            text text NOT NULL,
            token_count int NOT NULL,
            embedding vector(384) NOT NULL,
            embedding_model text NOT NULL,
            tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,
            UNIQUE (document_id, ordinal)
        )
    """)
    op.execute("CREATE INDEX chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops)")
    op.execute("CREATE INDEX chunks_tsv_idx ON chunks USING gin (tsv)")


def downgrade() -> None:
    op.execute("DROP TABLE chunks")
    op.execute("DROP TABLE documents")
