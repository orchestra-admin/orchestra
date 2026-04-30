import hashlib
import hmac
import json

from conductor_agent.conductor_tasks.config import get_project_root, load_musician_config
from conductor_agent.conductor_tasks.secrets import get_secret
from conductor_agent.conductor_tasks.musician import (
    load_redis_module,
    build_queue_job,
    enqueue_job,
)


def load_server_modules():
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
    try:
        return get_secret("WEBHOOK_SECRET")
    except KeyError:
        raise RuntimeError("WEBHOOK_SECRET is required to run the Orchestra server.")


def get_signature_header(headers) -> str | None:
    return headers.get("x-orchestra-signature-256") or headers.get("x-hub-signature-256")


def build_signature(raw_body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def is_valid_signature(raw_body: bytes, signature: str | None, secret: str) -> bool:
    if not signature:
        return False

    expected = build_signature(raw_body, secret)
    return hmac.compare_digest(signature, expected)


def create_webhook_app():
    modules = load_server_modules()
    FastAPI = modules["FastAPI"]
    HTTPException = modules["HTTPException"]

    project_root = get_project_root()
    musician_config = load_musician_config(project_root)
    host = musician_config["host"]
    port = musician_config["port"]
    db = musician_config["db"]
    queue_key = musician_config["queue_key"]

    redis = load_redis_module()
    redis_client = redis.Redis(host=host, port=port, db=db, decode_responses=True)
    redis_client.ping()

    secret = get_webhook_secret()
    app = FastAPI()

    @app.post("/webhook")
    async def receive_webhook(request):
        raw_body = await request.body()
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
        print(f"[*] Enqueued webhook job: {job['event_type']}")
        return {"queued": True, "event_type": job["event_type"]}

    return app


def start_server(port=8080):
    modules = load_server_modules()
    uvicorn = modules["uvicorn"]
    app = create_webhook_app()

    print(f"[*] Orchestra webhook server listening on port {port}")
    print(f"[*] Project root: {get_project_root()}")
    print(f"[*] Endpoint: POST /webhook")
    uvicorn.run(app, host="0.0.0.0", port=port)
