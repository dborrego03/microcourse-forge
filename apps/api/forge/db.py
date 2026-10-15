import asyncio
import os
import sys

import psycopg
from pgvector.psycopg import register_vector_async
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://forge:forge_dev_password@localhost:5432/microcourse"
)


async def connect() -> psycopg.AsyncConnection:
    conn = await psycopg.AsyncConnection.connect(DATABASE_URL, row_factory=dict_row)
    await register_vector_async(conn)
    return conn


def run(coro):
    # psycopg's async mode doesn't work with the default Proactor loop on Windows.
    if sys.platform == "win32":
        return asyncio.run(coro, loop_factory=asyncio.SelectorEventLoop)
    return asyncio.run(coro)
