import json

from orchestra_core.llm import llm_query

_DEFAULT_ASK_SYSTEM_PROMPT = (
    "You are helping an automation playbook. "
    "Answer concisely and only use the provided context."
)
_DECIDE_SYSTEM_PROMPT = (
    "You are helping an automation playbook make one bounded control-flow decision."
)
_MAX_ATTEMPTS = 3


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

    Uses the provider's structured-output support so the response is
    schema-validated to `{"decision": "<one of options>"}` at the API
    level. The chosen option string is returned directly.

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

    user_prompt = f"Decision prompt:\n{prompt}\n\nContext:\n{_format_context(context)}"

    last_error: str = ""
    for _ in range(_MAX_ATTEMPTS):
        try:
            result = llm_query(_DECIDE_SYSTEM_PROMPT, user_prompt, options=options)
        except Exception as exc:
            last_error = f"llm_query failed: {exc}"
            continue

        if result in options:
            return result
        last_error = f"result {result!r} not in options {options!r}"

    if default is not None:
        return default
    raise RuntimeError(
        f"decide() failed after {_MAX_ATTEMPTS} attempts; last error: {last_error}"
    )
