# Implementation Plan

## Objective
Build an MVP CLI tool (`generate.py`) that converts a plain-English markdown playbook into a runnable Python script.

## Steps
- [x] **Create `ip_enrichment.md`**:
   - [x] Write a sample playbook following the format in `SPEC_v1.md`.
- [x] **Implement `generate.py`**:
   - [x] Accept the playbook file path as a CLI argument.
   - [x] Read the content of the provided markdown playbook.
   - [x] Call the local `gemini` CLI tool using `subprocess`, passing the playbook content as a prompt to generate Python code.
   - [x] Write the code to `ip_enrichment.py`.

## Bugs
- [x] When running `python3 generate.py ip_enrichment.md` the gemini prompt output such as "I will read `ip_enrichment.md` to understand the playbook requirements for the Python script." is included in the generated python script.

## Open Questions & Assumptions
- **Gemini CLI Integration**: How does the local `gemini` CLI accept prompts? I will assume it can take a prompt via `stdin` (e.g., `subprocess.run(["gemini", "generate"], input=...)` or similar).

