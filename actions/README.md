# Actions

## Purpose
This directory serves as Orchestra's standard library of reusable modular automation components. It provides the building blocks that playbooks use to interact with external services and process data.

## What Belongs Here
- Pure Python functions that perform specific tasks (e.g., querying an API, parsing logs, sending a message).
- Integration modules (inside `integrations/`) that handle authentication and API wrappers for specific third-party services like Slack, Jira, or VirusTotal.
- Clear docstrings and type hints, as these are used by the Composer to understand how to build playbooks.

## What Does NOT Belong Here
- Code that run Orchestra.
