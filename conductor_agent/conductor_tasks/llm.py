import json
import sys

from conductor_agent.conductor_tasks.config import get_project_config_path
from conductor_agent.conductor_tasks.secrets import get_secret

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
    config_path = get_project_config_path()

    if not config_path.exists():
        return dict(DEFAULT_LLM_CONFIG)

    with open(config_path, "r") as f:
        data = json.load(f)

    llm_config = data.get("llm", {})
    merged = dict(DEFAULT_LLM_CONFIG)
    merged.update(llm_config)
    return merged


def _openai_query(prompt: str, model: str, api_key: str, base_url: str | None) -> str:
    import openai

    client = openai.OpenAI(api_key=api_key, base_url=base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content


def _anthropic_query(prompt: str, model: str, api_key: str) -> str:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


def _gemini_query(prompt: str, model: str, api_key: str) -> str:
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model_obj = genai.GenerativeModel(model)
    response = model_obj.generate_content(prompt)
    return response.text


def llm_query(prompt: str) -> str:
    config = _load_llm_config()
    provider = config.get("provider", DEFAULT_LLM_CONFIG["provider"])
    model = config.get("model", DEFAULT_LLM_CONFIG["model"])
    base_url = config.get("base_url")

    if provider not in SUPPORTED_PROVIDERS:
        valid = ", ".join(sorted(SUPPORTED_PROVIDERS.keys()))
        print(
            f"Error: Unknown LLM provider '{provider}'. Supported providers: {valid}.",
            file=sys.stderr,
        )
        sys.exit(1)

    provider_info = SUPPORTED_PROVIDERS[provider]
    secret_key = provider_info["secret_key"]

    try:
        api_key = get_secret(secret_key)
    except KeyError:
        print(
            f"Error: Secret '{secret_key}' not found. "
            f"Set it in your environment or .env file.",
            file=sys.stderr,
        )
        sys.exit(1)

    if provider == "openai":
        try:
            return _openai_query(prompt, model, api_key, base_url)
        except ImportError:
            print(
                f"Error: The 'openai' package is required for the OpenAI provider. "
                f"Install it with: {provider_info['install_hint']}",
                file=sys.stderr,
            )
            sys.exit(1)

    if provider == "anthropic":
        try:
            return _anthropic_query(prompt, model, api_key)
        except ImportError:
            print(
                f"Error: The 'anthropic' package is required for the Anthropic provider. "
                f"Install it with: {provider_info['install_hint']}",
                file=sys.stderr,
            )
            sys.exit(1)

    if provider == "gemini":
        try:
            return _gemini_query(prompt, model, api_key)
        except ImportError:
            print(
                f"Error: The 'google-generativeai' package is required for the Gemini provider. "
                f"Install it with: {provider_info['install_hint']}",
                file=sys.stderr,
            )
            sys.exit(1)