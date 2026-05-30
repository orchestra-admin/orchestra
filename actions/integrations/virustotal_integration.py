from orchestra_core.secrets import get_secret


def get_api_key() -> str:
    """Retrieve the VirusTotal API key."""
    return get_secret("VT_API_KEY")
