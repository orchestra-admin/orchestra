# Developer Guide - Architecure and System Design.

This document is for engineers extending, debugging, or contributing to Orchestra. It covers the architecture, the design decisions behind it, the spec-driven workflow the project uses, and the day-to-day engineering conventions (testing, linting, CI).

For end-user / operator documentation — install, run a playbook, deploy the engine — see the main `README.md`. For deeper operator playbooks, see `docs/deployment.md`, `docs/cli-guide.md`, and `docs/authoring-playbooks.md` (under construction as part of issue #40).

---

## Architecture

### Code structure / dependency graph

```
                        ┌───────────────────────┐
                        │      orchestra.py     │  argparse router
                        │  (no business logic)  │
                        └──────────┬────────────┘
                                   │ imports
                                   ▼
                        ┌───────────────────────┐
                        │         cli/          │  presentation
                        │  (the only layer      │  - print() lives here
                        │   allowed to print)   │  - sys.exit() lives here
                        └──────────┬────────────┘
                                   │
                  ┌────────────────┼────────────────┐
                  ▼                │                 ▼
        ┌─────────────────┐        │          ┌────────────────┐
        │ composer_agent/ │        │          │   conductor/   │
        │  LLM-driven     │        │          │   daemon       │
        │  generation     │        │          │   execution    │
        └────────┬────────┘        │          └───────┬────────┘
                 │                 │                  │
                 └─────────────────┼──────────────────┘
                                   ▼
                       ┌───────────────────────┐
                       │    orchestra_core/    │  infrastructure (no upward imports)
                       │  config · secrets ·   │
                       │  llm · redis · index  │
                       │  logging · validators │
                       └───────────────────────┘

```
Notice the music-inspired terminology! As a mental model, I personally find it useful to embrace the music analogy. <br><br>
The `Orchestra` is the overaching project, the `Composer` agent convert english playbook to deterministic and repeatable `musicsheets` (python script). The `Conductor` folder contain code responsible for the execution (nginx server, webhook, redis queue etc) and the `musicians` are the python worker that pick jobs off of the queue and play the music (Run the python scripts).


### Runtime architecture

```
                          ┌─────────────────────────────────────────────┐
                          │            Docker Compose Stack             │
                          │                                             │
   Webhook Source         │  ┌─────────┐      ┌────────────────────┐    │
   ───────────────────────┼─▶│  Nginx  │─────▶│  Webhook Receiver  │    │
   POST /webhook          │  │  :80    │      │  (FastAPI) :8000   │    │
                          │  └─────────┘      └──────────┬─────────┘    │
                          │                              │              │
                          │           Enqueue            │              │
   ┌──────────────┐       │                              ▼              │
   │  Manual CLI  │       │                    ┌─────────────────┐      │
   │ playbook run │───────┼─── Enqueue ───────▶│     Redis       │      │
   └──────────────┘       │                    │  orchestra:jobs │      │
                          │                    │  orchestra:dlq  │      │
   ┌──────────────┐       │                    │                 │      │
   │  Scheduler   │───────┼─── Enqueue ───────▶└────────┬────────┘      │
   │  (cron)      │       │                             │               │
   └──────────────┘       │                             ▼               │
                          │                    ┌─────────────────┐      │
                          │                    │     Musician    │      │
                          │                    │ (Python worker) │      │
                          │                    └────────┬────────┘      │
                          └─────────────────────────────┼───────────────┘
                                                        │ subprocess
                                              ┌─────────▼──────────┐
                                              │  musicsheets/      │   ← volume
                                              │  <event_type>.py   │     mounted
                                              └────────────────────┘     from host
```

Each script runs as an isolated subprocess with stdin piping, subprocess timeout enforcement, and DLQ capture on non-zero exit codes.



### Layer rules (enforced)

The import direction is one-way. Lint and code review should reject violations:

- `orchestra_core/` imports nothing from other layers.
- `composer_agent/` and `conductor/` import only from `orchestra_core/`.
- `cli/` imports from all three layers.
- Sideways imports (composer ↔ conductor) are forbidden.

The `actions/` package sits outside the framework's import graph — it is *called by* generated `musicsheets/*.py` at runtime, not by the framework itself. Generated scripts are loaded by the musician as a fresh subprocess, so they have a clean import path into `actions/` via the project working directory.

### Design decisions

A few non-obvious choices that shape the code that is not covered in README.md

- **Generated scripts run as subprocesses, not in-process.** Each musicsheet is `subprocess.run([sys.executable, "musicsheets/<event_type>.py"], input=payload_json, ...)`. A crashing script cannot bring down the musician; memory leaks are cleaned up when the subprocess exits; timeouts are trivially enforced. See `conductor/conductor_tasks/musician.py:execute_job`.
- **Stdin is the only contract between musician and musicsheet.** Scripts read JSON from stdin and write to stdout/stderr. No shared memory, no callback protocols, no plugin loading.
- **Activation state lives in JSON, Redis is a cache.** `.local_config/orchestra.json` is the source of truth for `playbooks.deactivated`. The musician and scheduler resync the Redis set from the config on startup so Redis can be flushed without losing state. See `orchestra_core/playbook_state.py`.
- **The Composer is a one-shot LLM call with retries, not an agentic loop.** Simpler to reason about, cheaper to run, easier to make deterministic. (An agentic compose mode is tracked as a future enhancement; see issue #37.)
- **No ORM, no SQL.** All state is in Redis (queue, runtime cache) or on disk (config, generated scripts, action library). Adding a database is a future ticket (#39).
- **The CLI is the only layer that prints.** The service and infrastructure layers log to `logs/orchestra.log` and return data; the CLI formats and prints. This keeps the service layer unit-testable and reuse-friendly (a web UI or Discord bot can call into the same code without inheriting terminal output).

---

## Spec-driven development

This project uses a spec-driven workflow for non-trivial changes. And we encourage the reader to follow a similar process. The goal is to agree on what we are building *before* writing code, and to leave a paper trail that explains *why* a feature looks the way it does. 

We also encourage the user to ultilise or extend the existing `AGENTS.md`. `AGENTS.md` at the repo root is the live rulebook for AI coding agents (and humans) working in this codebase. It captures conventions that are short, mechanical, and non-negotiable: where to put code, what to import, how to write service-layer return types, how to handle errors. Read it before opening a PR and follow it.

### The workflow

```
   New Proposal
        │
        ▼
   Create a SPEC  (with a coding agent)
        │
        ▼
   Agree on an implementation PLAN 
        │
        ▼
   Implement in small, logical commits 
   (Commits should be self-contained change that compiles, lints, and passes tests)
        │
        ▼
   (Optional) Open a PR
```


---

## Testing, linting, and coding guidelines

### Testing

The project uses `pytest` with a split between fast unit tests and slower integration smoke tests. Tests are deterministic, offline, and fast. **No** test in the default suite requires a network, Docker, Redis, AWS, OpenAI, Slack, VirusTotal, or any other external service. That is a hard rule.

Install test dependencies:

```bash
python3 -m pip install -e ".[test]"
```

Run the unit test suite:

```bash
pytest
```

Run only the integration smoke tests (these exercise the installed `orchestra` command, may be slower, and may require the package to be installed):

```bash
pytest -m integration
```

Run both, in order:

```bash
pytest
pytest -m integration
```

Quick syntax check across the whole framework (a useful pre-commit sanity step):

```bash
python3 -m compileall orchestra.py cli composer_agent conductor orchestra_core actions
```

Test layout:

- `tests/` is the single top-level test directory.
- `tests/test_<module>.py` mirrors the source module it covers (`tests/test_musician.py` for `conductor/conductor_tasks/musician.py`, etc.).
- Use `tmp_path`, `monkeypatch`, `capsys`, and small fake objects in place of real services.
- For service-layer code that hits Redis, use a fake Redis (a small class with `delete`, `sadd`, `srem`, `sismember`, `smembers`) — see `tests/test_playbook_state.py` for the canonical example.

Example things to test:

- Public function behaviour: success, error, and edge cases.
- Validation rules (event type format, secret key names, path safety).
- Config loading and defaults.
- DLQ record sanitization (no payloads leak).
- Idempotency of state-mutating helpers (e.g. `deactivate_playbook_state` returns `False` on a duplicate call).


### Linting

The project uses **Ruff** for both linting and formatting. Black is **not** used.

Install linting dependencies:

```bash
python3 -m pip install -e ".[lint]"
```

Run the linter:

```bash
ruff check .
```

Auto-fix safe issues:

```bash
ruff check --fix .
```

Check formatting:

```bash
ruff format --check .
```

Apply formatting:

```bash
ruff format .
```

Configuration lives in `pyproject.toml` under `[tool.ruff]`. Notable rules:

- `T201` (`flake8-print`) is on globally, so any stray `print()` in the service / infrastructure layer fails CI. The only allowed sources of `print()` are `cli/` and `orchestra.py` (the router).
- `D` (`pydocstyle`, Google convention) is on globally, with per-file ignores for `tests/*` (tests don't need docstrings) and `__init__.py` files.
- `B` (bugbear), `UP` (pyupgrade), `SIM` (simplify), `C4` (comprehensions), `I` (isort), `E`, `F` are all on.

### Pre-commit hooks

Pre-commit is configured in `.pre-commit-config.yaml`. After installing the lint extras:

```bash
pre-commit install
```

Every `git commit` will then run Ruff against staged files. If issues are found, the commit is blocked until they are fixed. To bypass (rarely appropriate):

```bash
git commit --no-verify -m "your message"
```

### Coding guidelines

Beyond what Ruff enforces, follow these conventions:

- **Service-layer functions return typed dataclasses**, not tuples. `ComposeResult`, `ExecutionResult` are the canonical examples. `sys.exit()` is never called from service code — only the CLI exits processes.
- **Public functions have docstrings.** One to three sentences. Use the Google pydocstyle convention (which is what Ruff's `D` rules check for).
- **Public function signatures have type hints.** Parameters and return type. Use modern union syntax (`str | None`, not `Optional[str]`).
- **Imports at the top of the file.** Lazy imports are only acceptable for optional dependencies that may not be installed (e.g. `openai`, `anthropic`, `boto3`).
- **No module-level mutable state.** No global caches, no mutable defaults.
- **Keep it simple.** No over-engineering, no premature abstractions, no future-proofing. Implement the simplest thing that satisfies the requirement.
- **Small, logical commits.** Split refactors, features, and fixes. Commit titles under 60 characters. Never commit secrets or `.env` files.

---

## CI pipeline

Continuous integration runs on every pull request and every push to `main`, via GitHub Actions (`.github/workflows/`).

### Triggers

- **Pull requests** against `main` — full validation must pass before merge.
- **Pushes to `main`** — same suite, additionally tagged as a release candidate run.

### Jobs

The default CI matrix runs on Python 3.11 and 3.12, with two jobs:

1. **Lint** — `ruff check .` against the full repo. Fails the build on any Ruff violation.
2. **Test** — `pytest` for unit tests. Fails on any test failure.

A separate optional **Integration** job runs `pytest -m integration` (slower, exercises the installed `orchestra` command) and is allowed to be opt-in / manual to keep PR feedback fast.

### Local pre-flight

Before opening a PR, run the same commands CI will run:

```bash
python3 -m compileall orchestra.py cli composer_agent conductor orchestra_core actions
ruff check .
pytest
```

If you have changed anything under `orchestra_core/init_assets/`, also confirm `orchestra init` still scaffolds a working project (smoke test: `cd /tmp && mkdir t && cd t && orchestra init && ls`).

### Secrets in CI

CI does not require any secrets. Tests that need real LLM API keys, AWS credentials, or external services are opt-in and skipped by default. A red CI run is never a secrets problem.

### Branch protection

`main` is protected: PRs require at least one approving review and a green CI run before merge. Squash-merge is the default to keep history linear.

---

## Where to go next

- New to the codebase? Read `AGENTS.md` end to end, then come back here.
- Debugging a failing test? Read the test first — it documents the contract. Then the implementation.
- Adding a new integration or action? Look at the existing built-ins under `actions/` and `actions/integrations/`, follow the same shape (thin credential wrapper + business-logic function with a docstring), then run `orchestra actions` to confirm it shows up in the index.
