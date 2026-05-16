# AGENTS.md — Orchestra Coding Standards

Rules for AI agents working on this codebase. These are enforced, not advisory.

---

## Architecture Layers

```
orchestra.py  (router)
    │
    ▼
  cli/         (presentation — the ONLY layer allowed to print())
    │
    ├── composer_agent/   (generation)
    ├── conductor/        (execution)
    └── orchestra_core/   (infrastructure)
```

**Import rules**:
- `orchestra_core/` imports nothing from other layers
- `composer_agent/` and `conductor/` import from `orchestra_core/` only
- `cli/` imports from all three
- Never import sideways (composer ↔ conductor)

---

## Python Style

### No print() outside cli/

Service and agent layers log to file or return data. CLI wrappers handle all user-facing output.

```python
# WRONG — in conductor/tasks/musician.py:
print("[+] Job completed")

# RIGHT — in conductor/tasks/musician.py:
logger.info("musician.job.completed", extra={"data": {...}})

# RIGHT — in cli/compose_cli.py:
print(f"[+] Output written to {path}")
```

### Return tuples from service layer

Pure functions return `(success: bool, path: str | None, error: str | None)`. Never `sys.exit()`.

```python
# RIGHT:
def compose_playbook(playbook_path) -> tuple[bool, str | None, str | None]:
    ...
    return (True, str(output_path), None)
```

### Docstrings

Every public function (no underscore prefix) must have a one-line docstring describing what it does.

```python
def get_secret(key: str) -> str:
    """Retrieve a secret value by key from the configured secrets backend."""
    ...
```

### Type hints

All public function signatures must include type hints for parameters and return values.

### No inline imports

Imports belong at the top of the file. Lazy imports only for optional dependencies that may not be installed.

```python
# WRONG:
elif args.command == "run":
    import json        # <-- move to top

# RIGHT — lazy import for optional dep:
def _openai_query(...):
    import openai     # <-- optional dependency, not installed by default
```

### No module-level mutable state

No global caches, singletons, or mutable defaults.

---

## Naming Conventions

| What | Format |
|---|---|
| Module names | `conductor/`, `composer_agent/`, `orchestra_core/`, `cli/` |
| Index files | `action_index.json`, `integration_index.json` (both grouped dict by module) |
| Event names (logging) | Dot notation: `musician.job.failed`, `compose.playbook.succeeded` |
| CLI commands | Subcommand patterns: `compose playbook`, `compose action`, `secrets push` |

---

## Git

- Small, logical commits. Split refactors, features, and fixes.
- Commit titles under 60 characters.
- Never commit `.env` files or secrets.
- Never amend or force push unless explicitly asked.

---

## Dependencies

- Core: `openai`, `boto3`, `fastapi`, `redis`, `uvicorn`, `croniter`
- Optional: `anthropic`, `google-generativeai` (via `[anthropic]`, `[gemini]`)
- No new dependencies without discussion
