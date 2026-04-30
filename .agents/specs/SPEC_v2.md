# SOAR MVP — Technical Specification

A lightweight, AI-powered Security Orchestration, Automation & Response (SOAR) tool that converts plain-English playbooks into executable Python scripts. No flowcharts. No proprietary DSL. Just markdown in, Python out.

---

## Overview

The user writes a structured markdown playbook describing what a script should do. They run `soar generate <playbook>` and get back a flat, runnable Python script. The generated script imports pre-built action functions from a local action library rather than reimplementing integrations from scratch.

---

## Project Structure

```
soar/
├── soar/
│   ├── __init__.py
│   ├── cli.py              # Entry point, argparse commands
│   ├── generator.py        # Reads playbook + action signatures → calls Claude API → writes script
│   └── actions/
│       ├── __init__.py
│       ├── virustotal.py   # lookup_ip()
│       └── slack.py        # send_message()
├── playbooks/
│   └── ip_enrichment.md   # Example playbook
├── generated/              # Output scripts land here (git-ignored)
├── pyproject.toml
└── README.md
```

---

## CLI Interface

The tool is invoked as `soar` from the command line.

### Commands

#### `soar generate <playbook>`

Reads a playbook `.md` file, generates a Python script, and writes it to `generated/`.

```bash
soar generate playbooks/ip_enrichment.md
# Writes to: generated/ip_enrichment.py

soar generate playbooks/ip_enrichment.md --output my_script.py
# Writes to: my_script.py
```

**Flags:**
- `--output / -o` — Override the output file path. Default: `generated/<playbook_stem>.py`
- `--dry-run` — Print the generated script to stdout instead of writing to disk

**Behaviour:**
1. Read the playbook file
2. Introspect `soar/actions/` — collect the name, signature, and docstring of every public function
3. Build the prompt (see Prompt Design below)
4. Call the Anthropic API
5. Write the raw response to the output path
6. Print the output path to stdout

---

## Playbook Format

Playbooks are markdown files with a fixed structure. All sections are required unless marked optional.

```markdown
# Playbook: <Human-readable name>

## Description
One paragraph describing what this playbook does and when it should be used.

## Inputs
- `input_name` (required): Description of what this value is
- `another_input` (optional): Description, and what happens if omitted

## Steps
1. Plain English description of step one
2. Plain English description of step two
3. ...

## Notifications
- Slack: #channel-name — what gets posted and when

## Environment Variables
- `ENV_VAR_NAME`: What it is and where to get it
```

### Authoring Rules (document these in README)

- Steps should be imperative and specific: *"Look up the IP on VirusTotal"* not *"Do threat intelligence"*
- Reference integration names explicitly: *"Send a Slack message"*, *"Call the VirusTotal API"*
- Do not write code in the playbook — describe intent only
- Each input in `## Inputs` becomes a CLI argument in the generated script

---

## Action Library

Pre-built integration functions that generated scripts can import. Each function is self-contained — it handles the HTTP call and returns a plain Python dict or string.

### `soar/actions/virustotal.py`

```python
def lookup_ip(ip: str, api_key: str) -> dict:
    """
    Look up an IP address on VirusTotal and return a structured report.

    Args:
        ip: IPv4 or IPv6 address to look up
        api_key: VirusTotal API v3 key

    Returns:
        {
            "ip": str,
            "verdict": str,           # "MALICIOUS", "SUSPICIOUS", or "CLEAN"
            "malicious": int,         # engines that flagged as malicious
            "suspicious": int,        # engines that flagged as suspicious
            "harmless": int,          # engines that flagged as harmless
            "country": str,           # two-letter country code, e.g. "US"
            "isp": str,               # AS owner / ISP name
            "reputation": int,        # VirusTotal reputation score
            "link": str               # URL to the full VT report
        }

    Verdict logic:
        malicious > 3           → "MALICIOUS"
        malicious 1–3 OR
          suspicious > 5        → "SUSPICIOUS"
        otherwise               → "CLEAN"
    """
```

**Implementation notes:**
- Endpoint: `GET https://www.virustotal.com/api/v3/ip_addresses/{ip}`
- Auth header: `x-apikey: {api_key}`
- Parse `data.attributes.last_analysis_stats` for counts
- Parse `data.attributes.country`, `data.attributes.as_owner`, `data.attributes.reputation`
- Build the link as `https://www.virustotal.com/gui/ip-address/{ip}`

---

### `soar/actions/slack.py`

```python
def send_message(webhook_url: str, text: str, blocks: list = None) -> None:
    """
    Post a message to a Slack channel via an incoming webhook.

    Args:
        webhook_url: Slack incoming webhook URL
        text:        Fallback plain-text message (shown in notifications)
        blocks:      Optional list of Slack Block Kit block dicts for rich formatting.
                     If provided, 'text' is used as the fallback only.

    Returns:
        None. Raises an exception if the POST fails.
    """
```

**Implementation notes:**
- `POST {webhook_url}` with `Content-Type: application/json`
- Body: `{"text": text}` or `{"text": text, "blocks": blocks}` if blocks provided
- Use `requests.post()`

---

## Generator Design

### Prompt Construction (`generator.py`)

The generator builds a prompt with two parts:

**System prompt:**
```
You are an expert Python developer. Your job is to convert a plain-English security 
playbook into a flat, executable Python script.

Rules:
- Output ONLY valid Python code. No markdown fences, no explanation, no preamble.
- The script must run with: python script.py [args]
- Accept all inputs defined in the playbook's "Inputs" section as CLI arguments using argparse.
- Read all secrets from environment variables using os.environ[]. Name the variables 
  exactly as listed in the playbook's "Environment Variables" section.
- Use the provided action functions wherever possible. Import them from the soar.actions module.
- Do not reimplement logic that exists in the action library.
- Follow the playbook steps in order. Do not add steps that are not in the playbook.
- Print progress to stdout as the script runs, e.g. print("[*] Looking up IP on VirusTotal...")
- Write a docstring at the top of the script describing what it does.
- The script should be flat — no function definitions, just sequential top-level code.
```

**User message:**
```
Here are the available action functions you can import and use:

{action_signatures}

---

Here is the playbook to convert:

{playbook_text}

---

Generate the Python script now.
```

### Action Signature Extraction

The generator introspects the `soar/actions/` directory at runtime:

1. Import each module in `soar/actions/`
2. For each public function (no leading underscore), extract:
   - Module path (e.g. `soar.actions.virustotal`)
   - Function name
   - Signature (via `inspect.signature()`)
   - Docstring (via `inspect.getdoc()`)
3. Format as a readable block injected into the prompt

### API Call

- Model: `claude-opus-4-5` (configurable via `SOAR_MODEL` env var)
- Auth: `ANTHROPIC_API_KEY` environment variable
- Max tokens: `4096`
- The raw text response is written directly to the output file — no post-processing

---

## Example: End-to-End Flow

### Input playbook: `playbooks/ip_enrichment.md`

```markdown
# Playbook: IP Reputation Check

## Description
Given an IP address, look it up on VirusTotal and post a summary to Slack.

## Inputs
- `ip_address` (required): The IP address to investigate

## Steps
1. Look up the IP address on VirusTotal
2. Determine a verdict based on the malicious detection count
3. Build a Slack message with: the verdict, detection counts, country, ISP, and a link to the full report
4. Post the message to Slack

## Notifications
- Slack: #security-alerts — verdict summary with VT stats

## Environment Variables
- `VIRUSTOTAL_API_KEY`: VirusTotal API v3 key
- `SLACK_WEBHOOK_URL`: Slack incoming webhook URL
```

### Expected generated output: `generated/ip_enrichment.py`

```python
"""
IP Reputation Check
Looks up an IP address on VirusTotal and posts a verdict summary to Slack.
"""

import os
import argparse
from soar.actions.virustotal import lookup_ip
from soar.actions.slack import send_message

parser = argparse.ArgumentParser(description="IP Reputation Check")
parser.add_argument("--ip-address", required=True, help="The IP address to investigate")
args = parser.parse_args()

vt_api_key = os.environ["VIRUSTOTAL_API_KEY"]
slack_webhook = os.environ["SLACK_WEBHOOK_URL"]

print(f"[*] Looking up {args.ip_address} on VirusTotal...")
report = lookup_ip(args.ip_address, vt_api_key)

print(f"[*] Verdict: {report['verdict']}")

message = (
    f"*IP Reputation Report: {report['ip']}*\n"
    f"Verdict: {report['verdict']}\n"
    f"Detections: {report['malicious']} malicious / {report['suspicious']} suspicious / {report['harmless']} harmless\n"
    f"Country: {report['country']} | ISP: {report['isp']}\n"
    f"Reputation score: {report['reputation']}\n"
    f"Full report: {report['link']}"
)

print("[*] Posting to Slack...")
send_message(slack_webhook, message)

print("[+] Done.")
```

### Running the generated script

```bash
export VIRUSTOTAL_API_KEY=your_key_here
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

python generated/ip_enrichment.py --ip-address 1.2.3.4
```

---

## Installation & Setup

```bash
# Clone the repo
git clone https://github.com/yourname/soar
cd soar

# Install in editable mode
pip install -e .

# Set required env vars
export ANTHROPIC_API_KEY=your_anthropic_key
```

### `pyproject.toml`

```toml
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.backends.legacy:BuildBackend"

[project]
name = "soar"
version = "0.1.0"
dependencies = [
    "anthropic",
    "requests",
]

[project.scripts]
soar = "soar.cli:main"
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Used by the generator to call Claude |
| `VIRUSTOTAL_API_KEY` | At runtime | Required by generated scripts that use VT |
| `SLACK_WEBHOOK_URL` | At runtime | Required by generated scripts that post to Slack |
| `SOAR_MODEL` | No | Override the Claude model. Default: `claude-opus-4-5` |

---

## Out of Scope for MVP

The following are explicitly deferred:

- Webhook execution mode (trigger via HTTP instead of CLI)
- Script caching / fingerprinting
- Additional integrations beyond VirusTotal and Slack
- Error handling in generated scripts
- A web UI
- Authentication / multi-user support
- Playbook versioning or a registry
