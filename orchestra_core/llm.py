import json

from orchestra_core.config import load_project_config
from orchestra_core.exceptions import OrchestraError
from orchestra_core.secrets import get_secret

SUPPORTED_PROVIDERS = {
    "openai": {
        "package": "openai",
        "secret_key": "OPENAI_API_KEY",
        "install_hint": "pip install orchestra[openai]",
    },
    "anthropic": {
        "package": "anthropic",
        "secret_key": "ANTHROPIC_API_KEY",
        "install_hint": "pip install orchestra[anthropic]",
    },
    "gemini": {
        "package": "google.genai",
        "secret_key": "GEMINI_API_KEY",
        "install_hint": "pip install orchestra[gemini]",
    },
}

DEFAULT_LLM_CONFIG = {
    "provider": "openai",
    "model": "gpt-4o",
}


def _build_decision_schema(options: list[str]) -> dict:
    """Build a JSON Schema constraining a decision to one of the allowed options."""
    return {
        "type": "object",
        "properties": {"decision": {"type": "string", "enum": options}},
        "required": ["decision"],
        "additionalProperties": False,
    }


def _load_llm_config() -> dict:
    llm_config = load_project_config().get("llm", {})
    merged = dict(DEFAULT_LLM_CONFIG)
    merged.update(llm_config)
    return merged


def _openai_query(
    system_prompt: str,
    user_prompt: str,
    model: str,
    api_key: str,
    base_url: str | None,
    options: list[str] | None = None,
) -> str:
    import openai

    client = openai.OpenAI(api_key=api_key, base_url=base_url)
    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    if options is not None:
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "decision",
                "strict": True,
                "schema": _build_decision_schema(options),
            },
        }
    response = client.chat.completions.create(**kwargs)
    content = response.choices[0].message.content
    if options is None:
        return content
    return json.loads(content)["decision"]


def _anthropic_query(
    system_prompt: str,
    user_prompt: str,
    model: str,
    api_key: str,
    options: list[str] | None = None,
) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    kwargs: dict = {
        "model": model,
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    if options is not None:
        kwargs["tools"] = [
            {
                "name": "decide",
                "description": "Choose one option",
                "strict": True,
                "input_schema": _build_decision_schema(options),
            }
        ]
        kwargs["tool_choice"] = {"type": "tool", "name": "decide"}
    response = client.messages.create(**kwargs)
    if options is None:
        return response.content[0].text
    tool_use = next(block for block in response.content if block.type == "tool_use")
    return tool_use.input["decision"]


def _gemini_query(
    system_prompt: str,
    user_prompt: str,
    model: str,
    api_key: str,
    options: list[str] | None = None,
) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    config_kwargs: dict = {"system_instruction": system_prompt}
    if options is not None:
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_json_schema"] = _build_decision_schema(options)
    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=types.GenerateContentConfig(**config_kwargs),
    )
    if options is None:
        return response.text
    return json.loads(response.text)["decision"]


def llm_query(
    system_prompt: str,
    user_prompt: str,
    options: list[str] | None = None,
) -> str:
    """Send a prompt to the configured LLM provider and return the response text.

    When `options` is None, returns the raw text response. When `options` is
    provided, the provider is asked to return JSON matching a
    `{"decision": "<one of options>"}` schema, and the chosen option string is
    returned directly.
    """
    config = _load_llm_config()
    provider = config.get("provider", DEFAULT_LLM_CONFIG["provider"])
    model = config.get("model", DEFAULT_LLM_CONFIG["model"])
    base_url = config.get("base_url")

    if provider not in SUPPORTED_PROVIDERS:
        valid = ", ".join(sorted(SUPPORTED_PROVIDERS.keys()))
        raise OrchestraError(
            f"Unknown LLM provider '{provider}'. Supported providers: {valid}."
        )

    provider_info = SUPPORTED_PROVIDERS[provider]
    secret_key = provider_info["secret_key"]

    try:
        api_key = get_secret(secret_key)
    except KeyError:
        raise OrchestraError(
            f"Secret '{secret_key}' not found. Set it in your environment or .env file."
        ) from None

    if provider == "openai":
        try:
            return _openai_query(
                system_prompt, user_prompt, model, api_key, base_url, options
            )
        except ImportError:
            raise OrchestraError(
                f"The 'openai' package is required for the OpenAI provider. "
                f"Install it with: {provider_info['install_hint']}"
            ) from None

    if provider == "anthropic":
        try:
            return _anthropic_query(system_prompt, user_prompt, model, api_key, options)
        except ImportError:
            raise OrchestraError(
                f"The 'anthropic' package is required for the Anthropic provider. "
                f"Install it with: {provider_info['install_hint']}"
            ) from None

    if provider == "gemini":
        try:
            return _gemini_query(system_prompt, user_prompt, model, api_key, options)
        except ImportError:
            raise OrchestraError(
                f"The 'google-genai' package is required for the "
                f"Gemini provider. "
                f"Install it with: {provider_info['install_hint']}"
            ) from None
