# Orchestra Core (Infrastructure and Shared Utilities)

## Purpose
This directory serves as the foundational Infrastructure Layer for the entire platform. It provides shared utilities, database connectors, and state management that all other agents and CLI tools rely upon.

## What Belongs Here
- Configuration loaders and environment variable management.
- Secrets retrieval and writing (`secrets.py`).
- Database connection factories (e.g., `redis.py` returning configured clients).
- Universal wrappers for external AI providers (`llm.py`).
- Reading, parsing, and returning the global and local action indexes (`index.py`).

## What Does NOT Belong Here
- Agent-specific business logic (e.g., how to build a Composer prompt).
- Execution loops or long-running daemons.
- Terminal output formatting, CLI routers, or `print()` statements.
