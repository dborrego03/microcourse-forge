"""Structured LLM calls, with two providers behind one function.

- claude-cli (default): the Claude Code CLI in headless mode (`claude -p --json-schema ...`),
  which runs on my Claude subscription. Anthropic's terms allow that for my own use and CI,
  not for serving other people, so it's for local development and evals only.
- anthropic: the Messages API with an API key (ANTHROPIC_API_KEY), for anything deployed.

FORGE_LLM_PROVIDER picks one. See docs/adr/0002-llm-provider.md.

Responses are cached on disk by (model, system prompt, prompt, schema), so re-running
evals or the same lesson request doesn't call the model again.
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

import anthropic
from pydantic import BaseModel, ValidationError

from forge import API_DIR

CACHE_DIR = API_DIR / ".cache" / "llm"
PROVIDER = os.environ.get("FORGE_LLM_PROVIDER", "claude-cli")
TIMEOUT_S = 240
MAX_ATTEMPTS = 3

# USD per million tokens (input, output), from Anthropic's pricing page in October 2026.
# Only used by the API provider; the CLI reports its own estimate.
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.00, 10.00)}


class LLMError(Exception):
    pass


@dataclass
class LLMResult:
    data: dict
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float  # at API list prices; for the CLI this is its own estimate
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


def call_claude_cli(system: str, prompt: str, schema: dict, model: str) -> LLMResult:
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
            except OSError as e:
                raise LLMError(f"can't run the Claude CLI ({e}); set FORGE_LLM_PROVIDER=anthropic") from e
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


def call_anthropic_api(system: str, prompt: str, output: type[BaseModel], model: str) -> LLMResult:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise LLMError("ANTHROPIC_API_KEY is not set, so lessons can't be generated here")
    # The SDK retries 429, 5xx and connection errors on its own.
    client = anthropic.Anthropic(timeout=TIMEOUT_S, max_retries=MAX_ATTEMPTS - 1)
    started = time.perf_counter()
    try:
        response = client.messages.parse(
            model=model,
            max_tokens=16000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=output,
        )
    except ValidationError as e:
        raise LLMError(f"the model's JSON didn't match the schema: {e}") from e
    except anthropic.APIStatusError as e:
        raise LLMError(f"Anthropic API error {e.status_code}: {e.message}") from e
    except anthropic.APIConnectionError as e:
        raise LLMError(f"can't reach the Anthropic API: {e}") from e

    if response.stop_reason in ("refusal", "max_tokens") or response.parsed_output is None:
        raise LLMError(f"no usable answer (stop reason: {response.stop_reason})")
    usage = response.usage
    tokens_in = (
        usage.input_tokens + (usage.cache_creation_input_tokens or 0) + (usage.cache_read_input_tokens or 0)
    )
    price_in, price_out = PRICES.get(model, (0.0, 0.0))
    return LLMResult(
        data=response.parsed_output.model_dump(),
        model=model,
        tokens_in=tokens_in,
        tokens_out=usage.output_tokens,
        cost_usd=(tokens_in * price_in + usage.output_tokens * price_out) / 1_000_000,
        latency_ms=round((time.perf_counter() - started) * 1000),
    )


def complete_json(system: str, prompt: str, output: type[BaseModel], model: str) -> LLMResult:
    """Ask `model` for JSON shaped like `output`. Returns the raw dict; callers validate it."""
    schema = output.model_json_schema()
    key = hashlib.sha256(json.dumps([model, system, prompt, schema], sort_keys=True).encode()).hexdigest()
    path = CACHE_DIR / f"{key}.json"
    if path.exists() and os.environ.get("FORGE_LLM_CACHE") != "off":
        return LLMResult(**{**json.loads(path.read_text(encoding="utf-8")), "cached": True})

    if PROVIDER == "anthropic":
        result = call_anthropic_api(system, prompt, output, model)
    else:
        result = call_claude_cli(system, prompt, schema, model)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(result)), encoding="utf-8")
    return result
