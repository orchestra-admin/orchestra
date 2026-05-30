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
        "package": "google.generativeai",
        "secret_key": "GEMINI_API_KEY",
        "install_hint": "pip install orchestra[gemini]",
    },
}

DEFAULT_LLM_CONFIG = {
    "provider": "openai",
    "model": "gpt-4o",
}


def _load_llm_config() -> dict:
    llm_config = load_project_config().get("llm", {})
    merged = dict(DEFAULT_LLM_CONFIG)
    merged.update(llm_config)
    return merged


def _openai_query(
    system_prompt: str, user_prompt: str, model: str, api_key: str, base_url: str | None
) -> str:
    import openai

    client = openai.OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return response.choices[0].message.content


def _anthropic_query(
    system_prompt: str, user_prompt: str, model: str, api_key: str
) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text


def _gemini_query(
    system_prompt: str, user_prompt: str, model: str, api_key: str
) -> str:
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    try:
        model_obj = genai.GenerativeModel(model, system_instruction=system_prompt)
    except TypeError:
        model_obj = genai.GenerativeModel(model)
        user_prompt = system_prompt + "\n\n" + user_prompt
    response = model_obj.generate_content(user_prompt)
    return response.text


def llm_query(system_prompt: str, user_prompt: str) -> str:
    """Send a prompt to the configured LLM provider and return the response text."""
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
            f"Secret '{secret_key}' not found. "
            f"Set it in your environment or .env file."
        ) from None

    if provider == "openai":
        try:
            return _openai_query(system_prompt, user_prompt, model, api_key, base_url)
        except ImportError:
            raise OrchestraError(
                f"The 'openai' package is required for the OpenAI provider. "
                f"Install it with: {provider_info['install_hint']}"
            ) from None

    if provider == "anthropic":
        try:
            return _anthropic_query(system_prompt, user_prompt, model, api_key)
        except ImportError:
            raise OrchestraError(
                f"The 'anthropic' package is required for the Anthropic provider. "
                f"Install it with: {provider_info['install_hint']}"
            ) from None

    if provider == "gemini":
        try:
            return _gemini_query(system_prompt, user_prompt, model, api_key)
        except ImportError:
            raise OrchestraError(
                f"The 'google-generativeai' package is required for the "
                f"Gemini provider. "
                f"Install it with: {provider_info['install_hint']}"
            ) from None
