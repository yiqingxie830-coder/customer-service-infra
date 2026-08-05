# Claude Guidance

This repo is an infrastructure workspace for a customer service application. Keep changes small, explicit, and grounded in files that exist.

## Architecture Boundaries

- `db/` holds the shared SQLite database (`store.sqlite`) and schema migration scripts (`migrate_schema.py`) used across services.
- `customer-service-agent/` contains the LangGraph agent backend and remains the source of truth for agent orchestration and conversation behavior.
- `app-backend/` is a lightweight FastAPI translation layer exposing `/chat` (proxying to LangGraph) and `/users`, `/prompts`, `/experts` (querying SQLite directly). Do not add conversation orchestration or LLM business logic there.
- `chat-board/` is the React/Vite/TypeScript frontend application interacting with `app-backend/`.

## Working Rules

- Do not invent setup commands, ports, deployment targets, package managers, or service contracts for uninitialized services.
- Prefer documenting confirmed behavior over intended behavior.
- Keep root docs focused on repo-level coordination; put service-specific details inside each service directory.
- Never commit secrets, `.env` files, local dependency directories, generated build outputs, or logs.

## Verification

- For documentation-only changes, verify the affected files and review the git diff.
- For code changes, run the narrowest relevant checks first, then broader typecheck/build/test commands when available.
