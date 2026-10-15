# ADR-002: LLM provider for generation and judging

Status: accepted (2026-10-15). Replaces the "OpenAI API" line of ADR-001.

## Context
The project rules say to keep API spend low. Lessons, quizzes and the LLM judge need a capable model, and the evals run often, locally and in CI. I already pay for a Claude subscription, and Claude Code can run headless (`claude -p --output-format json --json-schema ...`) on it, returning validated JSON plus token usage and an API-price cost estimate.

Anthropic's terms allow this for a subscriber's own use and document a CI token for GitHub Actions (`claude setup-token`). They don't allow serving other people through subscription credentials: a public deployment has to use an API key (Anthropic, or a cloud provider such as Azure).

## Decision
- Local development and evals call Claude through the CLI (`forge/llm.py`). The subprocess runs in an empty temp directory with no tools, no settings and no MCP servers, and `ANTHROPIC_API_KEY` is removed from its environment so it can't fall back to paid API billing.
- Models are pinned by full id: `claude-haiku-5-5` generates; the judge uses a different model, so it isn't grading its own output.
- Every response is cached on disk by model + prompts + schema.
- Retrieval (embeddings and re-ranking) runs locally with fastembed and needs no provider at all.
- Before a public deployment, add an API-key provider behind the same `complete_json` function and select it by environment variable.

## Consequences
- Generating and evaluating costs nothing beyond the subscription, but is subject to its usage limits. The cache keeps reruns cheap.
- The `cost_usd` recorded per run is the CLI's estimate at API list prices. That's the number a paid deployment would see, which is what "cost per lesson" should report.
- Calls take a few extra seconds of CLI start-up compared with a direct API call.
- The deployed demo can't generate new lessons until an API key is configured. It can still serve lessons that were already generated.
