import os
import subprocess
from functools import cache


@cache
def git_sha() -> str:
    """Short commit of the running code, with -dirty when there are local changes."""
    if sha := os.environ.get("GIT_SHA"):  # set in the Docker image, which has no .git
        return sha
    try:
        command = ["git", "describe", "--always", "--dirty", "--abbrev=7"]
        return subprocess.check_output(command, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
