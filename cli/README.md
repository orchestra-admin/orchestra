# CLI (Presentation Layer)

## Purpose
This directory acts as the Presentation Layer for the Orchestra framework following a strict Ports and Adapters (Hexagonal) architecture. It is the only boundary where the application interacts directly with the user's terminal.

## What Belongs Here
- Argument parsing, user input handling, and terminal UI logic.
- All `print()` statements, ASCII banners, error message formatting, and data tables.
- Lightweight wrapper functions that accept user input, call a backend service from the core or agents, and print the returned result.

## What Does NOT Belong Here
- Core business logic or file parsing.
- Database connections or Redis queue interactions.
- LLM prompt construction or code generation logic.
