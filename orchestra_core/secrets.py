import logging
import os
from pathlib import Path

from orchestra_core.config import get_project_root, load_project_config
from orchestra_core.validators import validate_secret_key_name

logger = logging.getLogger(__name__)


def _load_secrets_config() -> dict:
    return load_project_config().get(
        "secrets", {"backend": "env", "backend_configs": {}}
    )


def _load_env_file(path: Path) -> dict:
    env_vars = {}
    if not path.exists():
        return env_vars

    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if value.startswith("<set_in_"):
                continue
            if key:
                env_vars[key] = value

    return env_vars


def _get_secret_env(key: str) -> str:
    """Retrieve a secret from environment variables or the .env file."""
    value = os.environ.get(key)
    if value is not None:
        return value

    config = _load_secrets_config()
    env_config = config.get("backend_configs", {}).get("env", {})
    dotenv_path = Path(env_config.get("path", ".env"))

    if dotenv_path.is_absolute():
        env_file = dotenv_path
    else:
        env_file = get_project_root() / dotenv_path

    env_vars = _load_env_file(env_file)
    if key in env_vars:
        value = env_vars[key]
        if value.startswith("<set_in_"):
            raise KeyError(
                f"Secret '{key}' is set to a placeholder '{value}'. "
                f"The value now lives in the configured secrets backend. "
                f"Run 'orchestra secrets list' to verify."
            )
        return value

    raise KeyError(
        f"Secret '{key}' not found in environment or .env file. "
        f"Make sure it is set in your .env file or environment."
    )


def _get_secret_docker_secrets(key: str) -> str:
    validate_secret_key_name(key)
    config = _load_secrets_config()
    docker_config = config["backend_configs"].get("docker_secrets", {})
    secrets_path = Path(docker_config.get("path", "/run/secrets"))

    file_path = secrets_path / key

    if not file_path.exists():
        raise KeyError(
            f"Secret '{key}' not found at {file_path}. "
            f"Make sure the Docker secret is mounted in {secrets_path}."
        )

    return file_path.read_text().rstrip("\n")


def _get_secret_aws_ssm(key: str) -> str:
    try:
        import boto3
    except ImportError:
        raise ImportError(
            "boto3 is required for the 'aws_ssm' secrets backend. "
            "Install it with: pip install orchestra[aws]"
        ) from None

    config = _load_secrets_config()
    ssm_config = config["backend_configs"].get("aws_ssm", {})
    region = ssm_config.get("region") or None
    prefix = ssm_config.get("prefix", "/orchestra/")

    full_key = f"{prefix}{key}"

    client_kwargs = {}
    if region:
        client_kwargs["region_name"] = region
    client = boto3.client("ssm", **client_kwargs)

    try:
        response = client.get_parameter(Name=full_key, WithDecryption=True)
    except client.exceptions.ParameterNotFound:
        raise KeyError(
            f"Secret '{key}' not found in AWS SSM at parameter name '{full_key}' "
            f"(region: {region}). Make sure the parameter exists."
        ) from None

    return response["Parameter"]["Value"]


_BACKENDS = {
    "env": _get_secret_env,
    "docker_secrets": _get_secret_docker_secrets,
    "aws_ssm": _get_secret_aws_ssm,
}


def _set_secret_aws_ssm(key: str, value: str) -> None:
    import boto3

    config = _load_secrets_config()
    ssm_config = config.get("backend_configs", {}).get("aws_ssm", {})
    region = ssm_config.get("region") or None
    prefix = ssm_config.get("prefix", "/orchestra/")

    full_key = f"{prefix}{key}"
    client_kwargs = {}
    if region:
        client_kwargs["region_name"] = region
    client = boto3.client("ssm", **client_kwargs)
    client.put_parameter(
        Name=full_key, Value=value, Type="SecureString", Overwrite=True
    )


def _set_secret_docker_secrets(key: str, value: str) -> None:
    validate_secret_key_name(key)
    config = _load_secrets_config()
    docker_config = config.get("backend_configs", {}).get("docker_secrets", {})
    secrets_path = Path(docker_config.get("path", "/run/secrets"))
    secrets_path.mkdir(parents=True, exist_ok=True)
    (secrets_path / key).write_text(value)


_SET_BACKENDS = {
    "aws_ssm": _set_secret_aws_ssm,
    "docker_secrets": _set_secret_docker_secrets,
}


def set_secret(key: str, value: str) -> None:
    """Write a secret value to the configured secrets backend."""
    config = _load_secrets_config()
    backend_name = config.get("backend", "aws_ssm")

    if backend_name == "env":
        return

    write_fn = _SET_BACKENDS.get(backend_name)
    if write_fn is None:
        raise ValueError(
            f"Push not supported for secrets backend '{backend_name}'. "
            f"Supported backends: {', '.join(sorted(_SET_BACKENDS.keys()))}"
        )

    write_fn(key, value)


def get_secret(key: str) -> str:
    """Retrieve a secret value by key from the configured secrets backend."""
    config = _load_secrets_config()
    backend_name = config.get("backend", "env")

    if backend_name not in _BACKENDS:
        raise ValueError(
            f"Unknown secrets backend '{backend_name}'. "
            f"Supported backends: {', '.join(sorted(_BACKENDS.keys()))}"
        )

    return _BACKENDS[backend_name](key)


def sync_env_keys(integrations: dict) -> list[str]:
    """Append missing secret key labels from the integration index to .env.

    Returns the list of keys that were newly added.
    """
    all_secrets = set()
    for info in integrations.values():
        for key in info.get("secrets", []):
            all_secrets.add(key)

    if not all_secrets:
        return []

    project_root = get_project_root()
    env_file = project_root / ".env"
    existing_lines = env_file.read_text().splitlines() if env_file.exists() else []
    existing_keys = set()
    for line in existing_lines:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            existing_keys.add(line.split("=", 1)[0].strip())

    missing = sorted(all_secrets - existing_keys)
    if missing:
        with open(env_file, "a") as f:
            if existing_lines and existing_lines[-1].strip() != "":
                f.write("\n")
            for key in missing:
                f.write(f"{key}=\n")
        logger.info(
            "admin.env.synced",
            extra={"data": {"added": len(missing), "keys": sorted(missing)}},
        )

    return missing
