from conductor_agent.conductor_tasks.secrets import get_secret

def get_api_key() -> str:
    return get_secret("VT_API_KEY")
