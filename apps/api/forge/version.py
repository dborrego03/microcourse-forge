import os
import subprocess
from functools import cache


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True, stderr=subprocess.DEVNULL).strip()


@cache
def git_sha() -> str:
    """Short commit of the running code, with -dirty when tracked files have local changes.

    evals/results is left out of the dirty check: eval runs rewrite it, and the
    results don't change what the code does.
    """
    if sha := os.environ.get("GIT_SHA"):  # set in the Docker image, which has no .git
        return sha
    try:
        sha = git("rev-parse", "--short=7", "HEAD")
        changes = git(
            "status", "--porcelain", "--untracked-files=no", "--", ":/", ":(top,exclude)evals/results"
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return f"{sha}-dirty" if changes else sha
