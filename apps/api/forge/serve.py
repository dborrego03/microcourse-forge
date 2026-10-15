"""Run the API locally: uv run python -m forge.serve

Same as `uvicorn forge.api:app`, but on Windows uvicorn picks the Proactor
event loop, which psycopg's async mode can't use. In Docker plain uvicorn is fine.
"""

import uvicorn

from forge.db import run

if __name__ == "__main__":
    run(uvicorn.Server(uvicorn.Config("forge.api:app", host="127.0.0.1", port=8000)).serve())
