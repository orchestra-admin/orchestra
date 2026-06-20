import json
import re

from orchestra_core.llm import llm_query

_DEFAULT_ASK_SYSTEM_PROMPT = (
    "You are helping an automation playbook. "
    "Answer concisely and only use the provided context."
)
_DECIDE_SYSTEM_PROMPT = (
    "You are helping an automation playbook make one bounded control-flow decision. "
    "Return only JSON."
)
_MAX_ATTEMPTS = 3
_JSON_BLOB_PATTERN = re.compile(r"\{.*\}", re.DOTALL)


def _format_context(context: dict | None) -> str:
    """Serialize context as pretty JSON, or 'None' when absent."""
    if context is None:
        return "None"
    return json.dumps(context, indent=2, default=str, sort_keys=True)


def _validate_decision_inputs(
    prompt: str,
    options: list[str],
    default: str | None,
) -> None:
    """Validate decide() inputs, raising ValueError on any invalid argument."""
    if not prompt or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    if not options:
        raise ValueError("options must be a non-empty list")
    seen: set[str] = set()
    for option in options:
        if not option.strip():
            raise ValueError("every option must be a non-empty string")
        if option in seen:
            raise ValueError(f"duplicate option: {option!r}")
        seen.add(option)
    if default is not None and default not in options:
        raise ValueError(f"default {default!r} must be one of options")


def _parse_decision(raw: str) -> str:
    """Extract the decision string from an LLM response containing JSON.

    Strips markdown code fences and extracts the first JSON object found
    in the text. Does not validate against the allowed options — that is
    the caller's responsibility.
    """
    text = raw.strip()
    if text.startswith("```"):
        newline_idx = text.find("\n")
        if newline_idx != -1:
            text = text[newline_idx + 1 :]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

    match = _JSON_BLOB_PATTERN.search(text)
    if not match:
        raise ValueError(f"no JSON object found in response: {raw!r}")

    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ValueError(f"response is not valid JSON: {raw!r}") from exc

    if not isinstance(parsed, dict) or "decision" not in parsed:
        raise ValueError(f"response missing 'decision' key: {raw!r}")

    decision = parsed["decision"]
    if not isinstance(decision, str):
        raise ValueError(f"'decision' value must be a string: {raw!r}")

    return decision


def ask(
    prompt: str,
    context: dict | None = None,
    system_prompt: str | None = None,
) -> str:
    """Ask the configured LLM a question and return its text response.

    Args:
        prompt: The question or instruction for the LLM.
        context: Optional structured data serialized as pretty JSON and
            included in the user prompt for the LLM to reason about.
        system_prompt: Optional system prompt override. When omitted, a
            conservative default is used that asks for concise answers
            grounded in the provided context.

    Returns:
        The raw text response from the configured LLM provider.

    Raises:
        OrchestraError: If the LLM provider is misconfigured or the API
            key is missing (propagated from llm_query).
    """
    system = system_prompt if system_prompt is not None else _DEFAULT_ASK_SYSTEM_PROMPT
    user_prompt = f"Prompt:\n{prompt}\n\nContext:\n{_format_context(context)}"
    return llm_query(system, user_prompt)


def decide(
    prompt: str,
    options: list[str],
    context: dict | None = None,
    default: str | None = None,
) -> str:
    """Ask the configured LLM to choose one option for playbook control flow.

    Args:
        prompt: The decision question for the LLM.
        options: The only valid return values. Must be non-empty, unique,
            and each a non-empty string.
        context: Optional structured data serialized as pretty JSON and
            included in the user prompt.
        default: Optional fallback returned when all retry attempts fail.
            When provided, must be one of `options`.

    Returns:
        One of `options` on success, or `default` after repeated failures
        when `default` is provided.

    Raises:
        ValueError: On invalid caller input (empty prompt, empty or
            duplicate options, invalid default).
        RuntimeError: When all retry attempts fail and no `default` is
            provided.
    """
    _validate_decision_inputs(prompt, options, default)

    options_block = "\n".join(f"- {option}" for option in options)
    user_prompt = (
        f"Decision prompt:\n{prompt}\n\n"
        f"Allowed options:\n{options_block}\n\n"
        f"Context:\n{_format_context(context)}\n\n"
        "Return exactly:\n"
        '{"decision": "<one allowed option>"}'
    )

    last_error: str = ""
    for _ in range(_MAX_ATTEMPTS):
        try:
            raw = llm_query(_DECIDE_SYSTEM_PROMPT, user_prompt)
        except Exception as exc:
            last_error = f"llm_query failed: {exc}"
            continue

        try:
            decision = _parse_decision(raw)
        except ValueError as exc:
            last_error = f"parse failed: {exc}"
            continue

        if decision in options:
            return decision
        last_error = f"decision {decision!r} not in options {options!r}"

    if default is not None:
        return default
    raise RuntimeError(
        f"decide() failed after {_MAX_ATTEMPTS} attempts; last error: {last_error}"
    )
