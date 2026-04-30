from conductor_agent.conductor_tasks.secrets import get_secret

def get_secret(key: str) -> str:
    """
    Retrieve a secret value by key from the configured secrets backend.

    Args:
        key: The secret key to look up (e.g. "VT_API_KEY", "SLACK_WEBHOOK_URL").

    Returns:
        The secret value as a string.

    The active backend is configured in .local_config/orchestra.json under
    the "secrets" section. Supported backends: "env", "docker_secrets", "aws_ssm".
    """
    return get_secret(key)