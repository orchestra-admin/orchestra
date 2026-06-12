# CLI Guide

This is the full reference for every `orchestra` subcommand.

For install instructions, the Quick Start, and the day-to-day operator workflow, see the main `README.md`. For deployment and architecture context, see `docs/DEVELOPER_GUIDE.md`.

---

## Reference

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
| `orchestra jobs failed list` | List failed jobs in the DLQ |
| `orchestra jobs failed show <id-or-index>` | Show details for one failed job |
| `orchestra jobs failed replay <id-or-index>` | Replay a failed job (if payload is available) |
| `orchestra jobs failed purge --yes` | Purge all DLQ records |
| `orchestra jobs failed export --output <file>` | Export DLQ records as JSON |
| `orchestra secrets push` | Push `.env` values to the configured secrets backend |
| `orchestra secrets list` | List known secret keys and their status |
| `orchestra server [--port]` | Start the webhook HTTP server |
| `orchestra musician` | Start the Redis job worker (runs `musicsheets/<event_type>.py`) |
| `orchestra scheduler` | Start the cron-based scheduler |
