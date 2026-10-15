from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent
# The repo root in a checkout. Inside the Docker image the code sits in /app, so this
# resolves to "/" and the data paths below come from environment variables instead.
REPO_ROOT = API_DIR.parent.parent
