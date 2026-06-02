<img src="./logo.png" height=200px>

<br>

> *"The hottest new programming language is English"* &emsp;— **Andrej Karpathy**

<br>

:saxophone: Orchestra is a light-weight AI-assisted SOAR automation engine. You write security playbooks in plain English --- no cumbersome flowcharts. Orchestra converts them into executable Python scripts using modular re-usuable components, we then run them with our lightweight automation engine.

<br>

**Built by Engineer, for Engineers.**

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

## Quick Start

### Install

```bash
pip install orchestra
```

### Initialize a project

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
    └── action_index.json
```

### Set your LLM API key

Add your API key to `.env` (copy from `.env.example`):

```bash
# OpenAI
OPENAI_API_KEY=sk-...
# Anthropic
ANTHROPIC_API_KEY=sk-ant-...
# Gemini
GEMINI_API_KEY=...
```

### Write your first playbook

See [Writing a Playbook](#writing-a-playbook) below, or start with the included example:

```bash
orchestra compose playbook playbooks/ip_enrichment.md
```

### Run it

```bash
# Manual run. (For testing, add the require API keys in .env file)
orchestra playbook run ip_enrichment --payload '{"ip": "8.8.8.8"}'

# Deploy the full automation engine.
docker compose up -d
```

<br>

## CLI Reference

| Command | Description |
|---|---|
| `orchestra init` | Scaffold a new Orchestra automation project |
| `orchestra compose playbook <playbook>` | Convert a playbook markdown file into a Python script |
| `orchestra compose action <description> [--name]` | Generate a reusable action function |
| `orchestra compose integration <description> [--name]` | Generate an integration module |
| `orchestra playbook list` | List all playbooks in the project |
| `orchestra playbook review <playbook>` | AI-powered review with structured feedback |
| `orchestra playbook activate <event_type>` | Activate a playbook for webhook/scheduled triggers |
| `orchestra playbook deactivate <event_type>` | Deactivate a playbook (state persisted in `.local_config/orchestra.json`) |
| `orchestra playbook run <event_type> [--payload]` | Run a playbook manually from the CLI |
| `orchestra actions` | List available action library functions |
| `orchestra integrations` | List available integrations |
| `orchestra schedule list` | View scheduled playbooks |
| `orchestra schedule add <event_type> <cron>` | Schedule a playbook with a cron expression |
| `orchestra schedule remove <event_type>` | Remove a schedule |
| `orchestra server [--port]` | Start the webhook HTTP server |
| `orchestra musician` | Start the Redis job worker. Musician run python scripts (musicsheets)|
| `orchestra scheduler` | Start the cron-based scheduler |

<br>

## Writing a Playbook

Playbooks are markdown files with a structured format. See `playbooks/template.md` for the canonical template.

```markdown
# Playbook: IP Enrichment with Slack Notification

## Description
Receives an IP via webhook, enriches it via VirusTotal, posts result to Slack.

## Inputs
- JSON payload: `{"event_type": "ip_enrichment", "ip": "1.1.1.1"}`

## Invocation
Triggered by a webhook POST to `/webhook`.

## Steps
1. Read the IP address from the webhook payload using `actions.webhook.get_payload`.
2. Query VirusTotal using `actions.virustotal.lookup_ip`.
3. Format the result into a human-readable message.
4. Send the message to Slack using `actions.slack.send_message`.

## Output
- A Slack message with IP verdict, detection stats, country, and ISP.

## Environment Variables
- `VT_API_KEY`: VirusTotal API key
- `SLACK_WEBHOOK_URL`: Slack incoming webhook URL
```

Then compose it:

```bash
orchestra compose playbook playbooks/ip_enrichment.md
```

<br>

## Built-in Actions

The action library provides reusable functions that the Composer agent uses when generating scripts.

### Custom Actions

Add your own action functions in `musicsheets/local_actions/`, then rebuild the index:

```bash
orchestra actions
```

Your functions will be automatically discoverable by the Composer agent.

<br>

## Trigger Modes

### Webhook (default)
External services POST to `/webhook`. the payload is validated (HMAC-SHA256), enqueued into Redis, and picked up by the musician. The `event_type` field maps to `musicsheets/{event_type}.py`.

### Manual
Run any playbook directly from the CLI with optional JSON payload:

```bash
orchestra playbook run revoke_creds --payload '{"user": "alice"}'
```

### Scheduled
Cron-based recurring execution:

```bash
orchestra schedule add daily_report "0 9 * * *"
orchestra scheduler                    # Start the scheduler process
```

### Activation State
Playbook activation/deactivation state is persisted in `.local_config/orchestra.json` under `playbooks.deactivated`. Redis is used as a runtime cache for fast lookups; the musician and scheduler resync the Redis cache from the config file on startup. To inspect or edit durable state, view `.local_config/orchestra.json` directamente. This means `orchestra playbook activate <event_type>` and `orchestra playbook deactivate <event_type>` survive Redis restarts.

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

## Failed Jobs

Inspect and manage jobs that failed during execution:

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

**Replay limitation:** Failed job records are sanitized by default — the original webhook payload is not retained. Most failed jobs will refuse to replay with a clear error message. A future feature that stores a `replay_job` field in DLQ records would enable replay for sanitized records; this is currently out of scope.

This is a deliberate security choice: failed-job storage is operator-visible and audit-friendly, while still avoiding retention of sensitive payload data.

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
    "model": "gpt-4o"
  }
}
```

### Secrets Management Backends Options

| Backend | Description |
|---|---|
| `env` (default) | Reads from environment variables (use Docker Compose `env_file` or shell exports to load `.env`) |
| `docker_secrets` | Reads from Docker Swarm/Compose secret files |
| `aws_ssm` | Reads from AWS Systems Manager Parameter Store |

### LLM Providers

| Provider | Install | Config |
|---|---|---|
| OpenAI | Included by default | `OPENAI_API_KEY` |
| Anthropic | `pip install orchestra[anthropic]` | `ANTHROPIC_API_KEY` |
| Gemini | `pip install orchestra[gemini]` | `GEMINI_API_KEY` |
| OpenAI-compatible (Ollama, Groq, Together, etc.) | Included by default | Set `base_url` in config |

<br>

## Docker Deployment

The project includes a ready-to-run Docker Compose stack:

```bash
cp .env.example .env
# Edit .env with your secrets
docker compose up -d
```

| Service | Role |
|---|---|
| `redis` | Job queue (Redis 7 Alpine) |
| `webhook` | FastAPI server receiving webhook POSTs; exposes `GET /health` liveness probe |
| `musician` | Job worker pulling from Redis and executing scripts |
| `scheduler` | Cron-based trigger process |
| `nginx` | Reverse proxy with TLS termination |

The `musicsheets/` directory is mounted as a volume — add or update scripts without rebuilding images.

<br>

## Architecture

```
                         ┌─────────────────────────────────────────────┐
                         │            Docker Compose Stack             │
                         │                                             │
  Webhook Source         │  ┌─────────┐      ┌────────────────────┐    │
  ───────────────────────┼─▶│  Nginx  │─────▶│  Webhook Receiver  │    │
  POST /webhook          │  │  :443   │      │  (FastAPI) :8000   │    │
                         │  └─────────┘      └──────────┬─────────┘    │
                         │                              │              │
  ┌──────────────┐       │                          Enqueue            │
  │  Manual CLI  │       │                              │              │
  │ playbook run │───────┼─── Enqueue ───────▶┌─────────▼──────────┐   │
  └──────────────┘       │                    │       Redis        │   │
                         │                    │      (Queue)       │   │
                         │                    └─────────┬──────────┘   │
                         │                              │              │
                         │                              │              │
  ┌──────────────┐       │                    ┌─────────▼──────────┐   │
  │  Scheduler   │       │                    │      Musician      │   │
  │  (cron)      │───────┼─── Run Job ───────▶│   (Python worker)  │   │
  └──────────────┘       │                    └─────────┬──────────┘   │
                         │                              │              │
                         └──────────────────────────────┼──────────────┘
                                                        │ subprocess
                                           ┌────────────▼────────────┐
                                           │ musicsheets/ (host vol.)│
                                           │   ip_enrichment.py      │
                                           └─────────────────────────┘
```

Each script runs as an isolated subprocess with stdin piping, subprocess timeout enforcement, and DLQ capture on non-zero exit codes.

<br>

## Testing

Install test dependencies:

```bash
python3 -m pip install -e ".[test]"
```

Run unit tests:

```bash
python3 -m compileall orchestra.py cli composer_agent conductor orchestra_core actions
pytest
```

Run integration smoke tests:

```bash
pytest -m integration
```

Run all tests (unit + integration):

```bash
pytest
pytest -m integration
```

Tests are deterministic, offline, and fast. No external network calls, Docker, Redis, AWS, OpenAI, Slack, or VirusTotal required for default CI.

<br>

## Linting

Install linting tools:

```bash
python3 -m pip install -e ".[lint]"
```

Run linter:

```bash
ruff check .
```

Auto-fix safe issues:

```bash
ruff check --fix .
```

Format code:

```bash
black .
```

### Pre-commit Hooks

Install pre-commit hooks to run linters automatically before each commit:

```bash
python3 -m pip install -e ".[lint]"
pre-commit install
```

Now every `git commit` will run Ruff and Black automatically. If issues are found, the commit will be blocked until they're fixed.

To skip hooks for a specific commit (not recommended):

```bash
git commit --no-verify -m "your message"
```

<br>

## Requirements

- Python >= 3.11
- Redis (local or Docker)
- An LLM API key (OpenAI, Anthropic, Gemini, or compatible)

<br>

## License

MIT
