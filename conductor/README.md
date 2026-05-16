# Conductor (Execution Engine)

## Purpose
The Conductor is the Execution Engine for Orchestra. Its sole responsibility is to safely and reliably execute the playbooks that the Composer has generated, managing the flow of data and background jobs.

## What Belongs Here
- The Musician worker daemon that continuously polls the Redis queue for jobs.
- The Scheduler daemon that enqueues cron-based jobs.
- The Webhook server that listens for external HTTP POST events to trigger playbooks.
- Subprocess execution logic to safely run the compiled Python playbooks.

## What Does NOT Belong Here
- LLM prompting, code generation, or playbook reviewing.
- Shared database connection bootstrapping (e.g., setting up the Redis client belongs in `orchestra_core`).
- Terminal output logic or `print()` statements (these belong in the `cli/` layer).
