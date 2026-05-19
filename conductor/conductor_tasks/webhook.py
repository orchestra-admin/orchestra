import hashlib
import hmac
import json

from orchestra_core.config import get_project_root, load_musician_config, MAX_WEBHOOK_BODY_BYTES
from orchestra_core.secrets import get_secret
from orchestra_core.redis import get_redis_client
from conductor.conductor_tasks.musician import (
    build_queue_job,
    enqueue_job,
)
import logging

logger = logging.getLogger(__name__)


def load_server_modules():
    """Dynamically import and return uvicorn and FastAPI server modules."""
    try:
        import uvicorn
        from fastapi import FastAPI, HTTPException, Request
    except ImportError as exc:
        raise RuntimeError("fastapi and uvicorn packages are required to run the Orchestra server.") from exc

    return {
        "uvicorn": uvicorn,
        "FastAPI": FastAPI,
        "HTTPException": HTTPException,
        "Request": Request,
    }


def get_webhook_secret() -> str:
    """Retrieve the WEBHOOK_SECRET from the configured secrets backend."""
    try:
        return get_secret("WEBHOOK_SECRET")
    except KeyError:
        raise RuntimeError("WEBHOOK_SECRET is required to run the Orchestra server.")


def get_signature_header(headers) -> str | None:
    """Extract the webhook HMAC signature from request headers."""
    return headers.get("x-orchestra-signature-256") or headers.get("x-hub-signature-256")


def build_signature(raw_body: bytes, secret: str) -> str:
    """Compute an HMAC SHA-256 signature for a raw request body."""
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def is_valid_signature(raw_body: bytes, signature: str | None, secret: str) -> bool:
    """Verify a webhook request signature against the expected HMAC digest."""
    if not signature:
        return False

    expected = build_signature(raw_body, secret)
    return hmac.compare_digest(signature, expected)


def create_webhook_app():
    """Create and return a FastAPI webhook app with signature verification and Redis enqueuing."""
    modules = load_server_modules()
    FastAPI = modules["FastAPI"]
    HTTPException = modules["HTTPException"]

    project_root = get_project_root()
    musician_config = load_musician_config(project_root)
    queue_key = musician_config["queue_key"]

    redis_client = get_redis_client()
    redis_client.ping()

    secret = get_webhook_secret()
    Request = modules["Request"]
    app = FastAPI()

    @app.post("/webhook")
    async def receive_webhook(request: Request):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_WEBHOOK_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Request body too large")

        raw_body = await request.body()
        if len(raw_body) > MAX_WEBHOOK_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Request body too large")
        signature = get_signature_header(request.headers)

        if not is_valid_signature(raw_body, signature, secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

        try:
            payload = json.loads(raw_body.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Request body must be valid JSON") from exc

        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Request body must be a JSON object")

        try:
            job = build_queue_job(
                payload,
                metadata={
                    "path": str(request.url.path),
                    "client": request.client.host if request.client else None,
                },
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        enqueue_job(redis_client, queue_key, job)
        logger.info("webhook.request.accepted", extra={"data": {"event_type": job["event_type"], "client_ip": request.client.host if request.client else None}})
        return {"queued": True, "event_type": job["event_type"]}

    return app


def start_server(port=8080):
    """Start the Orchestra webhook server on the specified port."""
    from orchestra_core.logging import setup_logging
    setup_logging()

    modules = load_server_modules()
    uvicorn = modules["uvicorn"]
    app = create_webhook_app()
    uvicorn.run(app, host="0.0.0.0", port=port)
