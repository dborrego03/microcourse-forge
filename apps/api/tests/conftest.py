import asyncio
import sys

import psycopg
import pytest

from forge.db import connect

if sys.platform == "win32":
    # psycopg's async mode can't run on the Proactor loop Windows uses by default.
    def pytest_asyncio_loop_factories(config, item):
        return {"selector": asyncio.SelectorEventLoop}


@pytest.fixture
async def conn():
    """A connection whose changes are rolled back, so tests never touch real data."""
    try:
        conn = await connect()
    except psycopg.OperationalError:
        pytest.skip("Postgres is not running (docker compose up -d)")
    try:
        yield conn
    finally:
        await conn.rollback()
        await conn.close()
