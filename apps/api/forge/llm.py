"""Structured LLM calls.

Locally and in my own CI this goes through the Claude Code CLI in headless mode
(`claude -p --json-schema ...`), which runs on my Claude subscription instead of
a paid API key. That is only allowed for personal use, so a deployed instance
that other people use needs an API provider; see docs/adr/0002-llm-provider.md.

Responses are cached on disk by (model, system prompt, prompt, schema), so
re-running evals or the same lesson request doesn't call the model again.
"""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "llm"
TIMEOUT_S = 240
MAX_ATTEMPTS = 3


class LLMError(Exception):
    pass


@dataclass
class LLMResult:
    data: dict
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float  # what the same call would cost at API list prices, as reported by the CLI
    latency_ms: int
    attempts: int = 1
    cached: bool = False


def claude_command() -> str:
    if path := os.environ.get("CLAUDE_BIN"):
        return path
    found = shutil.which("claude") or "claude"
    # On Windows the npm shim is a .cmd file, and cmd.exe mangles quotes in the
    # JSON schema argument. Call the real executable it points to instead.
    native = Path(found).parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
    return str(native) if native.exists() else found


def call_claude(system: str, prompt: str, schema: dict, model: str) -> LLMResult:
    command = [
        claude_command(), "-p",
        "--output-format", "json",
        "--model", model,
        "--system-prompt", system,
        "--json-schema", json.dumps(schema),
        "--tools", "",
        "--setting-sources", "",
        "--strict-mcp-config",
        "--no-session-persistence",
    ]  # fmt: skip
    # With ANTHROPIC_API_KEY set, `claude -p` bills the API instead of the subscription.
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}

    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = time.perf_counter()
        # An empty working dir so no CLAUDE.md or project settings leak into the call.
        with tempfile.TemporaryDirectory() as workdir:
            try:
                proc = subprocess.run(
                    command, input=prompt, capture_output=True, text=True, encoding="utf-8",
                    cwd=workdir, env=env, timeout=TIMEOUT_S,
                )  # fmt: skip
            except subprocess.TimeoutExpired:
                error = f"timed out after {TIMEOUT_S}s"
                continue
        try:
            out = json.loads(proc.stdout)
        except json.JSONDecodeError:
            error = f"exit {proc.returncode}: {(proc.stderr or proc.stdout)[:300]}"
            continue

        if not out.get("is_error") and out.get("structured_output") is not None:
            usage = out.get("usage", {})
            return LLMResult(
                data=out["structured_output"],
                model=model,
                tokens_in=usage.get("input_tokens", 0)
                + usage.get("cache_creation_input_tokens", 0)
                + usage.get("cache_read_input_tokens", 0),
                tokens_out=usage.get("output_tokens", 0),
                cost_usd=out.get("total_cost_usd", 0.0),
                latency_ms=round((time.perf_counter() - started) * 1000),
                attempts=attempt,
            )
        error = f"{out.get('subtype')}: {str(out.get('result'))[:300]}"
        # Only rate limits and server errors are worth retrying.
        if out.get("api_error_status") not in (429, 500, 502, 503, 529):
            break
        time.sleep(2**attempt)
    raise LLMError(error)


def complete_json(system: str, prompt: str, schema: dict, model: str) -> LLMResult:
    key = hashlib.sha256(json.dumps([model, system, prompt, schema], sort_keys=True).encode()).hexdigest()
    path = CACHE_DIR / f"{key}.json"
    if path.exists() and os.environ.get("FORGE_LLM_CACHE") != "off":
        return LLMResult(**{**json.loads(path.read_text(encoding="utf-8")), "cached": True})

    result = call_claude(system, prompt, schema, model)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(result)), encoding="utf-8")
    return result
