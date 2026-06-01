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

### Return typed result objects from service layer

Pure functions return small frozen dataclasses (e.g. `ComposeResult`, `ExecutionResult`). Never `sys.exit()` from service code.

```python
# RIGHT:
@dataclass(frozen=True, slots=True)
class ComposeResult:
    ok: bool
    path: str | None = None
    error: str | None = None
    new_keys: list[str] = field(default_factory=list)

def compose_playbook(playbook_path) -> ComposeResult:
    ...
    return ComposeResult(ok=True, path=str(output_path))
```

**Why dataclasses over tuples:**
- Named fields (`result.ok`, `result.error`) instead of positional (`result[0]`, `result[2]`)
- Adding a new field with a default is non-breaking
- Type checking and IDE autocomplete work out of the box
- Immutable by default (`frozen=True`), memory efficient (`slots=True`)

**Why not `sys.exit()`:** Service code may be imported by a web UI, Discord bot, or test runner. Exiting the process from a library function is hostile. Let the CLI layer (`cli/`) handle exit codes.

### Docstrings

Every public function (no underscore prefix) must have a small (1-3 sentences) docstring describing what it does.

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

### Keep it simple

No over-engineering. Implement the simplest thing that satisfies the requirement. No unnecessary abstractions, no future-proofing, no speculative features.

---

## Workflow

- Work incrementally — implement one step of the plan at a time, not the entire plan in one pass.
- If a task is complex, break it into smaller sub-tasks and complete each before moving on.
- DO NOT START WRITING CODE UNLESS EXPLICITLY TOLD TO EVEN IF IN BUILD MODE.

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

- Small, logical commits. Split refactors, features, and fixes. Do not generate large chunks of code in a single commit.
- Commit titles under 60 characters.
- Never commit `.env` files or secrets.
- Never amend or force push unless explicitly asked.

---

## Dependencies

- Core: `openai`, `boto3`, `fastapi`, `redis`, `uvicorn`, `croniter`
- Optional: `anthropic`, `google-generativeai` (via `[anthropic]`, `[gemini]`)
- No new dependencies without discussion
