import json
import os
from pathlib import Path

from conductor_agent.conductor_tasks.config import get_project_config_path, get_project_root


def _load_secrets_config() -> dict:
    config_path = get_project_config_path()

    if not config_path.exists():
        return {"backend": "env", "backend_configs": {}}

    with open(config_path, "r") as f:
        data = json.load(f)

    return data.get("secrets", {"backend": "env", "backend_configs": {}})


def _load_env_file(path: Path) -> dict:
    env_vars = {}
    if not path.exists():
        return env_vars

    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key:
                env_vars[key] = value

    return env_vars


_ENV_FILE_CACHE: dict | None = None


def _get_secret_env(key: str) -> str:
    value = os.environ.get(key)
    if value is not None:
        return value

    global _ENV_FILE_CACHE
    if _ENV_FILE_CACHE is None:
        config = _load_secrets_config()
        env_config = config.get("backend_configs", {}).get("env", {})
        dotenv_path = Path(env_config.get("path", ".env"))

        if dotenv_path.is_absolute():
            env_file = dotenv_path
        else:
            env_file = get_project_root() / dotenv_path

        _ENV_FILE_CACHE = _load_env_file(env_file)

    if key in _ENV_FILE_CACHE:
        return _ENV_FILE_CACHE[key]

    raise KeyError(
        f"Secret '{key}' not found in environment or .env file. "
        f"Make sure it is set in your .env file or environment."
    )


def _get_secret_docker_secrets(key: str) -> str:
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
        )

    config = _load_secrets_config()
    ssm_config = config["backend_configs"].get("aws_ssm", {})
    region = ssm_config.get("region", "ap-southeast-2")
    prefix = ssm_config.get("prefix", "/orchestra/")

    full_key = f"{prefix}{key}"

    client = boto3.client("ssm", region_name=region)

    try:
        response = client.get_parameter(Name=full_key, WithDecryption=True)
    except client.exceptions.ParameterNotFound:
        raise KeyError(
            f"Secret '{key}' not found in AWS SSM at parameter name '{full_key}' "
            f"(region: {region}). Make sure the parameter exists."
        )

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
    region = ssm_config.get("region", "ap-southeast-2")
    prefix = ssm_config.get("prefix", "/orchestra/")

    full_key = f"{prefix}{key}"
    client = boto3.client("ssm", region_name=region)
    client.put_parameter(Name=full_key, Value=value, Type="SecureString", Overwrite=True)


def _set_secret_docker_secrets(key: str, value: str) -> None:
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
    config = _load_secrets_config()
    backend_name = config.get("backend", "env")

    if backend_name not in _BACKENDS:
        raise ValueError(
            f"Unknown secrets backend '{backend_name}'. "
            f"Supported backends: {', '.join(sorted(_BACKENDS.keys()))}"
        )

    return _BACKENDS[backend_name](key)