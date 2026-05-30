# slack_integration.py
from orchestra_core.secrets import get_secret


def get_webhook_url() -> str:
    """Retrieve the Slack incoming webhook URL."""
    return get_secret("SLACK_WEBHOOK_URL")
