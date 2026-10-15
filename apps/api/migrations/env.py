from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from forge.db import DATABASE_URL

if context.config.config_file_name:
    fileConfig(context.config.config_file_name)

# Migrations are plain SQL, so there is no SQLAlchemy metadata to compare against.
engine = create_engine(DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1))

with engine.connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
