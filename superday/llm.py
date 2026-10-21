"""One small agent runner shared by every agent.

run_agent() calls gpt-6-luna through the OpenAI Responses API (via Portkey), lets the model
call Python tools, and returns schema-checked JSON. Every model request is logged with its
real token counts and cost, and every tool call is written to the trace table.

Guards: a per-run token budget, a daily spend cap and a maximum number of model turns.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Callable

from openai import OpenAI

from . import config, db


class AIError(RuntimeError):
    """A friendly error that the UI can show."""


class BudgetExceeded(AIError):
    pass


_client: OpenAI | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        found = config.provider()
        if not found:
            raise AIError("No API key found. Put PORTKEY_API_KEY in .env (this folder or the one above).")
        name, key = found
        if name == "portkey":
            _client = OpenAI(
                api_key=key, base_url=config.PORTKEY_BASE_URL, timeout=90, max_retries=2,
                default_headers={"x-portkey-api-key": key, "x-portkey-provider": "openai"},
            )
        else:
            _client = OpenAI(api_key=key, timeout=90, max_retries=2)
    return _client


def new_run_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def cost_of(input_tokens: int, cached: int, cache_write: int, output: int) -> float:
    p = config.PRICE_PER_M
    fresh = max(input_tokens - cached - cache_write, 0)
    return (fresh * p["input"] + cached * p["cached_input"] + cache_write * p["cache_write"]
            + output * p["output"]) / 1_000_000


# ---------------------------------------------------------------------------
# JSON-schema helpers (strict mode: every field required, no extra fields)
# ---------------------------------------------------------------------------
def obj(**props) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def arr(items: dict) -> dict:
    return {"type": "array", "items": items}


STR = {"type": "string"}
INT = {"type": "integer"}
BOOL = {"type": "boolean"}


def tool_spec(name: str, description: str, **props) -> dict:
    return {"type": "function", "name": name, "description": description,
            "parameters": obj(**props), "strict": True}


# ---------------------------------------------------------------------------
# The runner
# ---------------------------------------------------------------------------
def run_agent(
    *,
    agent: str,
    run_id: str,
    instructions: str,
    user_input: str,
    schema: dict,
    schema_name: str,
    tools: list[dict] | None = None,
    tool_impls: dict[str, Callable[..., Any]] | None = None,
    max_output_tokens: int = 2_500,
    effort: str | None = None,
) -> dict:
    """Run one agent to completion and return its parsed JSON output."""
    if db.spend_today() >= config.DAILY_SPEND_CAP_USD:
        db.log_trace(run_id, agent, "guard", "daily_spend_cap", f"Blocked: daily cap ${config.DAILY_SPEND_CAP_USD:.2f} reached")
        raise BudgetExceeded(f"Daily AI budget of ${config.DAILY_SPEND_CAP_USD:.2f} reached. Try again tomorrow "
                             "or raise SUPERDAY_DAILY_CAP_USD in .env.")

    db.log_trace(run_id, agent, "input", "user_input", user_input)
    items: list[Any] = [{"role": "user", "content": user_input}]
    used_tokens = 0
    tool_impls = tool_impls or {}

    for step in range(1, config.MAX_TOOL_STEPS + 1):
        if used_tokens >= config.RUN_TOKEN_BUDGET:
            db.log_trace(run_id, agent, "guard", "run_token_budget", f"Stopped after {used_tokens} tokens")
            raise BudgetExceeded("This request used its token budget. Try a shorter input.")

        kwargs: dict[str, Any] = dict(
            model=config.MODEL,
            instructions=instructions,
            input=items,
            text={"format": {"type": "json_schema", "name": schema_name, "schema": schema, "strict": True}},
            reasoning={"effort": effort or config.REASONING_EFFORT},
            max_output_tokens=max_output_tokens,
            prompt_cache_key=f"superday-{agent}",
        )
        if tools:
            kwargs["tools"] = tools

        started = time.perf_counter()
        try:
            resp = client().responses.create(**kwargs)
        except AIError:
            raise
        except Exception as exc:  # network, auth or model errors
            status = getattr(exc, "status_code", None)
            _log_call(run_id, agent, step, None, 0, f"error {status or type(exc).__name__}")
            detail = str(exc)
            for secret in filter(None, [config.provider() and config.provider()[1]]):
                detail = detail.replace(secret, "[REDACTED]")
            db.log_trace(run_id, agent, "error", f"api_error_{status}", detail[:1500])
            if "content_filter" in detail or "content management policy" in detail:
                raise AIError("The AI provider's safety filter blocked this request. Please rephrase and avoid "
                              "instructions aimed at the AI.") from None
            raise AIError(f"The AI service did not answer ({status or type(exc).__name__}). Please try again.") from None
        latency = int((time.perf_counter() - started) * 1000)
        used_tokens += _log_call(run_id, agent, step, resp.usage, latency, resp.status or "ok")

        calls = [o for o in resp.output if getattr(o, "type", "") == "function_call"]
        if not calls:
            text = resp.output_text or ""
            if resp.status == "incomplete":
                raise AIError("The answer was cut off (output limit). Please try again.")
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                raise AIError("The AI returned an unreadable answer. Please try again.") from None
            db.log_trace(run_id, agent, "output", schema_name, result)
            return result

        items.extend(resp.output)
        for call in calls:
            try:
                args = json.loads(call.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            db.log_trace(run_id, agent, "tool_call", call.name, args)
            fn = tool_impls.get(call.name)
            try:
                output = fn(**args) if fn else {"error": f"Unknown tool {call.name}"}
            except Exception as exc:  # a tool bug should not crash the run
                output = {"error": f"{type(exc).__name__}: {exc}"}
            db.log_trace(run_id, agent, "tool_result", call.name, output)
            items.append({"type": "function_call_output", "call_id": call.call_id,
                          "output": json.dumps(output, ensure_ascii=False, default=str)})

    db.log_trace(run_id, agent, "guard", "max_tool_steps", f"Stopped after {config.MAX_TOOL_STEPS} model turns")
    raise AIError(f"The {agent} agent hit its step limit ({config.MAX_TOOL_STEPS}) and was stopped.")


def _log_call(run_id: str, agent: str, step: int, usage, latency_ms: int, status: str) -> int:
    inp = getattr(usage, "input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    details = getattr(usage, "input_tokens_details", None)
    cached = getattr(details, "cached_tokens", 0) or 0
    cache_write = getattr(details, "cache_write_tokens", 0) or 0
    reasoning = getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", 0) or 0
    db.execute(
        "INSERT INTO llm_calls (ts, run_id, agent, step, model, input_tokens, cached_tokens, cache_write_tokens, "
        "output_tokens, reasoning_tokens, latency_ms, cost_usd, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (db.now(), run_id, agent, step, config.MODEL, inp, cached, cache_write, out, reasoning, latency_ms,
         cost_of(inp, cached, cache_write, out), status),
    )
    return inp + out
