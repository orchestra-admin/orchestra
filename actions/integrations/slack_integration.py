from conductor_agent.conductor_tasks.secrets import get_secret

def get_webhook_url() -> str:
    return get_secret("SLACK_WEBHOOK_URL")
