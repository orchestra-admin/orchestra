<!-- DRAFT — not yet reviewed. This is a side-by-side replacement candidate for README.md. -->

<img src="./logo.png" height=200px>

<br>

> *"The hottest new programming language is English"* &emsp;— **Andrej Karpathy**

<br>

:saxophone: Orchestra is a light-weight AI-assisted SOAR automation engine. You write security playbooks in plain English — no cumbersome flowcharts. Orchestra converts them into executable Python scripts using modular re-usable components; we then runs them on a lightweight automation engine.

<br>

**Built by Engineers, for Engineers.**

<br>

## How It Works

```
You write a playbook          Orchestra composes it          Orchestra runs it
     (.md)          ───▶          (.py script)        ───▶    (webhook / manual / cron)
```

1. **Write** a playbook in markdown describing your automation in plain English.
2. **Compose** it with `orchestra compose playbook <playbook.md>` — an LLM converts it to a Python script using the built-in action library.
3. **Trigger** it via webhook, CLI, or cron schedule.

<br>

For a detailed architecture review, see [`docs/developer_guide.md`](docs/developer_guide.md).

<br>

## Quick Start

### Install

Clone the framework and install it in editable mode:

```bash
git clone https://github.com/orchestra-admin/orchestra.git
cd orchestra
pip install -e .
```

The editable install gives you a working `orchestra` command on your `$PATH` and lets you read or modify the framework source alongside your automation project.

### Initialize a project

Pick a separate directory for your automation project (not the framework repo you just cloned), then scaffold it:

```bash
mkdir orchestra_workspace
cd orchestra_workspace
orchestra init
```

This scaffolds your automation project in the current directory:

```
orchestra_workspace/
├── .env                              # Your secrets (generated from .env.example)
├── .env.example                      # Required secrets template
├── .local_config/
│   └── orchestra.json                # Runtime configuration
├── docker-compose.yml                # Docker deployment stack
├── nginx.conf                        # TLS termination & proxy
├── playbooks/
│   ├── template.md                   # Playbook template
│   └── ip_enrichment.md              # Example playbook
└── musicsheets/
    ├── ip_enrichment.py              # Example automation script
    └── local_actions/
        ├── __init__.py
        ├── action_index.json
        └── local_integrations/
            └── __init__.py
```

### Configure secrets and an LLM provider

`orchestra init` already generated a `.env` from `.env.example` (with a random `WEBHOOK_SECRET` pre-filled). Open `.env` and set at least one LLM key plus any secrets the example playbook needs (VirusTotal, Slack):

```bash
vim .env
```

```bash
# OpenAI
OPENAI_API_KEY=sk-...
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...
# Gemini
GEMINI_API_KEY=...

VT_API_KEY=...
SLACK_WEBHOOK_URL=...
```

### Write your first playbook

The init scaffold includes `playbooks/ip_enrichment.md`. Compose it into a runnable script:

```bash
orchestra compose playbook playbooks/ip_enrichment.md
```

### Run it

Manual run (uses the local Python interpreter, no Docker required):

```bash
orchestra playbook run ip_enrichment --payload '{"ip": "8.8.8.8"}'
```

Or deploy the full automation engine (Redis + webhook receiver + musician + scheduler + nginx) for webhook and scheduled triggers:

```bash
docker compose up -d
```

To run it on a real server (EC2, ECS Fargate, etc.) instead of your laptop, see [`docs/deployment.md`](docs/deployment.md).

<br>

## Trigger Modes

### Webhook (default)

External services `POST /webhook`. The payload is validated (HMAC-SHA256), enqueued into Redis, and picked up by the musician. The `event_type` field in the JSON body maps to `musicsheets/{event_type}.py`. The receiver also exposes `GET /health` for liveness probes.

### Manual

Run any playbook directly from the CLI with an optional JSON payload:

```bash
orchestra playbook run revoke_creds --payload '{"user": "alice"}'
```

Manual runs respect activation state — a deactivated playbook will not execute.

### Scheduled

Cron-based recurring execution. Schedules live in `.local_config/orchestra.json` under the `schedules` section:

```bash
orchestra schedule add daily_report "0 9 * * *"
orchestra scheduler                    # Start the scheduler process
```

Scheduled jobs go through the same Redis queue as webhook jobs, so all musician behavior (timeouts, DLQ, activation state) applies identically.

### Activation state

Playbook activation/deactivation state is persisted in `.local_config/orchestra.json` under `playbooks.deactivated`. Redis is a runtime cache used for fast lookups; the musician and scheduler resync the cache from the config file on startup. To inspect or edit durable state, view `.local_config/orchestra.json` directly. This means `orchestra playbook activate <event_type>` and `orchestra playbook deactivate <event_type>` survive Redis restarts.

### Deduplication

Two Redis-backed dedupe controls prevent duplicate job execution:

**Webhook idempotency** (opt-in): Callers may send an `X-Orchestra-Idempotency-Key` header. Reusing the same key within the TTL window returns `duplicate: true` and does not enqueue a second job. Reuse the upstream event ID when possible (e.g. GitHub `X-GitHub-Delivery`, Stripe `Stripe-Event-Id`).

```text
POST /webhook
X-Orchestra-Signature-256: sha256=...
X-Orchestra-Idempotency-Key: alert-12345
```

Omitting the header queues every valid webhook (default behavior).

**Scheduler dedupe** (always-on): The scheduler uses Redis `SET NX EX` to claim one fire per event type per cron minute across all scheduler processes. A restart, overlap, or accidental scale-up within the same minute will not enqueue duplicate jobs.

Configure TTLs in `.local_config/orchestra.json`:

```json
{
  "dedupe": {
    "webhook_idempotency_ttl_seconds": 86400,
    "scheduler_ttl_seconds": 120
  }
}
```

Defaults: webhook 24h, scheduler 2min. Omit the `dedupe` section to use defaults.

<br>

## Writing a Playbook

Playbooks are markdown files with a fixed structure. See [playbooks/template.md](orchestra_core/init_assets/playbooks/template.md) for the canonical template.

See [playbooks/ip_enrichment.md](orchestra_core/init_assets/playbooks/ip_enrichment.md) and [musicsheets/ip_enrichment.py](orchestra_core/init_assets/musicsheets/ip_enrichment.py) for a simple example.

```markdown
# Playbook: IP Enrichment with Slack Notification

## Description
This script receives an IP address via webhook payload, enriches it by querying VirusTotal, and sends the result to a Slack channel.

## Inputs
- Webhook JSON payload on stdin: `{"event_type": "ip_enrichment", "ip": "1.1.1.1"}`

## Invocation
This playbook is triggered by a webhook `POST` to `/webhook`.

## Steps
1. Read the IP address from the webhook payload using `actions.webhook.get_payload`.
2. Query VirusTotal using `actions.virustotal.lookup_ip`.
3. Format the enrichment result into a human-readable message string.
4. Send the formatted message to Slack using `actions.slack.send_message`.

## Output
- A Slack message containing the IP enrichment verdict, detection stats, country, ISP, and a link to the full VirusTotal report.
```

Then compose it:

```bash
orchestra compose playbook playbooks/ip_enrichment.md
```

### The action and integration system

Generated `musicsheets/*.py` scripts are thin orchestrators that import from the **action library**. There are two kinds of modules:

- **`actions/*.py`** — high-level helpers with real business logic. Each function does one thing (e.g. `actions.virustotal.lookup_ip`), handles its own HTTP call and error reporting, and returns a plain `dict` or `str`. These are what the Composer agent reaches for when generating scripts.
- **`actions/integrations/*.py`** — thin credential wrappers. Each one exposes one or more `get_secret()` calls behind a descriptive name (e.g. `actions.integrations.slack_integration.get_webhook_url()`). Action functions call into integrations to retrieve credentials; musicsheets never read `os.environ` directly.

Add your own action functions in `musicsheets/local_actions/`, then rebuild the index:

```bash
orchestra actions
```

Your functions are automatically discoverable by the Composer agent the next time it composes a playbook.

<br>

## Configuration

Runtime config lives at `.local_config/orchestra.json`:

```json
{
  "redis": {
    "host": "127.0.0.1",
    "port": 6379,
    "db": 0
  },
  "musician": {
    "queue_key": "orchestra:jobs",
    "dlq_key": "orchestra:dlq",
    "timeout_seconds": 300,
    "block_seconds": 5
  },
  "playbooks": {
    "deactivated": []
  },
  "schedules": {
    "daily_report": "0 9 * * *"
  },
  "dedupe": {
    "webhook_idempotency_ttl_seconds": 86400,
    "scheduler_ttl_seconds": 120
  },
  "secrets": {
    "backend": "env",
    "backend_configs": {
      "env": { "path": ".env" },
      "docker_secrets": { "path": "/run/secrets" },
      "aws_ssm": { "region": "ap-southeast-2", "prefix": "/orchestra/" }
    }
  },
  "llm": {
    "provider": "openai",
    "model": "gpt-5.5"
  }
}
```

### Environment variable overrides

Most settings can be overridden at process start with `ORCHESTRA_*` environment variables, used by the Docker Compose stack to point services at the Redis container without editing the JSON:

| Key | Env var |
|---|---|
| `redis.host` | `ORCHESTRA_REDIS_HOST` |
| `redis.port` | `ORCHESTRA_REDIS_PORT` |
| `redis.db` | `ORCHESTRA_REDIS_DB` |
| `musician.queue_key` | `ORCHESTRA_QUEUE_KEY` |
| `musician.dlq_key` | `ORCHESTRA_DLQ_KEY` |
| `musician.timeout_seconds` | `ORCHESTRA_TIMEOUT_SECONDS` |
| `musician.block_seconds` | `ORCHESTRA_BLOCK_SECONDS` |

### LLM providers

| Provider | Install | Config |
|---|---|---|
| OpenAI | Included by default | `OPENAI_API_KEY` |
| Anthropic | `pip install orchestra[anthropic]` | `ANTHROPIC_API_KEY` |
| Gemini | `pip install orchestra[gemini]` | `GEMINI_API_KEY` |
| OpenAI-compatible (Ollama, Groq, Together, etc.) | Included by default | Set `base_url` in `llm` config |

### Secret Management

Generated scripts do not read environment variables directly. Instead, every credential lookup goes through `actions.secrets_helper.get_secret(key)`, which dispatches to the backend configured under `secrets.backend` in `.local_config/orchestra.json`.

#### Backends

| Backend | Description |
|---|---|
| `env` (default) | Reads from environment variables, with a fallback to a `.env` file at the configured path. |
| `docker_secrets` | Reads from files mounted at `/run/secrets/<KEY>` (or a configured path). |
| `aws_ssm` | Reads from AWS Systems Manager Parameter Store, with an optional region and key prefix. |

```json
{
  "secrets": {
    "backend": "aws_ssm",
    "backend_configs": {
      "env": { "path": ".env" },
      "docker_secrets": { "path": "/run/secrets" },
      "aws_ssm": { "region": "ap-southeast-2", "prefix": "/orchestra/" }
    }
  }
}
```

#### Pushing and rotating

For backends that are not the local `.env` file, push values from `.env` to the configured backend in one step:

```bash
orchestra secrets push
```

After a successful push, the local `.env` values are replaced with `<set_in_<backend>>` placeholders so the source of truth is unambiguous. List what is set and what is missing:

```bash
orchestra secrets list
```

<br>

## Troubleshooting

### Logging

The framework writes structured JSON events to `logs/orchestra.log` (10 MB rotation, 5 backups, 60 MB total cap). One event per line:

```json
{"timestamp":"2026-06-12T14:30:22.123Z","level":"INFO","event":"musician.job.completed","data":{"job_id":"...","event_type":"ip_enrichment","returncode":0}}
```

#### Event naming

Events use dot notation, grouped by area. The most common namespaces:

| Namespace | Examples |
|---|---|
| `compose.*` | `compose.playbook.started`, `compose.playbook.succeeded`, `compose.llm.retry` |
| `webhook.*` | `webhook.request.accepted`, `webhook.request.rejected` |
| `musician.*` | `musician.job.pulled`, `musician.job.completed`, `musician.job.dlq`, `musician.job.skipped_deactivated` |
| `scheduler.*` | `scheduler.cron.fired`, `scheduler.cron.skipped_duplicate` |
| `admin.*` | `admin.init`, `admin.secrets.push`, `admin.playbook.activate` |
| `error.*` | `error.llm_api_key`, `error.redis_connection`, `error.playbook_not_found` |

#### Levels

| Level | When |
|---|---|
| `INFO` | Normal operations: job completed, playbook composed, cron fired, secrets pushed |
| `WARNING` | Recoverable issues: job timed out, LLM retry triggered, deactivated playbook skipped |
| `ERROR` | Failures: job non-zero exit, LLM API error, Redis connection lost, config error |

The CLI's own stdout is unaffected — it is reserved for operator-facing output.

### Failed Jobs

The musician captures four failure modes into the dead letter queue (`orchestra:dlq`):

- The script returned a non-zero exit code.
- The script exceeded the configured timeout.
- No `musicsheets/<event_type>.py` was found for the event.
- The playbook was deactivated at runtime.

Inspect and manage failed jobs with the `orchestra jobs failed` subcommands:

```bash
# List failed jobs (compact table)
orchestra jobs failed list

# Show one failed job (by index or job_id)
orchestra jobs failed show 0
orchestra jobs failed show abc123

# Replay a failed job if its original payload is available
orchestra jobs failed replay 0

# Purge all failed job records (requires explicit confirmation)
orchestra jobs failed purge --yes

# Export failed jobs as JSON
orchestra jobs failed export --output failed_jobs.json
```

**Replay limitation:** Failed job records are sanitized by default — the original webhook payload is not retained. Most failed jobs will refuse to replay with a clear error message. This is a deliberate security choice: failed-job storage is operator-visible and audit-friendly, while still avoiding retention of sensitive payload data.

<br>

## CLI Reference

For the full list of subcommands, flags, and arguments, see [`docs/cli-guide.md`](docs/cli-guide.md).

<br>

## Requirements

- Python >= 3.11
- Redis (local or Docker)
- An LLM API key (OpenAI, Anthropic, Gemini, or compatible)

<br>

## License

Apache License 2.0
