# Composer Agent (Generation Engine)

## Purpose
The Generation Engine, responsible for reading natural language descriptions or Markdown playbooks and translating them into executable Python scripts and providing developer feedback.

## What Belongs Here
- Interactions with LLMs to generate or review code.
- Construction of LLM prompts (e.g., `review_prompt.md`).
- Parsing Markdown files and writing generated Python scripts to the user's workspace.
- Functions that return structured data (strings, tuples, or status codes) indicating the result of a generation task.

## What Does NOT Belong Here
- Execution of the generated scripts.
- Infrastructure concerns like connecting to Redis or running cron jobs.
- Terminal output logic or `print()` statements (these belong in the `cli/` layer).
