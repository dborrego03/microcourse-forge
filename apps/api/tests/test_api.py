import httpx
import psycopg
import pytest

from forge.api import app
from forge.db import connect


@pytest.fixture
async def client():
    try:
        await (await connect()).close()
    except psycopg.OperationalError:
        pytest.skip("Postgres is not running (docker compose up -d)")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_metrics_has_every_panel_section(client):
    res = await client.get("/metrics")
    assert res.status_code == 200
    assert set(res.json()) == {"evals", "steps", "blocked", "lessons"}


async def test_packages_only_come_in_known_formats(client):
    assert (await client.get("/lessons/1/zip")).status_code == 422
    assert (await client.get("/lessons/999999/cmi5")).status_code == 404


async def test_search_rejects_tiny_queries(client):
    assert (await client.get("/search", params={"q": "a"})).status_code == 422
