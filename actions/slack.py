import json
import urllib.request
import urllib.error
from .integrations.slack_integration import get_webhook_url as _get_webhook_url

def send_message(text: str) -> dict:
    """
    Send a text message to the configured Slack channel via Incoming Webhook.

    Args:
        text: The message text to send to Slack.

    Returns:
        {"ok": True}  on success, or raises an Exception on failure.
    """
    webhook_url = _get_webhook_url()
    payload = json.dumps({"text": text}).encode("utf-8")

    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
    except urllib.error.URLError as e:
        raise Exception("Slack API request failed")

    return {"ok": True}
